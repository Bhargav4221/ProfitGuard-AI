"""ProfitGuard AI Decision Engine Service.

Implements:
1. 3-Tier Authoritative Financial Architecture:
   - Tier 1: Base Outcome Contribution (Ex-Ante Terminal Payoffs: Delivered, RTO, Cancelled)
   - Tier 2: Action-Adjusted Expected Contribution (EC) for 5 candidate actions:
             SHIP_AS_IS, VERIFY_OTP, INCENTIVIZE_PREPAID, MANUAL_REVIEW, HOLD_CANCEL
   - Tier 3: Realized Contribution Tracking and Intervention Logging
2. Single-Intervention Cost Rule: Pre-dispatch costs deducted exactly once.
3. Transparent, Configurable Risk Rules & Pincode Heuristic Calibration.
4. Policy Guard Enforcement (Safety Value Cap, Anti-Cancellation Gate, Auto-Cancel setting).
5. Audit-logged decision recording and intervention lifecycle tracking.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.schemas.decision import (
    ActionEvaluation,
    DecisionExplanation,
    PolicyGuard,
    TriggeredRule,
)
from app.services.audit_service import AuditService


class DecisionAssumptions:
    """Configurable operational assumptions for decision payoffs and risk heuristics.

    DISCLOSURE:
    These values are operational baseline assumptions, NOT machine-learned predictions
    or calibrated statistical models. Expected contributions derived from these
    assumptions represent decision-theoretic projections under stated priors.
    """

    # Baseline Prior RTO Risk
    PRIOR_RTO_COD: Decimal = Decimal("0.2500")
    PRIOR_RTO_PREPAID: Decimal = Decimal("0.0500")

    # Heuristic Risk Deltas
    DELTA_HIGH_ORDER_VALUE: Decimal = Decimal("0.1000")
    DELTA_INCOMPLETE_ADDRESS: Decimal = Decimal("0.0400")
    DELTA_MISSING_CITY: Decimal = Decimal("0.0500")
    DELTA_SUSPICIOUS_PHONE: Decimal = Decimal("0.2500")

    # Pre-Dispatch Action Operational Assumptions
    OTP_CONFIRMATION_RATE: Decimal = Decimal("0.7500")          # P(Customer confirms OTP)
    OTP_RTO_RISK_MULTIPLIER: Decimal = Decimal("0.4000")       # Residual RTO risk after OTP confirmation

    PREPAID_CONVERSION_RATE: Decimal = Decimal("0.2000")       # P(COD buyer converts to prepaid)
    PREPAID_CONVERTED_RTO: Decimal = Decimal("0.0500")         # Baseline RTO risk of converted prepaid

    MANUAL_REVIEW_APPROVAL_RATE: Decimal = Decimal("0.8000")   # P(Reviewer approves order)
    MANUAL_REVIEW_RTO_MULTIPLIER: Decimal = Decimal("1.0") / Decimal("3.0")  # Residual risk after operator review

    # Pincode Evidence & Uncertainty Safeguards
    MIN_PINCODE_SAMPLE_SIZE: int = 15          # Minimum completed orders required within freshness window
    MIN_DISTINCT_CUSTOMERS: int = 15           # Minimum distinct customer identities required
    PINCODE_FRESHNESS_DAYS: int = 180          # Maximum historical lookback window in days
    SHRINKAGE_PRIOR_M0: int = 25               # Heuristic shrinkage prior strength
    MAX_UNCERTAINTY_THRESHOLD: Decimal = Decimal("0.7910")  # Reconciled threshold consistent with N >= 15

    # Bounds
    MIN_P_RTO: Decimal = Decimal("0.0100")
    MAX_P_RTO: Decimal = Decimal("0.9500")


def round_curr(val: Decimal) -> Decimal:
    """Rounds currency amounts to 2 decimal places using standard half-up rounding."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class DecisionEngineService:
    @staticmethod
    def calculate_base_delivered(
        order_value: Decimal,
        is_cod: bool,
        cogs: Decimal,
        fwd_shipping: Decimal,
        packaging: Decimal,
        cod_fee: Decimal,
        gateway_fee: Decimal,
    ) -> Decimal:
        """Payoff if parcel is accepted by customer upon delivery."""
        if is_cod:
            return round_curr(order_value - cod_fee - cogs - packaging - fwd_shipping)
        return round_curr(order_value - gateway_fee - cogs - packaging - fwd_shipping)

    @staticmethod
    def calculate_base_rto(
        order_value: Decimal,
        is_cod: bool,
        cogs: Decimal,
        fwd_shipping: Decimal,
        rev_shipping: Decimal,
        packaging: Decimal,
        damage_rate: Decimal,
        cod_fee: Decimal,
        cod_fee_incurred_on: str,
        gateway_fee: Decimal,
    ) -> Decimal:
        """Payoff if parcel is returned to warehouse (RTO)."""
        damage_loss = damage_rate * cogs
        if is_cod:
            cod_charged = cod_fee if cod_fee_incurred_on == "UPON_MANIFEST" else Decimal("0.00")
            return round_curr(- cod_charged - packaging - fwd_shipping - rev_shipping - damage_loss)
        # Prepaid RTO: order value is refunded in full, gateway fee is non-refundable
        return round_curr(- gateway_fee - packaging - fwd_shipping - rev_shipping - damage_loss)

    @staticmethod
    def calculate_profit_at_risk(
        order_value: Decimal,
        rev_shipping: Decimal,
        cogs: Decimal,
        damage_rate: Decimal,
        cod_fee: Decimal,
        cod_fee_incurred_on: str,
        is_cod: bool = True,
    ) -> Decimal:
        """Difference between delivered and RTO contribution under explicit accounting rules."""
        if is_cod:
            i_rto = Decimal("1.0") if cod_fee_incurred_on == "UPON_MANIFEST" else Decimal("0.0")
            recovered_inventory = (Decimal("1.0") - damage_rate) * cogs
            return round_curr(order_value + rev_shipping - (Decimal("1.0") - i_rto) * cod_fee - recovered_inventory)
        # For prepaid
        recovered_inventory = (Decimal("1.0") - damage_rate) * cogs
        return round_curr(order_value + rev_shipping - recovered_inventory)

    @staticmethod
    def estimate_order_risk(
        order: Order,
        economics: MerchantEconomics,
        session: Optional[Session] = None,
    ) -> Tuple[Decimal, Decimal, str, List[TriggeredRule], List[PolicyGuard], Dict[str, Any]]:
        """Transparent, rule-based baseline RTO probability and uncertainty estimation."""
        triggered_rules: List[TriggeredRule] = []
        policy_guards: List[PolicyGuard] = []

        is_cod = order.payment_method == "COD"
        order_val = order.order_value

        # Baseline prior (Operational Assumption)
        if is_cod:
            p_rto = DecisionAssumptions.PRIOR_RTO_COD
            triggered_rules.append(TriggeredRule(
                rule_name="PAYMENT_METHOD_COD",
                factor="COD Payment",
                risk_delta=f"+{DecisionAssumptions.PRIOR_RTO_COD}",
                description="Cash on Delivery orders carry inherent default non-acceptance risk.",
            ))
        else:
            p_rto = DecisionAssumptions.PRIOR_RTO_PREPAID
            triggered_rules.append(TriggeredRule(
                rule_name="PAYMENT_METHOD_PREPAID",
                factor="Prepaid Payment",
                risk_delta=f"+{DecisionAssumptions.PRIOR_RTO_PREPAID}",
                description="Prepaid orders have paid funds, drastically reducing RTO risk.",
            ))

        # Order Value Risk
        safety_cap = economics.safety_value_cap
        if order_val > safety_cap:
            p_rto += DecisionAssumptions.DELTA_HIGH_ORDER_VALUE
            triggered_rules.append(TriggeredRule(
                rule_name="HIGH_ORDER_VALUE_ABOVE_CAP",
                factor=f"Order Value ₹{order_val} > Cap ₹{safety_cap}",
                risk_delta=f"+{DecisionAssumptions.DELTA_HIGH_ORDER_VALUE}",
                description=f"High-ticket order exceeds merchant safety cap of ₹{safety_cap}.",
            ))
            policy_guards.append(PolicyGuard(
                guard_name="SAFETY_VALUE_CAP",
                passed=False,
                detail=f"Order value ₹{order_val} exceeds safety cap ₹{safety_cap}; mandatory verification required.",
            ))
        else:
            policy_guards.append(PolicyGuard(
                guard_name="SAFETY_VALUE_CAP",
                passed=True,
                detail=f"Order value ₹{order_val} is within safety threshold of ₹{safety_cap}.",
            ))

        # Address completeness & quality checks
        addr1 = order.shipping_address1 or ""
        addr2 = order.shipping_address2 or ""
        city = order.shipping_city or ""
        pincode = order.shipping_pincode or ""
        phone = order.customer_phone or ""

        if not addr2 or len(addr2.strip()) < 4:
            p_rto += DecisionAssumptions.DELTA_INCOMPLETE_ADDRESS
            triggered_rules.append(TriggeredRule(
                rule_name="INCOMPLETE_ADDRESS_LINE_2",
                factor="Missing Address Line 2",
                risk_delta=f"+{DecisionAssumptions.DELTA_INCOMPLETE_ADDRESS}",
                description="Missing apartment/locality landmarks correlates with courier delivery failure.",
            ))

        if not city or len(city.strip()) < 3:
            p_rto += DecisionAssumptions.DELTA_MISSING_CITY
            triggered_rules.append(TriggeredRule(
                rule_name="MISSING_CITY_NAME",
                factor="Missing City",
                risk_delta=f"+{DecisionAssumptions.DELTA_MISSING_CITY}",
                description="Courier routing depends on valid destination city name.",
            ))

        # Repetitive / dummy digits check in phone
        if phone:
            digits = "".join(filter(str.isdigit, phone))
            if len(set(digits)) <= 2:
                p_rto += DecisionAssumptions.DELTA_SUSPICIOUS_PHONE
                triggered_rules.append(TriggeredRule(
                    rule_name="SUSPICIOUS_PHONE_NUMBER",
                    factor="Low Digit Entropy",
                    risk_delta=f"+{DecisionAssumptions.DELTA_SUSPICIOUS_PHONE}",
                    description=f"Phone number '{phone}' has repeating digits suggesting dummy order entry.",
                ))

        # Pincode Safeguards & Uncertainty Calibration Protocol
        # U_j = sqrt(M_0 / (M_0 + N_j)), M_0 = 25
        # Safeguards:
        # 1. 180-day freshness window (stale historical orders are excluded)
        # 2. Minimum 15 completed orders within window
        # 3. Minimum 15 distinct customer identities (phone or email)
        # 4. Uncertainty threshold U_j <= 0.7910 (reconciled with N >= 15 for M_0 = 25)
        # NOTE: Pincode history currently controls cancellation eligibility only.
        # Raw historical RTO rates are NOT applied directly to baseline risk pending calibrated empirical smoothing.
        m_0 = DecisionAssumptions.SHRINKAGE_PRIOR_M0
        n_pincode = 0
        n_distinct_customers = 0

        if session and pincode and order.org_id:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=DecisionAssumptions.PINCODE_FRESHNESS_DAYS)

            # Distinguish customer identity via non-empty phone or email
            customer_ident = func.coalesce(
                func.nullif(Order.customer_phone, ""),
                func.nullif(Order.customer_email, "")
            )

            stats_q = (
                select(
                    func.count(Order.id).label("total_orders"),
                    func.count(func.distinct(customer_ident)).label("distinct_customers"),
                )
                .where(
                    Order.org_id == order.org_id,
                    Order.shipping_pincode == pincode,
                    Order.status.in_(["DELIVERED", "RTO"]),
                    Order.created_at >= cutoff_date,
                )
            )
            row = session.execute(stats_q).first()
            if row:
                n_pincode = row.total_orders or 0
                n_distinct_customers = row.distinct_customers or 0

        # Compute uncertainty heuristic score
        u_score = Decimal(str(math.sqrt(m_0 / (m_0 + n_pincode)))).quantize(Decimal("0.0001"))

        # Stationarity / Anti-cancellation gate evaluation
        can_auto_cancel_pincode = True
        prohibitions = []

        if n_pincode < DecisionAssumptions.MIN_PINCODE_SAMPLE_SIZE:
            can_auto_cancel_pincode = False
            prohibitions.append(
                f"Sample size {n_pincode} < {DecisionAssumptions.MIN_PINCODE_SAMPLE_SIZE} ({DecisionAssumptions.PINCODE_FRESHNESS_DAYS}-day window)"
            )

        if n_distinct_customers < DecisionAssumptions.MIN_DISTINCT_CUSTOMERS:
            can_auto_cancel_pincode = False
            prohibitions.append(
                f"Distinct customers {n_distinct_customers} < {DecisionAssumptions.MIN_DISTINCT_CUSTOMERS}"
            )

        if u_score > DecisionAssumptions.MAX_UNCERTAINTY_THRESHOLD:
            can_auto_cancel_pincode = False
            prohibitions.append(
                f"Uncertainty {u_score} > threshold {DecisionAssumptions.MAX_UNCERTAINTY_THRESHOLD}"
            )

        if not can_auto_cancel_pincode:
            policy_guards.append(PolicyGuard(
                guard_name="ANTI_CANCELLATION_GATE",
                passed=False,
                detail=(
                    f"Sparse or unrepresentative data for pincode {pincode} ({'; '.join(prohibitions)}). "
                    f"Automated cancellation prohibited."
                ),
            ))
        else:
            policy_guards.append(PolicyGuard(
                guard_name="ANTI_CANCELLATION_GATE",
                passed=True,
                detail=(
                    f"Sufficient empirical evidence for pincode {pincode} "
                    f"(N={n_pincode}, Distinct={n_distinct_customers}, Uncertainty={u_score} <= {DecisionAssumptions.MAX_UNCERTAINTY_THRESHOLD})."
                ),
            ))

        # Merchant policy auto-cancel flag
        if not economics.allow_auto_cancel:
            policy_guards.append(PolicyGuard(
                guard_name="MERCHANT_AUTO_CANCEL_POLICY",
                passed=False,
                detail="Merchant economics setting 'allow_auto_cancel' is False. Automatic cancellations disabled.",
            ))
        else:
            policy_guards.append(PolicyGuard(
                guard_name="MERCHANT_AUTO_CANCEL_POLICY",
                passed=True,
                detail="Merchant economics permits automated cancellation when expected contribution is negative.",
            ))

        # Clamp baseline P_rto to operational bounds [0.0100, 0.9500]
        p_rto = max(DecisionAssumptions.MIN_P_RTO, min(p_rto, DecisionAssumptions.MAX_P_RTO)).quantize(Decimal("0.0001"))

        # Risk Tier
        if p_rto < Decimal("0.1500"):
            risk_tier = "LOW"
        elif p_rto < Decimal("0.3500"):
            risk_tier = "MEDIUM"
        elif p_rto < Decimal("0.6000"):
            risk_tier = "HIGH"
        else:
            risk_tier = "CRITICAL"

        uncertainty_disclosure = {
            "pincode": pincode,
            "sample_size": n_pincode,
            "sample_size_n": n_pincode,
            "distinct_customers": n_distinct_customers,
            "distinct_customers_count": n_distinct_customers,
            "freshness_window_days": DecisionAssumptions.PINCODE_FRESHNESS_DAYS,
            "shrinkage_prior_m0": m_0,
            "uncertainty_score": str(u_score),
            "max_uncertainty_threshold": str(DecisionAssumptions.MAX_UNCERTAINTY_THRESHOLD),
            "qualification": (
                "Sample-size heuristic shrinkage proxy towards merchant aggregate prior. "
                "Pincode history controls cancellation policy eligibility only; raw historical "
                "RTO rates are not applied to baseline order risk."
            ),
            "can_auto_cancel": can_auto_cancel_pincode,
        }

        # Phase 2 & 4C: ML inference (supporting SHADOW, LIVE_ASSISTED, DISABLED modes)
        try:
            from app.services.ml_inference_service import ml_inference_service
            ml_pred = ml_inference_service.infer_order_risk(order, session)
        except Exception as exc:
            ml_pred = {
                "status": "RULE_BASED_FALLBACK",
                "operating_mode": "SHADOW",
                "is_shadow_mode": True,
                "is_approved_for_consequential_actions": False,
                "rto_probability": None,
                "predicted_risk_tier": None,
                "fallback_used": True,
                "reason": f"Safe fallback on ML inference: {exc}",
                "data_provenance": "RULE_BASED_ENGINE",
            }
        uncertainty_disclosure["shadow_ml_prediction"] = ml_pred
        uncertainty_disclosure["ml_inference_result"] = ml_pred

        return p_rto, u_score, risk_tier, triggered_rules, policy_guards, uncertainty_disclosure

    @classmethod
    def evaluate_order(
        cls,
        order: Order,
        economics: MerchantEconomics,
        session: Session,
        evaluated_by_user_id: Optional[UUID] = None,
        override_p_rto: Optional[Decimal] = None,  # For deterministic test fixture calibration
    ) -> OrderEvaluation:
        """Evaluates an order across all 5 candidate actions and persists the evaluation."""
        order_val = order.order_value
        is_cod = order.payment_method == "COD"

        # Determine COGS
        # If line items have unit costs, sum them; otherwise, use default COGS percent
        item_cogs = Decimal("0.00")
        has_item_costs = False
        if order.items:
            for item in order.items:
                if item.unit_cost is not None:
                    item_cogs += item.quantity * item.unit_cost
                    has_item_costs = True

        if has_item_costs and item_cogs > 0:
            cogs = round_curr(item_cogs)
        else:
            cogs = round_curr((economics.default_cogs_percent / Decimal("100.00")) * order_val)

        fwd_shipping = economics.forward_shipping_cost
        rev_shipping = economics.reverse_shipping_cost
        packaging = economics.packaging_cost
        cod_fee = economics.cod_carrier_fee
        cod_fee_incurred_on = economics.cod_fee_incurred_on
        damage_rate = economics.inventory_damage_rate

        gateway_percent = economics.payment_gateway_percent
        gateway_flat = economics.payment_gateway_flat
        gateway_fee = round_curr((gateway_percent / Decimal("100.00")) * order_val + gateway_flat)

        # Base Terminal Payoffs (Tier 1)
        del_payoff = cls.calculate_base_delivered(
            order_value=order_val,
            is_cod=is_cod,
            cogs=cogs,
            fwd_shipping=fwd_shipping,
            packaging=packaging,
            cod_fee=cod_fee,
            gateway_fee=gateway_fee,
        )

        rto_payoff = cls.calculate_base_rto(
            order_value=order_val,
            is_cod=is_cod,
            cogs=cogs,
            fwd_shipping=fwd_shipping,
            rev_shipping=rev_shipping,
            packaging=packaging,
            damage_rate=damage_rate,
            cod_fee=cod_fee,
            cod_fee_incurred_on=cod_fee_incurred_on,
            gateway_fee=gateway_fee,
        )

        cancel_payoff = Decimal("0.00")

        par = cls.calculate_profit_at_risk(
            order_value=order_val,
            rev_shipping=rev_shipping,
            cogs=cogs,
            damage_rate=damage_rate,
            cod_fee=cod_fee,
            cod_fee_incurred_on=cod_fee_incurred_on,
            is_cod=is_cod,
        )

        # Risk & Uncertainty Estimation
        p_rto, u_score, risk_tier, triggered_rules, policy_guards, uncertainty_disclosure = cls.estimate_order_risk(
            order=order,
            economics=economics,
            session=session,
        )

        if override_p_rto is not None:
            p_rto = override_p_rto

        # Intervention Unit Costs
        c_otp = economics.otp_verification_cost
        c_manual = economics.manual_review_cost
        d_prep = economics.prepaid_incentive_discount
        c_comm = economics.prepaid_comms_cost

        # ---------------------------------------------------------------------
        # Tier 2: Evaluate 5 Actions
        # ---------------------------------------------------------------------
        comparisons: List[ActionEvaluation] = []

        # 1. Action: SHIP_AS_IS
        p_del = Decimal("1.0") - p_rto
        ec_ship_as_is = round_curr(p_del * del_payoff + p_rto * rto_payoff)
        comparisons.append(ActionEvaluation(
            action="SHIP_AS_IS",
            expected_contribution=ec_ship_as_is,
            lift_vs_ship_as_is=Decimal("0.00"),
            intervention_cost=Decimal("0.00"),
            probabilities={
                "p_delivered": str(p_del),
                "p_rto": str(p_rto),
            },
            terminal_payoffs={
                "delivered": str(del_payoff),
                "rto": str(rto_payoff),
            },
            is_policy_eligible=True,
        ))

        # 2. Action: VERIFY_OTP
        # OTP verification rate P_conf; if confirmed, RTO drops by operational multiplier
        p_conf = DecisionAssumptions.OTP_CONFIRMATION_RATE
        p_rto_conf = (p_rto * DecisionAssumptions.OTP_RTO_RISK_MULTIPLIER).quantize(Decimal("0.0001"))
        p_del_conf = Decimal("1.0") - p_rto_conf
        branch_conf = p_del_conf * del_payoff + p_rto_conf * rto_payoff
        ec_otp = round_curr(p_conf * branch_conf + (Decimal("1.0") - p_conf) * cancel_payoff - c_otp)
        lift_otp = round_curr(ec_otp - ec_ship_as_is)

        comparisons.append(ActionEvaluation(
            action="VERIFY_OTP",
            expected_contribution=ec_otp,
            lift_vs_ship_as_is=lift_otp,
            intervention_cost=c_otp,
            probabilities={
                "p_customer_confirms": str(p_conf),
                "p_rto_if_confirmed": str(p_rto_conf),
            },
            terminal_payoffs={
                "branch_confirmed": str(round_curr(branch_conf)),
                "branch_unconfirmed": "0.00",
            },
            is_policy_eligible=True,
        ))

        # 3. Action: INCENTIVIZE_PREPAID
        # Only applicable to COD orders. For prepaid orders, it is disqualified.
        if is_cod:
            p_conv = DecisionAssumptions.PREPAID_CONVERSION_RATE
            p_rto_prep = DecisionAssumptions.PREPAID_CONVERTED_RTO
            v_prime = max(Decimal("1.00"), order_val - d_prep)
            f_pg_prime = round_curr((gateway_percent / Decimal("100.00")) * v_prime + gateway_flat)

            del_converted = v_prime - f_pg_prime - cogs - packaging - fwd_shipping
            rto_converted = - f_pg_prime - packaging - fwd_shipping - rev_shipping - (damage_rate * cogs)
            payoff_converted = (Decimal("1.0") - p_rto_prep) * del_converted + p_rto_prep * rto_converted

            ec_prep = round_curr(p_conv * payoff_converted + (Decimal("1.0") - p_conv) * ec_ship_as_is - c_comm)
            lift_prep = round_curr(ec_prep - ec_ship_as_is)

            comparisons.append(ActionEvaluation(
                action="INCENTIVIZE_PREPAID",
                expected_contribution=ec_prep,
                lift_vs_ship_as_is=lift_prep,
                intervention_cost=c_comm,
                probabilities={
                    "p_conversion_to_prepaid": str(p_conv),
                    "p_rto_if_converted": str(p_rto_prep),
                },
                terminal_payoffs={
                    "delivered_converted": str(round_curr(del_converted)),
                    "rto_converted": str(round_curr(rto_converted)),
                },
                is_policy_eligible=True,
            ))
        else:
            comparisons.append(ActionEvaluation(
                action="INCENTIVIZE_PREPAID",
                expected_contribution=ec_ship_as_is,
                lift_vs_ship_as_is=Decimal("0.00"),
                intervention_cost=Decimal("0.00"),
                is_policy_eligible=False,
                disqualification_reason="Order is already prepaid; prepaid incentive action is inapplicable.",
            ))

        # 4. Action: MANUAL_REVIEW
        p_appr = DecisionAssumptions.MANUAL_REVIEW_APPROVAL_RATE
        p_rto_appr = (p_rto * DecisionAssumptions.MANUAL_REVIEW_RTO_MULTIPLIER).quantize(Decimal("0.0001"))
        p_del_appr = Decimal("1.0") - p_rto_appr
        branch_appr = p_del_appr * del_payoff + p_rto_appr * rto_payoff
        ec_manual = round_curr(p_appr * branch_appr + (Decimal("1.0") - p_appr) * cancel_payoff - c_manual)
        lift_manual = round_curr(ec_manual - ec_ship_as_is)

        comparisons.append(ActionEvaluation(
            action="MANUAL_REVIEW",
            expected_contribution=ec_manual,
            lift_vs_ship_as_is=lift_manual,
            intervention_cost=c_manual,
            probabilities={
                "p_agent_approves": str(p_appr),
                "p_rto_if_approved": str(p_rto_appr),
            },
            terminal_payoffs={
                "branch_approved": str(round_curr(branch_appr)),
                "branch_rejected": "0.00",
            },
            is_policy_eligible=True,
        ))

        # 5. Action: HOLD_CANCEL
        # Payoff is 0.00.
        ec_cancel = Decimal("0.00")
        lift_cancel = round_curr(ec_cancel - ec_ship_as_is)

        # Policy Gate for HOLD_CANCEL
        # Can only be recommended if allow_auto_cancel is True AND ec_ship_as_is < 0 AND anti-cancellation gate passed
        auto_cancel_allowed = economics.allow_auto_cancel and uncertainty_disclosure["can_auto_cancel"]
        cancel_disqualification = None
        if not economics.allow_auto_cancel:
            cancel_disqualification = "Merchant setting 'allow_auto_cancel' is False."
        elif not uncertainty_disclosure["can_auto_cancel"]:
            cancel_disqualification = f"Sparse or high-uncertainty data (U={u_score}). Cancellation requires manual verification."
        elif ec_ship_as_is >= 0:
            cancel_disqualification = f"Normal shipping has positive expected contribution (+₹{ec_ship_as_is}). Cancellation would sacrifice profit."

        comparisons.append(ActionEvaluation(
            action="HOLD_CANCEL",
            expected_contribution=ec_cancel,
            lift_vs_ship_as_is=lift_cancel,
            intervention_cost=Decimal("0.00"),
            probabilities={"p_cancelled": "1.00"},
            terminal_payoffs={"cancelled": "0.00"},
            is_policy_eligible=(cancel_disqualification is None),
            disqualification_reason=cancel_disqualification,
        ))

        # ---------------------------------------------------------------------
        # Optimal Recommendation Selection
        # ---------------------------------------------------------------------
        # Filter eligible actions
        eligible_actions = [a for a in comparisons if a.is_policy_eligible]

        # Policy Safety Guard: If Order Value > Safety Value Cap, cannot SHIP_AS_IS without verification
        if order_val > economics.safety_value_cap:
            for a in eligible_actions:
                if a.action == "SHIP_AS_IS":
                    a.is_policy_eligible = False
                    a.disqualification_reason = f"Order value ₹{order_val} exceeds safety cap ₹{economics.safety_value_cap}. Mandatory verification required."
            eligible_actions = [a for a in eligible_actions if a.is_policy_eligible]

        # Sort eligible actions by expected contribution descending
        eligible_actions.sort(key=lambda a: a.expected_contribution, reverse=True)

        if not eligible_actions:
            # Fallback to MANUAL_REVIEW if all disqualified
            recommended = [a for a in comparisons if a.action == "MANUAL_REVIEW"][0]
        else:
            recommended = eligible_actions[0]

        rec_deterministic = recommended.action

        # ---------------------------------------------------------------------
        # Phase 4C: ML-Assisted Decisioning & Operating Mode Policy
        # ---------------------------------------------------------------------
        ml_pred = uncertainty_disclosure.get("ml_inference_result")
        ml_mode = (ml_pred.get("operating_mode") if ml_pred else None) or getattr(settings, "ML_OPERATING_MODE", "SHADOW")
        ml_mode = ml_mode.upper()
        ml_status = ml_pred.get("status") if ml_pred else "RULE_BASED_FALLBACK"
        ml_p_rto = ml_pred.get("rto_probability") if ml_pred else None
        is_approved_consequential = bool(ml_pred.get("is_approved_for_consequential_actions", False)) if ml_pred else False

        rec_ml_assisted = None
        if ml_status == "ML_PREDICTION" and ml_p_rto is not None:
            p_ml = max(DecisionAssumptions.MIN_P_RTO, min(Decimal(str(ml_p_rto)), DecisionAssumptions.MAX_P_RTO))

            # Expected Contributions under ML Risk
            ec_ml_ship_as_is = round_curr((Decimal("1.0") - p_ml) * del_payoff + p_ml * rto_payoff)

            p_rto_conf_ml = (p_ml * DecisionAssumptions.OTP_RTO_RISK_MULTIPLIER).quantize(Decimal("0.0001"))
            branch_conf_ml = (Decimal("1.0") - p_rto_conf_ml) * del_payoff + p_rto_conf_ml * rto_payoff
            ec_ml_otp = round_curr(p_conf * branch_conf_ml + (Decimal("1.0") - p_conf) * cancel_payoff - c_otp)

            if is_cod:
                p_conv = DecisionAssumptions.PREPAID_CONVERSION_RATE
                p_rto_prep = DecisionAssumptions.PREPAID_CONVERTED_RTO
                payoff_conv_ml = (Decimal("1.0") - p_rto_prep) * del_converted + p_rto_prep * rto_converted
                ec_ml_prep = round_curr(p_conv * payoff_conv_ml + (Decimal("1.0") - p_conv) * ec_ml_ship_as_is - c_comm)
            else:
                ec_ml_prep = ec_ml_ship_as_is

            p_rto_appr_ml = (p_ml * DecisionAssumptions.MANUAL_REVIEW_RTO_MULTIPLIER).quantize(Decimal("0.0001"))
            branch_appr_ml = (Decimal("1.0") - p_rto_appr_ml) * del_payoff + p_rto_appr_ml * rto_payoff
            ec_ml_manual = round_curr(p_appr * branch_appr_ml + (Decimal("1.0") - p_appr) * cancel_payoff - c_manual)

            # HOLD_CANCEL eligibility under ML
            can_cancel_ml = False
            cancel_ml_disq = None
            if not is_approved_consequential:
                cancel_ml_disq = (
                    "Model-readiness gate: synthetic-trained model is not approved for consequential "
                    "actions (HOLD_CANCEL). Manual review or verification required."
                )
            elif not economics.allow_auto_cancel:
                cancel_ml_disq = "Merchant setting 'allow_auto_cancel' is False."
            elif not uncertainty_disclosure.get("can_auto_cancel", False):
                cancel_ml_disq = f"Sparse or high-uncertainty data (U={u_score}). Cancellation requires manual verification."
            elif ec_ml_ship_as_is >= Decimal("0.00"):
                cancel_ml_disq = f"Normal fulfillment has positive expected contribution (+₹{ec_ml_ship_as_is})."
            else:
                can_cancel_ml = True

            ml_candidates = [
                {"action": "SHIP_AS_IS", "ec": ec_ml_ship_as_is, "eligible": True, "disqualification": None},
                {"action": "VERIFY_OTP", "ec": ec_ml_otp, "eligible": is_cod, "disqualification": "Prepaid order" if not is_cod else None},
                {"action": "INCENTIVIZE_PREPAID", "ec": ec_ml_prep, "eligible": is_cod, "disqualification": "Prepaid order" if not is_cod else None},
                {"action": "MANUAL_REVIEW", "ec": ec_ml_manual, "eligible": True, "disqualification": None},
                {"action": "HOLD_CANCEL", "ec": Decimal("0.00"), "eligible": can_cancel_ml, "disqualification": cancel_ml_disq},
            ]

            # Apply Safety Value Cap to ML candidates
            if order_val > economics.safety_value_cap:
                for cand in ml_candidates:
                    if cand["action"] == "SHIP_AS_IS":
                        cand["eligible"] = False
                        cand["disqualification"] = f"Order value ₹{order_val} exceeds safety cap ₹{economics.safety_value_cap}."

            ml_eligible = [c for c in ml_candidates if c["eligible"]]
            ml_eligible.sort(key=lambda c: c["ec"], reverse=True)
            rec_ml_assisted = ml_eligible[0]["action"] if ml_eligible else "MANUAL_REVIEW"

        # Operating Mode Policy Resolution
        policy_version = getattr(settings, "ML_DECISION_POLICY_VERSION", "v1.1-ml-assisted")
        if ml_mode == "DISABLED":
            final_recommendation = rec_deterministic
            ml_decision_rationale = "ML inference is disabled by configuration. Authoritative deterministic recommendation enforced."
        elif ml_mode == "SHADOW":
            final_recommendation = rec_deterministic
            if rec_ml_assisted is not None:
                if rec_ml_assisted == rec_deterministic:
                    ml_decision_rationale = (
                        f"Shadow mode active: ML recommendation matches deterministic ({rec_deterministic}) "
                        f"at P(RTO)={ml_p_rto:.4f}. Deterministic recommendation enforced without modification."
                    )
                else:
                    ml_decision_rationale = (
                        f"Shadow mode active: ML suggested {rec_ml_assisted} (P(RTO)={ml_p_rto:.4f}, "
                        f"Tier={ml_pred.get('predicted_risk_tier')}), but authoritative deterministic "
                        f"recommendation {rec_deterministic} is strictly enforced."
                    )
            else:
                ml_decision_rationale = (
                    f"Shadow mode active: ML inference returned {ml_status} "
                    f"({ml_pred.get('reason') if ml_pred else 'N/A'}). Deterministic recommendation {rec_deterministic} enforced."
                )
        elif ml_mode == "LIVE_ASSISTED":
            if rec_ml_assisted is not None:
                final_recommendation = rec_ml_assisted
                if rec_ml_assisted == rec_deterministic:
                    ml_decision_rationale = (
                        f"Live-assisted mode: ML prediction (P(RTO)={ml_p_rto:.4f}, "
                        f"Tier={ml_pred.get('predicted_risk_tier')}) confirms deterministic recommendation ({final_recommendation})."
                    )
                else:
                    ml_decision_rationale = (
                        f"Live-assisted mode override: Deterministic policy suggested {rec_deterministic}, "
                        f"but ML risk prediction (P(RTO)={ml_p_rto:.4f}, Tier={ml_pred.get('predicted_risk_tier')}) "
                        f"elevated recommendation to {final_recommendation} to optimize risk-adjusted contribution "
                        f"(readiness gate enforced: autonomous cancellation blocked)."
                    )
            else:
                final_recommendation = rec_deterministic
                ml_decision_rationale = (
                    f"Live-assisted mode fallback: ML inference returned {ml_status} "
                    f"({ml_pred.get('reason') if ml_pred else 'N/A'}). Safe fallback to deterministic recommendation {rec_deterministic}."
                )
        else:
            final_recommendation = rec_deterministic
            ml_decision_rationale = f"Unknown operating mode '{ml_mode}'. Fallback to deterministic recommendation {rec_deterministic}."

        # Mark recommended action on comparison evaluations
        for a in comparisons:
            a.is_recommended = (a.action == final_recommendation)

        chosen_action_eval = next((a for a in comparisons if a.action == final_recommendation), recommended)
        best_ec = chosen_action_eval.expected_contribution
        rec_lift = chosen_action_eval.lift_vs_ship_as_is

        # Formulate Explanation
        if final_recommendation != rec_deterministic:
            primary_reason = (
                f"ML-assisted policy recommended {final_recommendation} "
                f"(expected contribution: +₹{best_ec}, lift: +₹{rec_lift}): {ml_decision_rationale}"
            )
        elif final_recommendation == "SHIP_AS_IS":
            primary_reason = (
                f"Normal fulfillment provides the highest expected contribution (+₹{best_ec}). "
                f"Pre-dispatch interventions do not yield positive incremental profit."
            )
        elif final_recommendation == "VERIFY_OTP":
            primary_reason = (
                f"Automated OTP verification yields an expected contribution of +₹{best_ec} "
                f"(+₹{rec_lift} lift over standard shipping), filtering out unconfirmed COD orders."
            )
        elif final_recommendation == "INCENTIVIZE_PREPAID":
            primary_reason = (
                f"Prepaid conversion incentive yields an expected contribution of +₹{best_ec} "
                f"(+₹{rec_lift} lift over standard shipping), converting high-risk COD into locked prepaid revenue."
            )
        elif final_recommendation == "MANUAL_REVIEW":
            primary_reason = (
                f"Manual customer verification provides the optimal risk-adjusted contribution of +₹{best_ec} "
                f"(+₹{rec_lift} lift over standard shipping) for this high-value or elevated-risk order."
            )
        elif final_recommendation == "HOLD_CANCEL":
            primary_reason = (
                f"Order expected contribution under normal shipping is negative (₹{ec_ship_as_is}). "
                f"Cancelling avoids an expected loss of ₹{abs(ec_ship_as_is)} under merchant policy."
            )
        else:
            primary_reason = f"Action {final_recommendation} optimizes expected contribution."

        uncertainty_disclosure["ml_decision_metadata"] = {
            "deterministic_recommendation": rec_deterministic,
            "ml_assisted_recommendation": rec_ml_assisted,
            "final_recommendation": final_recommendation,
            "ml_operating_mode": ml_mode,
            "decision_policy_version": policy_version,
            "ml_decision_rationale": ml_decision_rationale,
            "is_approved_for_consequential_actions": is_approved_consequential,
        }

        explanation = DecisionExplanation(
            primary_reason=primary_reason,
            triggered_rules=triggered_rules,
            policy_guards=policy_guards,
            uncertainty_disclosure=uncertainty_disclosure,
            financial_assumptions={
                "cogs_amount": str(cogs),
                "forward_shipping": str(fwd_shipping),
                "reverse_shipping": str(rev_shipping),
                "packaging": str(packaging),
                "cod_fee": str(cod_fee),
                "cod_fee_incurred_on": cod_fee_incurred_on,
                "gateway_fee": str(gateway_fee),
                "damage_rate": str(damage_rate),
                "tax_accounting_mode": economics.tax_accounting_mode,
            },
            operational_probability_assumptions={
                "otp_confirmation_rate": str(DecisionAssumptions.OTP_CONFIRMATION_RATE),
                "otp_residual_rto_multiplier": str(DecisionAssumptions.OTP_RTO_RISK_MULTIPLIER),
                "prepaid_conversion_rate": str(DecisionAssumptions.PREPAID_CONVERSION_RATE),
                "prepaid_converted_rto": str(DecisionAssumptions.PREPAID_CONVERTED_RTO),
                "manual_review_approval_rate": str(DecisionAssumptions.MANUAL_REVIEW_APPROVAL_RATE),
                "manual_review_residual_rto_multiplier": str(round(Decimal(str(DecisionAssumptions.MANUAL_REVIEW_RTO_MULTIPLIER)), 4)),
                "disclosure": "These parameters are operational baseline assumptions, not trained ML predictions.",
            },
        )

        # Build and persist OrderEvaluation
        order_evaluation = OrderEvaluation(
            org_id=order.org_id,
            order_id=order.id,
            evaluated_at=datetime.now(timezone.utc),
            evaluated_by_user_id=evaluated_by_user_id,
            recommended_action=final_recommendation,
            recommended_action_deterministic=rec_deterministic,
            recommended_action_ml_assisted=rec_ml_assisted,
            decision_policy_version=policy_version,
            ml_operating_mode=ml_mode,
            ml_decision_rationale=ml_decision_rationale,
            recommended_lift=rec_lift,
            ship_as_is_ec=ec_ship_as_is,
            best_ec=best_ec,
            profit_at_risk=par,
            baseline_p_rto=p_rto,
            uncertainty_score=u_score,
            risk_tier=risk_tier,
            comparison_data=[a.model_dump(mode="json") for a in comparisons],
            explanation_data=explanation.model_dump(mode="json"),
            decision_status="EVALUATED",
            intervention_status="NONE",
        )
        session.add(order_evaluation)
        session.flush()

        AuditService.record_event(
            session=session,
            org_id=order.org_id,
            actor_user_id=evaluated_by_user_id,
            action="ORDER_EVALUATED",
            resource_type="OrderEvaluation",
            resource_id=str(order_evaluation.id),
            payload={
                "order_id": str(order.id),
                "external_order_id": order.external_order_id,
                "recommended_action": final_recommendation,
                "recommended_action_deterministic": rec_deterministic,
                "recommended_action_ml_assisted": rec_ml_assisted,
                "ml_operating_mode": ml_mode,
                "decision_policy_version": policy_version,
                "lift": str(rec_lift),
                "best_ec": str(best_ec),
                "risk_tier": risk_tier,
            },
        )

        session.commit()
        session.refresh(order_evaluation)
        return order_evaluation

    @staticmethod
    def get_latest_evaluation(
        order_id: UUID,
        org_id: UUID,
        session: Session,
    ) -> OrderEvaluation:
        """Retrieves the latest evaluation for an order, enforcing tenant isolation."""
        evaluation = session.scalar(
            select(OrderEvaluation)
            .where(
                OrderEvaluation.order_id == order_id,
                OrderEvaluation.org_id == org_id,
            )
            .order_by(OrderEvaluation.created_at.desc())
        )
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No decision evaluation found for this order. Run evaluate first.",
            )
        return evaluation

    @staticmethod
    def record_decision(
        order_id: UUID,
        org_id: UUID,
        user_id: UUID,
        action: str,
        override_reason: Optional[str],
        session: Session,
    ) -> OrderEvaluation:
        """Records an authorized decision (acceptance or override) and transitions order state."""
        # Check order exists
        order = session.scalar(select(Order).where(Order.id == order_id, Order.org_id == org_id))
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found or unauthorized.")

        # Get latest evaluation or auto-evaluate if not evaluated yet
        evaluation = session.scalar(
            select(OrderEvaluation)
            .where(OrderEvaluation.order_id == order_id, OrderEvaluation.org_id == org_id)
            .order_by(OrderEvaluation.created_at.desc())
        )
        if not evaluation:
            economics = session.scalar(select(MerchantEconomics).where(MerchantEconomics.org_id == org_id))
            if not economics:
                economics = MerchantEconomics(org_id=org_id)
                session.add(economics)
                session.flush()
            evaluation = DecisionEngineService.evaluate_order(
                order=order,
                economics=economics,
                session=session,
                evaluated_by_user_id=user_id,
            )

        is_override = action != evaluation.recommended_action
        if is_override and not override_reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Overriding recommendation '{evaluation.recommended_action}' with '{action}' requires an override_reason.",
            )

        evaluation.selected_action = action
        evaluation.decision_status = "OVERRIDDEN" if is_override else "ACCEPTED"
        evaluation.override_reason = override_reason
        evaluation.decided_at = datetime.now(timezone.utc)
        evaluation.decided_by_user_id = user_id

        # Transition order state based on decision
        if action == "HOLD_CANCEL":
            order.status = "CANCELLED"
            order.fulfillment_status = "HOLD"
        elif action == "SHIP_AS_IS":
            order.status = "CONFIRMED"
        elif action in {"VERIFY_OTP", "INCENTIVIZE_PREPAID", "MANUAL_REVIEW"}:
            evaluation.intervention_status = "PENDING"
            order.status = "HOLD"

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=user_id,
            action="DECISION_RECORDED",
            resource_type="OrderEvaluation",
            resource_id=str(evaluation.id),
            payload={
                "order_id": str(order_id),
                "selected_action": action,
                "recommended_action": evaluation.recommended_action,
                "is_override": is_override,
                "override_reason": override_reason,
            },
        )

        session.commit()
        session.refresh(evaluation)
        return evaluation

    @staticmethod
    def record_intervention_outcome(
        order_id: UUID,
        org_id: UUID,
        user_id: UUID,
        outcome: str,
        notes: Optional[str],
        session: Session,
    ) -> OrderEvaluation:
        """Records terminal outcome of a pre-dispatch intervention."""
        order = session.scalar(select(Order).where(Order.id == order_id, Order.org_id == org_id))
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found or unauthorized.")

        evaluation = session.scalar(
            select(OrderEvaluation)
            .where(OrderEvaluation.order_id == order_id, OrderEvaluation.org_id == org_id)
            .order_by(OrderEvaluation.created_at.desc())
        )
        if not evaluation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order evaluation not found.")

        evaluation.intervention_status = outcome
        evaluation.intervention_notes = notes
        evaluation.intervention_resolved_at = datetime.now(timezone.utc)

        # Update order status based on intervention outcome
        if outcome in {"OTP_VERIFIED", "MANUAL_APPROVED"}:
            order.status = "CONFIRMED"
        elif outcome in {"OTP_FAILED", "MANUAL_REJECTED"}:
            order.status = "CANCELLED"
            order.fulfillment_status = "HOLD"
        elif outcome == "PREPAID_CONVERTED":
            order.payment_method = "PREPAID"
            order.status = "CONFIRMED"
        elif outcome == "PREPAID_DECLINED":
            order.status = "CONFIRMED"  # proceeds as normal COD

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=user_id,
            action="INTERVENTION_OUTCOME_RECORDED",
            resource_type="OrderEvaluation",
            resource_id=str(evaluation.id),
            payload={
                "order_id": str(order_id),
                "outcome": outcome,
                "notes": notes,
                "order_status": order.status,
            },
        )

        session.commit()
        session.refresh(evaluation)
        return evaluation
