"""Delivery Lifecycle and NDR Recovery Service.

Provides:
- Delivery state machine with strict transition validation.
- Delivery tracking events with idempotency and out-of-order event safety.
- Webhook HMAC signature verification for courier events.
- NDR Case creation, multi-attempt tracking, and priority assignment.
- Permitted recovery actions (CONTACT_CUSTOMER, VERIFY_ADDRESS, SCHEDULE_REATTEMPT, ESCALATE, CLOSE).
- Financial decision support calculating expected recovery lift without double-counting.
- Full hash-chained audit logging and tenant isolation.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.delivery import DeliveryEvent, NDRActionLog, NDRCase
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.schemas.delivery import (
    CourierWebhookPayload,
    DeliveryEventCreate,
    NDRActionCreate,
    NDRRecommendationOut,
    SimulateDeliveryRequest,
)
from app.services.audit_service import AuditService


ALLOWED_TRANSITIONS = {
    "PENDING": {"CONFIRMED", "HOLD", "CANCELLED"},
    "CONFIRMED": {"READY_TO_SHIP", "HOLD", "CANCELLED"},
    "HOLD": {"CONFIRMED", "READY_TO_SHIP", "CANCELLED"},
    "READY_TO_SHIP": {"SHIPPED", "HOLD", "CANCELLED"},
    "SHIPPED": {"OUT_FOR_DELIVERY", "DELIVERED", "NDR", "RTO"},
    "OUT_FOR_DELIVERY": {"DELIVERED", "NDR", "RTO"},
    "NDR": {"OUT_FOR_DELIVERY", "DELIVERED", "RTO", "CANCELLED"},
    "DELIVERED": set(),  # Terminal state
    "RTO": set(),        # Terminal state
    "CANCELLED": set(),  # Terminal state
}

TERMINAL_STATES = {"DELIVERED", "RTO", "CANCELLED"}


class DeliveryService:

    @staticmethod
    def validate_transition(current_status: str, target_status: str) -> bool:
        """Checks if moving from current_status to target_status is permitted."""
        if current_status == target_status:
            return True
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        return target_status in allowed

    @staticmethod
    def map_event_to_status(event_type: str) -> str:
        """Maps incoming courier or operational event type to standardized order status."""
        event_upper = event_type.upper().strip()
        mapping = {
            "ORDER_CONFIRMED": "CONFIRMED",
            "CONFIRMED": "CONFIRMED",
            "READY_TO_SHIP": "READY_TO_SHIP",
            "MANIFESTED": "SHIPPED",
            "PICKED_UP": "SHIPPED",
            "IN_TRANSIT": "SHIPPED",
            "SHIPPED": "SHIPPED",
            "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
            "DELIVERY_ATTEMPT_FAILED": "NDR",
            "NDR": "NDR",
            "UNDELIVERED": "NDR",
            "DELIVERED": "DELIVERED",
            "RTO_INITIATED": "RTO",
            "RTO_IN_TRANSIT": "RTO",
            "RTO_DELIVERED": "RTO",
            "RTO": "RTO",
            "CANCELLED": "CANCELLED",
            "HOLD": "HOLD",
        }
        if event_upper not in mapping:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown event type: '{event_type}'. Permitted event types: {list(mapping.keys())}",
            )
        return mapping[event_upper]

    @staticmethod
    def record_delivery_event(
        org_id: UUID,
        order_id: UUID,
        event_in: DeliveryEventCreate,
        session: Session,
        actor_user_id: Optional[UUID] = None,
    ) -> Tuple[DeliveryEvent, Order]:
        """Ingests a delivery tracking event with idempotency, transition guards, and audit trail."""
        order = session.scalar(
            select(Order).where(Order.id == order_id, Order.org_id == org_id)
        )
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found or unauthorized.",
            )

        event_id = event_in.event_id or f"evt-{order.external_order_id}-{event_in.event_type}-{uuid.uuid4().hex[:8]}"

        # Idempotency check: return existing event without mutating order
        existing_event = session.scalar(
            select(DeliveryEvent).where(
                DeliveryEvent.org_id == org_id,
                DeliveryEvent.event_id == event_id,
            )
        )
        if existing_event:
            return existing_event, order

        target_status = DeliveryService.map_event_to_status(event_in.event_type)
        current_status = order.status
        status_changed = False

        # Out-of-order handling: If order is in a terminal state, log event but do NOT revert order status
        if current_status in TERMINAL_STATES and target_status != current_status:
            # Out of order: record event with note, keep terminal status
            new_order_status = current_status
        else:
            if not DeliveryService.validate_transition(current_status, target_status):
                allowed = list(ALLOWED_TRANSITIONS.get(current_status, []))
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid delivery transition: cannot move from '{current_status}' to '{target_status}'. Permitted next states: {allowed}",
                )
            if current_status != target_status:
                order.status = target_status
                if target_status in ("SHIPPED", "OUT_FOR_DELIVERY", "NDR", "DELIVERED", "RTO"):
                    order.fulfillment_status = "FULFILLED"
                elif target_status in ("PENDING", "CONFIRMED", "READY_TO_SHIP"):
                    order.fulfillment_status = "UNFULFILLED"
                elif target_status in ("HOLD", "CANCELLED"):
                    order.fulfillment_status = "HOLD"
                status_changed = True
            new_order_status = order.status

        occurred_at = event_in.occurred_at or datetime.now(timezone.utc)

        delivery_event = DeliveryEvent(
            org_id=org_id,
            order_id=order_id,
            event_id=event_id,
            event_type=event_in.event_type.upper(),
            previous_status=current_status,
            new_status=new_order_status,
            event_source=event_in.event_source or "SYSTEM",
            is_simulated=bool(event_in.is_simulated),
            carrier_name=event_in.carrier_name or order.courier_name,
            tracking_number=event_in.tracking_number or order.tracking_number,
            carrier_status_code=event_in.carrier_status_code,
            reason_code=event_in.reason_code,
            reason_description=event_in.reason_description,
            location=event_in.location,
            occurred_at=occurred_at,
            raw_payload=event_in.raw_payload or {},
        )
        session.add(delivery_event)
        session.flush()

        # Update order courier/tracking if provided
        if event_in.carrier_name and not order.courier_name:
            order.courier_name = event_in.carrier_name
        if event_in.tracking_number and not order.tracking_number:
            order.tracking_number = event_in.tracking_number

        # Automatic NDR Case Lifecycle
        if target_status == "NDR":
            DeliveryService._handle_ndr_trigger(
                order=order,
                delivery_event=delivery_event,
                session=session,
            )
        elif target_status in TERMINAL_STATES:
            DeliveryService._handle_terminal_ndr_closure(
                order=order,
                terminal_status=target_status,
                session=session,
                closed_by_user_id=actor_user_id,
            )
            # Automatic Real-Order Outcome Tracking & Realized Reconciliation
            try:
                from app.services.outcome_tracking_service import OutcomeTrackingService
                OutcomeTrackingService.record_order_outcome(
                    org_id=org_id,
                    order_id=order_id,
                    session=session,
                    actor_user_id=actor_user_id,
                )
            except Exception as outcome_exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Automatic outcome tracking failed for order %s: %s", order.id, outcome_exc
                )

        # Audit log entry
        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="DELIVERY_EVENT_RECORDED",
            resource_type="DeliveryEvent",
            resource_id=str(delivery_event.id),
            payload={
                "order_id": str(order.id),
                "external_order_id": order.external_order_id,
                "event_type": delivery_event.event_type,
                "previous_status": current_status,
                "new_status": new_order_status,
                "status_changed": status_changed,
                "is_simulated": delivery_event.is_simulated,
                "reason_code": delivery_event.reason_code,
            },
        )

        session.commit()
        session.refresh(delivery_event)
        session.refresh(order)
        return delivery_event, order

    @staticmethod
    def _handle_ndr_trigger(
        order: Order,
        delivery_event: DeliveryEvent,
        session: Session,
    ) -> NDRCase:
        """Creates or updates an NDR recovery case upon delivery attempt failure."""
        active_case = session.scalar(
            select(NDRCase).where(
                NDRCase.org_id == order.org_id,
                NDRCase.order_id == order.id,
                NDRCase.status.in_(["OPEN", "IN_PROGRESS", "REATTEMPT_SCHEDULED"]),
            )
        )

        reason_code = delivery_event.reason_code or "CUSTOMER_UNAVAILABLE"

        if active_case:
            active_case.attempt_count += 1
            active_case.last_attempt_date = delivery_event.occurred_at
            active_case.reason_code = reason_code
            if delivery_event.reason_description:
                active_case.carrier_reason_raw = delivery_event.reason_description
            if active_case.attempt_count >= 3:
                active_case.priority = "HIGH"
                active_case.next_action = "CRITICAL_ATTEMPT_LIMIT_REACHED"
            return active_case

        # Create new NDR case
        case_num = f"NDR-{order.external_order_id}-{uuid.uuid4().hex[:4].upper()}"
        order_val = Decimal(str(order.order_value))
        priority = "HIGH" if order_val >= Decimal("2500.00") else ("MEDIUM" if order_val >= Decimal("1000.00") else "LOW")

        # Load economics to compute recovery decision support
        economics = session.scalar(
            select(MerchantEconomics).where(MerchantEconomics.org_id == order.org_id)
        )
        if not economics:
            economics = MerchantEconomics(org_id=order.org_id)
            session.add(economics)
            session.flush()

        rec = DeliveryService.compute_recovery_recommendation(order=order, economics=economics, reason_code=reason_code)

        ndr_case = NDRCase(
            org_id=order.org_id,
            order_id=order.id,
            case_number=case_num,
            status="OPEN",
            priority=priority,
            attempt_count=1,
            last_attempt_date=delivery_event.occurred_at,
            reason_code=reason_code,
            carrier_reason_raw=delivery_event.reason_description,
            is_simulated=delivery_event.is_simulated,
            expected_recovery_lift=rec.expected_recovery_lift,
            estimated_recovery_ec=rec.estimated_recovery_ec,
            recommended_recovery_action=rec.recommended_action,
            recommendation_rationale=rec.rationale,
            next_action=rec.recommended_action,
        )
        session.add(ndr_case)
        session.flush()
        return ndr_case

    @staticmethod
    def _handle_terminal_ndr_closure(
        order: Order,
        terminal_status: str,
        session: Session,
        closed_by_user_id: Optional[UUID] = None,
    ) -> None:
        """Automatically closes active NDR cases when order reaches a terminal state."""
        active_cases = list(
            session.scalars(
                select(NDRCase).where(
                    NDRCase.org_id == order.org_id,
                    NDRCase.order_id == order.id,
                    NDRCase.status.in_(["OPEN", "IN_PROGRESS", "REATTEMPT_SCHEDULED"]),
                )
            ).all()
        )
        for case in active_cases:
            if terminal_status == "DELIVERED":
                case.status = "RESOLVED_DELIVERED"
                case.closure_reason = "Order successfully delivered on reattempt."
            elif terminal_status == "RTO":
                case.status = "RESOLVED_RTO"
                case.closure_reason = "Order returned to origin (RTO)."
            elif terminal_status == "CANCELLED":
                case.status = "RESOLVED_CANCELLED"
                case.closure_reason = "Order cancelled."
            case.closed_at = datetime.now(timezone.utc)
            case.closed_by_user_id = closed_by_user_id

    @staticmethod
    def compute_recovery_recommendation(
        order: Order,
        economics: MerchantEconomics,
        reason_code: str,
    ) -> NDRRecommendationOut:
        """Computes optimal NDR recovery decision and financial lift without double counting.
        
        Zero Double-Counting Principles:
        - Forward shipping S_f is already committed and sunk.
        - Reverse shipping S_r is only incurred if the order terminates in RTO.
        - Intervention cost C_int is deducted exactly once.
        - Profit at Risk (PaR) = Payoff(Delivered) - Payoff(RTO).
        - Net Lift = P(Delivered) * PaR - C_int.
        """
        v = Decimal(str(order.order_value))
        cogs_pct = Decimal(str(economics.default_cogs_percent)) / Decimal("100.00")
        cogs = (v * cogs_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        s_f = Decimal(str(economics.forward_shipping_cost))
        s_r = Decimal(str(economics.reverse_shipping_cost))
        c_inv = Decimal(str(economics.packaging_cost))
        damage_rate = Decimal(str(economics.inventory_damage_rate))
        damage_rto = (cogs * damage_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Payment processing fee
        if order.payment_method == "COD":
            f_p = Decimal(str(economics.cod_carrier_fee))
            # COD manifest vs delivery policy
            f_cod_manifest = f_p if economics.cod_fee_incurred_on == "UPON_MANIFEST" else Decimal("0.00")
        else:
            pg_pct = Decimal(str(economics.payment_gateway_percent)) / Decimal("100.00")
            pg_flat = Decimal(str(economics.payment_gateway_flat))
            f_p = (v * pg_pct + pg_flat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            f_cod_manifest = f_p  # Non-refundable gateway fee

        # Payoff if Delivered: R_col - COGS - S_f - F_p - C_inv
        payoff_delivered = v - cogs - s_f - f_p - c_inv

        # Payoff if RTO: - (S_f + S_r + F_cod_manifest + D_rto + C_inv)
        payoff_rto = -(s_f + s_r + f_cod_manifest + damage_rto + c_inv)

        # Profit at Risk: difference between delivering and RTO
        par = payoff_delivered - payoff_rto

        # Choose best candidate recovery action based on failure reason
        reason_upper = reason_code.upper() if reason_code else "CUSTOMER_UNAVAILABLE"
        if "INCORRECT_ADDRESS" in reason_upper or "ADDRESS" in reason_upper:
            rec_action = "VERIFY_ADDRESS"
            p_deliv = Decimal("0.70")
            c_int = Decimal("6.50")  # Address verification comms + review
            rationale = "Customer address is reported incomplete. Reaching out via WhatsApp/SMS to capture landmark and corrected address yields ~70% delivery success."
        elif "RESCHEDULE" in reason_upper or "DATE" in reason_upper:
            rec_action = "SCHEDULE_REATTEMPT"
            p_deliv = Decimal("0.75")
            c_int = Decimal("1.50")  # Courier reschedule API / WhatsApp confirmation
            rationale = "Customer requested reschedule. Rebooking delivery slot yields ~75% delivery success."
        elif "REFUSED" in reason_upper:
            rec_action = "ESCALATE_TO_MANUAL_REVIEW"
            p_deliv = Decimal("0.35")
            c_int = Decimal("15.00")  # Senior dialer agent
            rationale = "Customer refused delivery at doorstep. High risk of immediate RTO. Requiring senior tele-agent intervention."
        else:  # CUSTOMER_UNAVAILABLE or UNREACHABLE
            rec_action = "CONTACT_CUSTOMER"
            p_deliv = Decimal("0.60")
            c_int = Decimal("5.00")  # Multi-channel reminder
            rationale = "Customer was unavailable or phone unreachable. Automated WhatsApp delivery alert with confirmation link yields ~60% recovery rate."

        # Net Recovery Expected Contribution:
        # EC = P_deliv * Payoff(Delivered) + (1 - P_deliv) * Payoff(RTO) - C_int
        # Net Lift over RTO = P_deliv * PaR - C_int
        expected_lift = (p_deliv * par - c_int).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        expected_ec = (p_deliv * payoff_delivered + (Decimal("1.00") - p_deliv) * payoff_rto - c_int).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return NDRRecommendationOut(
            ndr_case_id=uuid.uuid4(),
            order_id=order.id,
            recommended_action=rec_action,
            expected_recovery_lift=expected_lift,
            estimated_recovery_ec=expected_ec,
            baseline_rto_loss=payoff_rto,
            profit_at_risk=par,
            estimated_rescue_prob=p_deliv,
            intervention_cost=c_int,
            rationale=rationale,
            data_sufficiency="SUFFICIENT" if v > 0 else "DEFAULT_CONFIGURED",
            accounting_notes="Forward shipping S_f is sunk. Reverse shipping S_r is avoided upon rescue. C_int is deducted exactly once.",
        )

    @staticmethod
    def record_ndr_action(
        org_id: UUID,
        case_id: UUID,
        action_in: NDRActionCreate,
        session: Session,
        actor_user_id: Optional[UUID] = None,
    ) -> NDRCase:
        """Executes a permitted recovery action on an active NDR case."""
        ndr_case = session.scalar(
            select(NDRCase).where(NDRCase.id == case_id, NDRCase.org_id == org_id)
        )
        if not ndr_case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="NDR case not found or unauthorized.",
            )

        if ndr_case.status in ["RESOLVED_DELIVERED", "RESOLVED_RTO", "RESOLVED_CANCELLED", "CLOSED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot execute action on closed NDR case (status: {ndr_case.status}).",
            )

        order = session.scalar(
            select(Order).where(Order.id == ndr_case.order_id, Order.org_id == org_id)
        )

        action_type = action_in.action_type.upper().strip()
        action_details: Dict[str, Any] = {}
        cost = Decimal("0.00")

        if action_type == "CONTACT_CUSTOMER":
            ndr_case.customer_contacted = True
            ndr_case.contact_method = action_in.contact_method or "WHATSAPP"
            ndr_case.customer_response = action_in.customer_response
            ndr_case.status = "IN_PROGRESS"
            cost = Decimal("1.50") if action_in.contact_method in ["WHATSAPP", "SMS"] else Decimal("15.00")
            action_details = {
                "method": ndr_case.contact_method,
                "response": ndr_case.customer_response,
            }

        elif action_type == "VERIFY_ADDRESS":
            if action_in.updated_address1:
                ndr_case.updated_address1 = action_in.updated_address1
                if order:
                    order.shipping_address1 = action_in.updated_address1
            if action_in.updated_address2:
                ndr_case.updated_address2 = action_in.updated_address2
                if order:
                    order.shipping_address2 = action_in.updated_address2
            if action_in.updated_city:
                ndr_case.updated_city = action_in.updated_city
                if order:
                    order.shipping_city = action_in.updated_city
            if action_in.updated_state:
                ndr_case.updated_state = action_in.updated_state
                if order:
                    order.shipping_state = action_in.updated_state
            if action_in.updated_pincode:
                ndr_case.updated_pincode = action_in.updated_pincode
                if order:
                    order.shipping_pincode = action_in.updated_pincode
            if action_in.updated_phone:
                ndr_case.updated_phone = action_in.updated_phone
                if order:
                    order.customer_phone = action_in.updated_phone
            ndr_case.status = "IN_PROGRESS"
            cost = Decimal("5.00")
            action_details = {
                "address1": ndr_case.updated_address1,
                "pincode": ndr_case.updated_pincode,
                "phone": ndr_case.updated_phone,
            }

        elif action_type == "SCHEDULE_REATTEMPT":
            reattempt_dt = action_in.reattempt_date or datetime.now(timezone.utc)
            ndr_case.reattempt_date = reattempt_dt
            ndr_case.status = "REATTEMPT_SCHEDULED"
            ndr_case.next_action = "AWAITING_COURIER_REATTEMPT"
            cost = Decimal("1.50")
            action_details = {"scheduled_date": reattempt_dt.isoformat()}

        elif action_type == "ESCALATE_TO_MANUAL_REVIEW":
            ndr_case.priority = "HIGH"
            ndr_case.status = "IN_PROGRESS"
            ndr_case.next_action = "SENIOR_OPERATOR_REVIEW"
            cost = Decimal("15.00")
            action_details = {"escalated_to": "OPERATOR"}

        elif action_type == "REQUEST_RTO":
            ndr_case.status = "RESOLVED_RTO"
            ndr_case.closure_reason = action_in.closure_reason or "Operator initiated RTO after failed rescue."
            ndr_case.closed_at = datetime.now(timezone.utc)
            ndr_case.closed_by_user_id = actor_user_id
            action_details = {"reason": ndr_case.closure_reason}

            # Mutate order to RTO via delivery event
            if order:
                order.status = "RTO"

        elif action_type == "CLOSE_CASE":
            ndr_case.status = "CLOSED"
            ndr_case.closure_reason = action_in.closure_reason or "Manually closed by operator."
            ndr_case.closed_at = datetime.now(timezone.utc)
            ndr_case.closed_by_user_id = actor_user_id
            action_details = {"reason": ndr_case.closure_reason}

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported NDR action type: '{action_type}'. Permitted actions: CONTACT_CUSTOMER, VERIFY_ADDRESS, SCHEDULE_REATTEMPT, ESCALATE_TO_MANUAL_REVIEW, REQUEST_RTO, CLOSE_CASE",
            )

        # Log individual action
        action_log = NDRActionLog(
            org_id=org_id,
            ndr_case_id=case_id,
            order_id=ndr_case.order_id,
            actor_user_id=actor_user_id,
            action_type=action_type,
            action_details=action_details,
            intervention_cost=cost,
            notes=action_in.notes,
        )
        session.add(action_log)

        # Audit trail
        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=f"NDR_ACTION_{action_type}",
            resource_type="NDRCase",
            resource_id=str(ndr_case.id),
            payload={
                "case_number": ndr_case.case_number,
                "action_type": action_type,
                "cost": str(cost),
                "new_case_status": ndr_case.status,
            },
        )

        session.commit()
        session.refresh(ndr_case)
        return ndr_case

    @staticmethod
    def list_ndr_cases(
        org_id: UUID,
        session: Session,
        status_filter: Optional[str] = None,
        reason_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[NDRCase], int]:
        """Lists NDR cases with filtering, search, and pagination."""
        query = select(NDRCase).where(NDRCase.org_id == org_id)

        if status_filter:
            query = query.where(NDRCase.status == status_filter)
        if reason_filter:
            query = query.where(NDRCase.reason_code == reason_filter)
        if priority_filter:
            query = query.where(NDRCase.priority == priority_filter)

        if search:
            search_pattern = f"%{search.strip()}%"
            # Join order for external_order_id and customer info
            query = query.join(Order, NDRCase.order_id == Order.id).where(
                or_(
                    NDRCase.case_number.ilike(search_pattern),
                    Order.external_order_id.ilike(search_pattern),
                    Order.customer_name.ilike(search_pattern),
                    Order.customer_phone.ilike(search_pattern),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = session.scalar(count_query) or 0

        query = query.order_by(NDRCase.created_at.desc())
        query = query.limit(min(limit, 200)).offset(max(offset, 0))

        cases = list(session.scalars(query).all())
        return cases, total

    @staticmethod
    def get_ndr_case(
        org_id: UUID,
        case_id: UUID,
        session: Session,
    ) -> NDRCase:
        """Retrieves single NDR case by ID enforcing tenant isolation."""
        case = session.scalar(
            select(NDRCase).where(NDRCase.id == case_id, NDRCase.org_id == org_id)
        )
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="NDR case not found or unauthorized.",
            )
        return case

    @staticmethod
    def verify_webhook_signature(
        raw_body: bytes,
        signature: Optional[str],
        secret: str,
    ) -> bool:
        """Verifies HMAC-SHA256 signature on courier webhook payload."""
        if not signature or not secret:
            return False
        expected_sig = hmac.new(
            key=secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected_sig, signature)
