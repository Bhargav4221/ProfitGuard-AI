"""Authoritative Financial Reconciliation and Realized Contribution Service.

Enforces:
1. Immutable Order Value (GMV) separate from Collected Revenue.
2. Single authoritative ledger where COGS, shipping, payment fees, inventory damage,
   pre-dispatch intervention, and NDR recovery costs are counted exactly once.
3. Ex-ante Expected Contribution (EC) vs ex-post Realized Contribution (RC) comparison.
4. Tenant-scoped persistence and audit logging.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.delivery import NDRActionLog
from app.models.financial_reconciliation import OrderFinancialReconciliation
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.services.audit_service import AuditService


class ReconciliationService:

    @staticmethod
    def reconcile_order(
        org_id: UUID,
        order_id: UUID,
        session: Session,
        actor_user_id: Optional[UUID] = None,
    ) -> OrderFinancialReconciliation:
        """Calculates and persists the authoritative realized contribution ledger for an order."""
        order = session.scalar(
            select(Order).where(Order.id == order_id, Order.org_id == org_id)
        )
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found or unauthorized.",
            )

        economics = session.scalar(
            select(MerchantEconomics).where(MerchantEconomics.org_id == org_id)
        )
        if not economics:
            economics = MerchantEconomics(org_id=org_id)
            session.add(economics)
            session.flush()

        v = Decimal(str(order.order_value))
        terminal_status = order.status

        # 1. Calculate actual COGS
        if order.items and len(order.items) > 0 and any(item.unit_cost for item in order.items):
            cogs_total = sum(
                (Decimal(str(item.unit_cost or 0)) * item.quantity for item in order.items),
                Decimal("0.00"),
            )
        else:
            cogs_pct = Decimal(str(economics.default_cogs_percent)) / Decimal("100.00")
            cogs_total = (v * cogs_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        s_f_cost = Decimal(str(economics.forward_shipping_cost))
        s_r_cost = Decimal(str(economics.reverse_shipping_cost))
        pkg_cost = Decimal(str(economics.packaging_cost))
        damage_rate = Decimal(str(economics.inventory_damage_rate))

        # 2. Pre-dispatch intervention cost
        pre_dispatch_cost = Decimal("0.00")
        latest_eval = session.scalar(
            select(OrderEvaluation)
            .where(OrderEvaluation.org_id == org_id, OrderEvaluation.order_id == order_id)
            .order_by(OrderEvaluation.created_at.desc())
        )
        if latest_eval and latest_eval.selected_action:
            action = latest_eval.selected_action
            if action == "VERIFY_OTP":
                pre_dispatch_cost = Decimal(str(economics.otp_verification_cost))
            elif action == "MANUAL_REVIEW":
                pre_dispatch_cost = Decimal(str(economics.manual_review_cost))
            elif action == "INCENTIVIZE_PREPAID":
                comms_cost = Decimal(str(economics.prepaid_comms_cost))
                if latest_eval.intervention_status == "PREPAID_CONVERTED":
                    discount = Decimal(str(economics.prepaid_incentive_discount))
                    pre_dispatch_cost = comms_cost + discount
                else:
                    # Declined, uncompleted, or cancelled: discount was never granted; only comms cost incurred
                    pre_dispatch_cost = comms_cost

        # 3. NDR recovery intervention cost (summed across all recovery actions)
        ndr_cost_sum = session.scalar(
            select(func.sum(NDRActionLog.intervention_cost))
            .where(NDRActionLog.org_id == org_id, NDRActionLog.order_id == order_id)
        ) or Decimal("0.00")
        ndr_recovery_cost = Decimal(str(ndr_cost_sum))

        # 4. Terminal status accounting
        if terminal_status == "DELIVERED":
            collected_revenue = v
            actual_cogs = cogs_total
            forward_shipping = s_f_cost
            reverse_shipping = Decimal("0.00")
            packaging = pkg_cost
            inventory_damage = Decimal("0.00")

            if order.payment_method == "COD":
                payment_fee = Decimal(str(economics.cod_carrier_fee))
            else:
                pg_pct = Decimal(str(economics.payment_gateway_percent)) / Decimal("100.00")
                pg_flat = Decimal(str(economics.payment_gateway_flat))
                payment_fee = (v * pg_pct + pg_flat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # RC = Collected Revenue - COGS - S_f - PaymentFee - Packaging - PreDispatchCost - NDRCost
            realized_rc = (
                collected_revenue
                - actual_cogs
                - forward_shipping
                - payment_fee
                - packaging
                - pre_dispatch_cost
                - ndr_recovery_cost
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            accounting_notes = "Delivered fulfillment: Revenue collected in full; reverse shipping avoided; pre-dispatch & NDR costs accounted for."

        elif terminal_status == "RTO":
            collected_revenue = Decimal("0.00")  # Zero revenue on RTO
            actual_cogs = Decimal("0.00")        # Restocked into warehouse inventory
            forward_shipping = s_f_cost
            reverse_shipping = s_r_cost
            packaging = pkg_cost
            inventory_damage = (cogs_total * damage_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if order.payment_method == "COD":
                payment_fee = (
                    Decimal(str(economics.cod_carrier_fee))
                    if economics.cod_fee_incurred_on == "UPON_MANIFEST"
                    else Decimal("0.00")
                )
            else:
                pg_pct = Decimal(str(economics.payment_gateway_percent)) / Decimal("100.00")
                pg_flat = Decimal(str(economics.payment_gateway_flat))
                payment_fee = (v * pg_pct + pg_flat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # RC = - (S_f + S_r + PaymentFee + Packaging + Damage + PreDispatchCost + NDRCost)
            realized_rc = -(
                forward_shipping
                + reverse_shipping
                + payment_fee
                + packaging
                + inventory_damage
                + pre_dispatch_cost
                + ndr_recovery_cost
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            accounting_notes = "RTO terminal loss: Zero revenue collected; reverse shipping and inventory damage incurred."

        elif terminal_status == "CANCELLED":
            collected_revenue = Decimal("0.00")
            actual_cogs = Decimal("0.00")
            forward_shipping = Decimal("0.00")  # Stopped before manifest
            reverse_shipping = Decimal("0.00")
            packaging = Decimal("0.00")
            inventory_damage = Decimal("0.00")
            payment_fee = Decimal("0.00")

            # Cancelled orders incur only pre-dispatch or NDR comms costs
            realized_rc = -(pre_dispatch_cost + ndr_recovery_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            accounting_notes = "Pre-dispatch cancellation: Inventory preserved; zero shipping and gateway charges incurred."

        else:
            # Order is still in-flight (PENDING, CONFIRMED, SHIPPED, OUT_FOR_DELIVERY, NDR)
            collected_revenue = Decimal("0.00")
            actual_cogs = Decimal("0.00")
            forward_shipping = s_f_cost if terminal_status in ["SHIPPED", "OUT_FOR_DELIVERY", "NDR"] else Decimal("0.00")
            reverse_shipping = Decimal("0.00")
            packaging = pkg_cost if forward_shipping > 0 else Decimal("0.00")
            inventory_damage = Decimal("0.00")
            payment_fee = Decimal("0.00")
            realized_rc = -(forward_shipping + packaging + pre_dispatch_cost + ndr_recovery_cost).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            accounting_notes = f"Provisional in-flight ledger for status '{terminal_status}'. Awaiting terminal outcome."

        # Ex-ante expected contribution comparison
        expected_ec = Decimal(str(latest_eval.best_ec)) if latest_eval and latest_eval.best_ec is not None else None
        variance = (realized_rc - expected_ec).quantize(Decimal("0.01")) if expected_ec is not None else None

        status_flag = "SETTLED" if terminal_status in ["DELIVERED", "RTO", "CANCELLED"] else "PROVISIONAL"

        # Check existing reconciliation record (upsert)
        recon = session.scalar(
            select(OrderFinancialReconciliation).where(
                OrderFinancialReconciliation.org_id == org_id,
                OrderFinancialReconciliation.order_id == order_id,
            )
        )
        if not recon:
            recon = OrderFinancialReconciliation(
                org_id=org_id,
                order_id=order_id,
                external_order_id=order.external_order_id,
                terminal_status=terminal_status,
                order_value=v,
                collected_revenue=collected_revenue,
                cogs=actual_cogs,
                forward_shipping_cost=forward_shipping,
                reverse_shipping_cost=reverse_shipping,
                payment_fee=payment_fee,
                packaging_cost=packaging,
                inventory_damage_cost=inventory_damage,
                pre_dispatch_intervention_cost=pre_dispatch_cost,
                ndr_recovery_intervention_cost=ndr_recovery_cost,
                realized_contribution=realized_rc,
                expected_contribution=expected_ec,
                variance_ec_vs_rc=variance,
                reconciliation_status=status_flag,
                accounting_notes=accounting_notes,
                reconciled_at=datetime.now(timezone.utc),
            )
            session.add(recon)
        else:
            recon.terminal_status = terminal_status
            recon.collected_revenue = collected_revenue
            recon.cogs = actual_cogs
            recon.forward_shipping_cost = forward_shipping
            recon.reverse_shipping_cost = reverse_shipping
            recon.payment_fee = payment_fee
            recon.packaging_cost = packaging
            recon.inventory_damage_cost = inventory_damage
            recon.pre_dispatch_intervention_cost = pre_dispatch_cost
            recon.ndr_recovery_intervention_cost = ndr_recovery_cost
            recon.realized_contribution = realized_rc
            recon.expected_contribution = expected_ec
            recon.variance_ec_vs_rc = variance
            recon.reconciliation_status = status_flag
            recon.accounting_notes = accounting_notes
            recon.reconciled_at = datetime.now(timezone.utc)

        # Audit event
        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="ORDER_FINANCIALLY_RECONCILED",
            resource_type="OrderFinancialReconciliation",
            resource_id=str(recon.id),
            payload={
                "order_id": str(order.id),
                "external_order_id": order.external_order_id,
                "terminal_status": terminal_status,
                "order_value": str(v),
                "collected_revenue": str(collected_revenue),
                "realized_contribution": str(realized_rc),
                "status": status_flag,
            },
        )

        session.commit()
        session.refresh(recon)
        return recon

    @staticmethod
    def get_order_reconciliation(
        org_id: UUID,
        order_id: UUID,
        session: Session,
    ) -> OrderFinancialReconciliation:
        """Retrieves existing financial reconciliation or computes on-the-fly."""
        recon = session.scalar(
            select(OrderFinancialReconciliation).where(
                OrderFinancialReconciliation.org_id == org_id,
                OrderFinancialReconciliation.order_id == order_id,
            )
        )
        if not recon:
            return ReconciliationService.reconcile_order(org_id=org_id, order_id=order_id, session=session)
        return recon
