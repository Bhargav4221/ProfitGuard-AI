"""Real-Order Outcome Tracking and Monitoring Service.

Provides:
1. Idempotent recording of terminal order outcomes linked with predictions and financial reconciliations.
2. Tenant-scoped authorization and isolation.
3. Prediction-time feature temporal integrity (no post-order leakage fields).
4. Comprehensive monitoring metrics separating observed empirical facts from modeled counterfactual estimates.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.delivery import DeliveryEvent
from app.models.financial_reconciliation import OrderFinancialReconciliation
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.order_outcome import OrderOutcome
from app.schemas.outcome import (
    ClassificationMetrics,
    ModeledExAnteEstimates,
    ObservedRealizedFacts,
    OrderOutcomeOut,
    OutcomeMonitoringMetricsOut,
)
from app.services.audit_service import AuditService
from app.services.reconciliation_service import ReconciliationService


TERMINAL_OUTCOMES = {"DELIVERED", "RTO", "CANCELLED"}


class OutcomeTrackingService:

    @staticmethod
    def record_order_outcome(
        org_id: UUID,
        order_id: UUID,
        session: Session,
        actor_user_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> OrderOutcome:
        """Idempotently records terminal order outcomes, linking predictions and financial reconciliations."""
        # 1. Enforce tenant isolation & verify order exists
        order = session.scalar(
            select(Order).where(Order.id == order_id, Order.org_id == org_id)
        )
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found or unauthorized.",
            )

        # 2. Transition & Terminal Outcome Verification
        if order.status not in TERMINAL_OUTCOMES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Order '{order.external_order_id}' is in non-terminal status '{order.status}'. "
                    f"Outcome tracking requires a terminal delivery status ({sorted(list(TERMINAL_OUTCOMES))})."
                ),
            )

        # 3. Ensure financial reconciliation exists
        recon = session.scalar(
            select(OrderFinancialReconciliation).where(
                OrderFinancialReconciliation.org_id == org_id,
                OrderFinancialReconciliation.order_id == order_id,
            )
        )
        if not recon:
            recon = ReconciliationService.reconcile_order(
                org_id=org_id,
                order_id=order_id,
                session=session,
                actor_user_id=actor_user_id,
            )

        # 4. Extract Prediction-Time Evaluation (Excluding Post-Order Information)
        latest_eval = session.scalar(
            select(OrderEvaluation)
            .where(OrderEvaluation.org_id == org_id, OrderEvaluation.order_id == order_id)
            .order_by(OrderEvaluation.created_at.desc())
        )

        model_version = None
        feature_contract_version = None
        prediction_timestamp = None
        prediction_feature_ref = None
        prediction_features_snapshot = None
        predicted_p_rto = None
        predicted_risk_tier = None
        deterministic_recommendation = "SHIP_AS_IS"
        ml_assisted_recommendation = None
        final_recommendation = "SHIP_AS_IS"
        ml_operating_mode = "SHADOW"
        decision_policy_version = "v1.1-ml-assisted"
        merchant_approved_action = None
        intervention_status = "NONE"

        if latest_eval:
            deterministic_recommendation = getattr(latest_eval, "recommended_action_deterministic", None) or latest_eval.recommended_action
            ml_assisted_recommendation = getattr(latest_eval, "recommended_action_ml_assisted", None)
            final_recommendation = latest_eval.recommended_action
            ml_operating_mode = getattr(latest_eval, "ml_operating_mode", None) or "SHADOW"
            decision_policy_version = getattr(latest_eval, "decision_policy_version", None) or "v1.1-ml-assisted"
            merchant_approved_action = latest_eval.selected_action
            intervention_status = latest_eval.intervention_status or "NONE"
            prediction_timestamp = latest_eval.evaluated_at
            predicted_risk_tier = latest_eval.risk_tier
            predicted_p_rto = latest_eval.baseline_p_rto

            # Extract shadow ML prediction metadata if present
            expl_data = latest_eval.explanation_data or {}
            uncertainty_info = expl_data.get("uncertainty_disclosure", {})
            shadow_ml = uncertainty_info.get("shadow_ml_prediction", {})
            if isinstance(shadow_ml, dict) and shadow_ml.get("status") == "ML_PREDICTION":
                model_version = shadow_ml.get("model_version")
                feature_contract_version = shadow_ml.get("feature_contract_version")
                if shadow_ml.get("rto_probability") is not None:
                    predicted_p_rto = Decimal(str(round(float(shadow_ml["rto_probability"]), 4)))

            # Build prediction-time features snapshot strictly from order placement information
            order_val = float(order.order_value)
            raw_order_features = {
                "order_value": order_val,
                "payment_method": order.payment_method,
                "shipping_pincode": order.shipping_pincode,
                "shipping_city": order.shipping_city,
                "shipping_state": order.shipping_state,
                "source_channel": order.source_channel,
                "item_count": len(order.items) if order.items else 1,
            }
            prediction_features_snapshot = raw_order_features
            feature_bytes = json.dumps(raw_order_features, sort_keys=True).encode("utf-8")
            prediction_feature_ref = f"feat-{hashlib.sha256(feature_bytes).hexdigest()[:16]}"

        # 5. Extract Terminal Logistics Details
        carrier_name = order.courier_name
        tracking_number = order.tracking_number
        delivered_at = None
        rto_reason_code = None
        rto_reason_description = None

        terminal_event = session.scalar(
            select(DeliveryEvent)
            .where(
                DeliveryEvent.org_id == org_id,
                DeliveryEvent.order_id == order_id,
                DeliveryEvent.new_status == order.status,
            )
            .order_by(DeliveryEvent.occurred_at.desc())
        )
        if terminal_event:
            delivered_at = terminal_event.occurred_at
            carrier_name = terminal_event.carrier_name or carrier_name
            tracking_number = terminal_event.tracking_number or tracking_number
            rto_reason_code = terminal_event.reason_code
            rto_reason_description = terminal_event.reason_description

        # 6. Realized Financial Values from Authoritative Reconciliation Ledger
        realized_order_val = recon.order_value
        realized_revenue = recon.collected_revenue
        realized_cogs = recon.cogs
        realized_shipping = recon.forward_shipping_cost + recon.reverse_shipping_cost
        realized_damage = recon.inventory_damage_cost
        intervention_cost = recon.pre_dispatch_intervention_cost + recon.ndr_recovery_intervention_cost
        realized_contribution = recon.realized_contribution
        expected_contribution = recon.expected_contribution
        variance_ec_vs_rc = recon.variance_ec_vs_rc

        realized_rto_loss = Decimal("0.00")
        if order.status == "RTO":
            realized_rto_loss = (
                recon.forward_shipping_cost
                + recon.reverse_shipping_cost
                + recon.packaging_cost
                + recon.inventory_damage_cost
            )

        # 7. Idempotent Upsert
        existing_outcome = session.scalar(
            select(OrderOutcome).where(
                OrderOutcome.org_id == org_id,
                OrderOutcome.order_id == order_id,
            )
        )

        now = datetime.now(timezone.utc)
        if existing_outcome:
            # Update existing outcome record with latest terminal accounting
            existing_outcome.final_delivery_outcome = order.status
            existing_outcome.reconciliation_id = recon.id
            existing_outcome.carrier_name = carrier_name
            existing_outcome.tracking_number = tracking_number
            existing_outcome.delivered_at = delivered_at or existing_outcome.delivered_at
            existing_outcome.rto_reason_code = rto_reason_code or existing_outcome.rto_reason_code
            existing_outcome.rto_reason_description = rto_reason_description or existing_outcome.rto_reason_description
            existing_outcome.realized_order_value = realized_order_val
            existing_outcome.realized_collected_revenue = realized_revenue
            existing_outcome.realized_cogs = realized_cogs
            existing_outcome.realized_shipping_cost = realized_shipping
            existing_outcome.realized_damage_cost = realized_damage
            existing_outcome.realized_rto_loss = realized_rto_loss
            existing_outcome.realized_contribution = realized_contribution
            existing_outcome.expected_contribution = expected_contribution
            existing_outcome.variance_ec_vs_rc = variance_ec_vs_rc
            existing_outcome.intervention_cost = intervention_cost
            existing_outcome.deterministic_recommendation = deterministic_recommendation
            existing_outcome.ml_assisted_recommendation = ml_assisted_recommendation
            existing_outcome.final_recommendation = final_recommendation
            existing_outcome.ml_operating_mode = ml_operating_mode
            existing_outcome.decision_policy_version = decision_policy_version
            if notes:
                existing_outcome.notes = notes
            outcome_record = existing_outcome
        else:
            outcome_record = OrderOutcome(
                org_id=org_id,
                order_id=order_id,
                external_order_id=order.external_order_id,
                evaluation_id=latest_eval.id if latest_eval else None,
                reconciliation_id=recon.id,
                model_version=model_version,
                feature_contract_version=feature_contract_version,
                prediction_timestamp=prediction_timestamp,
                prediction_feature_ref=prediction_feature_ref,
                prediction_features_snapshot=prediction_features_snapshot,
                predicted_p_rto=predicted_p_rto,
                predicted_risk_tier=predicted_risk_tier,
                deterministic_recommendation=deterministic_recommendation,
                ml_assisted_recommendation=ml_assisted_recommendation,
                final_recommendation=final_recommendation,
                ml_operating_mode=ml_operating_mode,
                decision_policy_version=decision_policy_version,
                merchant_approved_action=merchant_approved_action,
                intervention_status=intervention_status,
                intervention_cost=intervention_cost,
                final_delivery_outcome=order.status,
                carrier_name=carrier_name,
                tracking_number=tracking_number,
                delivered_at=delivered_at,
                rto_reason_code=rto_reason_code,
                rto_reason_description=rto_reason_description,
                realized_order_value=realized_order_val,
                realized_collected_revenue=realized_revenue,
                realized_cogs=realized_cogs,
                realized_shipping_cost=realized_shipping,
                realized_damage_cost=realized_damage,
                realized_rto_loss=realized_rto_loss,
                realized_contribution=realized_contribution,
                expected_contribution=expected_contribution,
                variance_ec_vs_rc=variance_ec_vs_rc,
                recorded_at=now,
                recorded_by_user_id=actor_user_id,
                notes=notes,
            )
            session.add(outcome_record)

        session.flush()

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="ORDER_OUTCOME_RECORDED",
            resource_type="OrderOutcome",
            resource_id=str(outcome_record.id),
            payload={
                "order_id": str(order.id),
                "external_order_id": order.external_order_id,
                "final_delivery_outcome": order.status,
                "model_version": model_version,
                "realized_contribution": str(realized_contribution),
                "realized_rto_loss": str(realized_rto_loss),
            },
        )

        session.commit()
        session.refresh(outcome_record)
        return outcome_record

    @staticmethod
    def get_order_outcome(org_id: UUID, order_id: UUID, session: Session) -> OrderOutcome:
        """Retrieves outcome record for a specific order."""
        outcome = session.scalar(
            select(OrderOutcome).where(
                OrderOutcome.org_id == org_id,
                OrderOutcome.order_id == order_id,
            )
        )
        if not outcome:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outcome record not found for this order.",
            )
        return outcome

    @staticmethod
    def list_order_outcomes(
        org_id: UUID,
        session: Session,
        final_delivery_outcome: Optional[str] = None,
        model_version: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[OrderOutcome], int]:
        """Lists outcomes for tenant with multi-criteria filtering and pagination."""
        query = select(OrderOutcome).where(OrderOutcome.org_id == org_id)

        if final_delivery_outcome:
            query = query.where(OrderOutcome.final_delivery_outcome == final_delivery_outcome.upper())
        if model_version:
            query = query.where(OrderOutcome.model_version == model_version)
        if date_from:
            query = query.where(OrderOutcome.recorded_at >= date_from)
        if date_to:
            query = query.where(OrderOutcome.recorded_at <= date_to)

        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = session.scalars(
            query.order_by(OrderOutcome.recorded_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), total

    @staticmethod
    def get_monitoring_metrics(
        org_id: UUID,
        session: Session,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        operating_threshold: float = 0.18,
    ) -> OutcomeMonitoringMetricsOut:
        """Computes comprehensive closed-loop monitoring metrics separating observed facts from modeled estimates."""
        # 1. Base Query for Eligible Completed Orders
        completed_orders_q = select(func.count(Order.id)).where(
            Order.org_id == org_id,
            Order.status.in_(["DELIVERED", "RTO", "CANCELLED"]),
        )
        if date_from:
            completed_orders_q = completed_orders_q.where(Order.created_at >= date_from)
        if date_to:
            completed_orders_q = completed_orders_q.where(Order.created_at <= date_to)
        eligible_completed_count = session.scalar(completed_orders_q) or 0

        # 2. Query for Recorded Outcomes
        outcomes_q = select(OrderOutcome).where(OrderOutcome.org_id == org_id)
        if date_from:
            outcomes_q = outcomes_q.where(OrderOutcome.recorded_at >= date_from)
        if date_to:
            outcomes_q = outcomes_q.where(OrderOutcome.recorded_at <= date_to)

        outcomes = session.scalars(outcomes_q).all()
        outcome_count = len(outcomes)

        delivered_count = sum(1 for o in outcomes if o.final_delivery_outcome == "DELIVERED")
        rto_count = sum(1 for o in outcomes if o.final_delivery_outcome == "RTO")
        cancelled_count = sum(1 for o in outcomes if o.final_delivery_outcome == "CANCELLED")

        terminal_delivery_count = delivered_count + rto_count
        observed_rto_rate = (
            round((rto_count / terminal_delivery_count) * 100, 2)
            if terminal_delivery_count > 0
            else 0.0
        )
        outcome_coverage_pct = (
            round((outcome_count / eligible_completed_count) * 100, 2)
            if eligible_completed_count > 0
            else 0.0
        )

        predictions_evaluated_count = sum(1 for o in outcomes if o.predicted_p_rto is not None)
        prediction_coverage_pct = (
            round((predictions_evaluated_count / outcome_count) * 100, 2)
            if outcome_count > 0
            else 0.0
        )

        # 3. Intervention Acceptance Rate
        recommended_interventions = [o for o in outcomes if o.deterministic_recommendation != "SHIP_AS_IS"]
        accepted_interventions = [o for o in recommended_interventions if o.merchant_approved_action is not None and o.merchant_approved_action != "SHIP_AS_IS"]
        intervention_acceptance_rate = (
            round((len(accepted_interventions) / len(recommended_interventions)) * 100, 2)
            if len(recommended_interventions) > 0
            else 0.0
        )

        # 4. Verified Financial Aggregates
        total_rev = sum((o.realized_collected_revenue for o in outcomes), Decimal("0.00"))
        total_cogs = sum((o.realized_cogs for o in outcomes), Decimal("0.00"))
        total_shipping = sum((o.realized_shipping_cost for o in outcomes), Decimal("0.00"))
        total_damage = sum((o.realized_damage_cost for o in outcomes), Decimal("0.00"))
        total_rto_loss = sum((o.realized_rto_loss for o in outcomes), Decimal("0.00"))
        total_int_cost = sum((o.intervention_cost for o in outcomes), Decimal("0.00"))
        total_realized_rc = sum((o.realized_contribution for o in outcomes), Decimal("0.00"))

        # 5. Empirical Classification Performance (Evaluated on Terminal Delivery Orders)
        tp = 0
        fp = 0
        fn = 0
        tn = 0
        for o in outcomes:
            if o.final_delivery_outcome not in ("DELIVERED", "RTO"):
                continue

            # A prediction flag is positive if shadow P(RTO) >= threshold OR rule recommended intervention
            flagged_positive = False
            if o.predicted_p_rto is not None:
                flagged_positive = float(o.predicted_p_rto) >= operating_threshold
            elif o.deterministic_recommendation != "SHIP_AS_IS":
                flagged_positive = True

            actual_rto = o.final_delivery_outcome == "RTO"

            if flagged_positive and actual_rto:
                tp += 1
            elif flagged_positive and not actual_rto:
                fp += 1
            elif not flagged_positive and actual_rto:
                fn += 1
            else:
                tn += 1

        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None
        recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else None
        f1_score = None
        if precision is not None and recall is not None and (precision + recall) > 0:
            f1_score = round(2 * (precision * recall) / (precision + recall), 4)

        classification_perf = ClassificationMetrics(
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            true_negatives=tn,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            evaluation_basis=f"Evaluated on {terminal_delivery_count} terminal delivery outcomes with threshold tau={operating_threshold}",
        )

        observed_facts = ObservedRealizedFacts(
            eligible_completed_orders_count=eligible_completed_count,
            outcome_records_count=outcome_count,
            outcome_coverage_pct=outcome_coverage_pct,
            delivered_count=delivered_count,
            rto_count=rto_count,
            cancelled_count=cancelled_count,
            observed_rto_rate_pct=observed_rto_rate,
            predictions_evaluated_count=predictions_evaluated_count,
            prediction_coverage_pct=prediction_coverage_pct,
            intervention_acceptance_rate_pct=intervention_acceptance_rate,
            total_realized_revenue_inr=total_rev,
            total_realized_cogs_inr=total_cogs,
            total_realized_shipping_inr=total_shipping,
            total_realized_damage_inr=total_damage,
            total_realized_rto_loss_inr=total_rto_loss,
            total_realized_intervention_cost_inr=total_int_cost,
            total_realized_net_contribution_inr=total_realized_rc,
            classification_performance=classification_perf,
        )

        # 6. Modeled Ex-Ante Estimates & Counterfactual Simulations
        ec_list = [o.expected_contribution for o in outcomes if o.expected_contribution is not None]
        total_ec = sum(ec_list, Decimal("0.00")) if ec_list else None
        variance_rc_ec = (total_realized_rc - total_ec) if total_ec is not None else None

        prob_list = [float(o.predicted_p_rto) for o in outcomes if o.predicted_p_rto is not None]
        mean_p_rto = round(sum(prob_list) / len(prob_list), 4) if prob_list else None

        # Counterfactual sweep on observed TP loss pool
        tp_loss_sum = sum(
            o.realized_rto_loss
            for o in outcomes
            if o.final_delivery_outcome == "RTO"
            and (
                (o.predicted_p_rto is not None and float(o.predicted_p_rto) >= operating_threshold)
                or o.deterministic_recommendation != "SHIP_AS_IS"
            )
        )
        fp_count = fp
        fp_friction_loss = Decimal("0.00")
        for o in outcomes:
            if o.final_delivery_outcome == "DELIVERED" and (
                (o.predicted_p_rto is not None and float(o.predicted_p_rto) >= operating_threshold)
                or o.deterministic_recommendation != "SHIP_AS_IS"
            ):
                fp_friction_loss += (o.realized_contribution * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        overhead = (Decimal(str(tp + fp)) * Decimal("0.50")) + fp_friction_loss
        break_even_eta = float((overhead / tp_loss_sum).quantize(Decimal("0.0001"))) if tp_loss_sum > Decimal("0.00") else 0.0

        counterfactual_scenarios = {
            "break_even_effectiveness_eta": break_even_eta,
            "break_even_effectiveness_pct": round(break_even_eta * 100, 2),
            "simulated_scenarios": {
                "eta_10pct": {
                    "assumed_eta": 0.10,
                    "simulated_gross_saved_loss": str(round(tp_loss_sum * Decimal("0.10"), 2)),
                    "simulated_net_lift": str(round(tp_loss_sum * Decimal("0.10") - overhead, 2)),
                },
                "eta_20pct": {
                    "assumed_eta": 0.20,
                    "simulated_gross_saved_loss": str(round(tp_loss_sum * Decimal("0.20"), 2)),
                    "simulated_net_lift": str(round(tp_loss_sum * Decimal("0.20") - overhead, 2)),
                },
                "eta_25pct": {
                    "assumed_eta": 0.25,
                    "simulated_gross_saved_loss": str(round(tp_loss_sum * Decimal("0.25"), 2)),
                    "simulated_net_lift": str(round(tp_loss_sum * Decimal("0.25") - overhead, 2)),
                },
            },
        }

        modeled_estimates = ModeledExAnteEstimates(
            total_expected_contribution_inr=total_ec,
            variance_realized_vs_expected_inr=variance_rc_ec,
            mean_predicted_p_rto=mean_p_rto,
            counterfactual_disclaimer=(
                "GOVERNANCE NOTICE: Counterfactual scenarios are mathematical estimates based on assumed "
                "intervention conversion rates (eta). They represent modeled potential, NOT verified cash savings. "
                "Real causal efficacy can only be proven via randomized controlled A/B testing on live merchant traffic."
            ),
            counterfactual_scenarios=counterfactual_scenarios,
        )

        return OutcomeMonitoringMetricsOut(
            org_id=org_id,
            generated_at=datetime.now(timezone.utc),
            time_window={
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
            observed_realized_facts=observed_facts,
            modeled_ex_ante_estimates=modeled_estimates,
        )
