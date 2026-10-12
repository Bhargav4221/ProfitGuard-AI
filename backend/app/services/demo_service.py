"""Repeatable Demo Dataset and End-to-End Demonstration Service.

Provides:
- Reset: Safely purges only DEMO-* records for the current tenant.
- Seed: Populates a realistic demo workspace with simulated orders and NDR cases.
- Run Journey: Executes the complete 8-step journey from order intake to financial reconciliation.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.delivery import DeliveryEvent, NDRCase
from app.models.financial_reconciliation import OrderFinancialReconciliation
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.order_item import OrderItem
from app.schemas.decision import InterventionOutcomeRequest, OrderDecisionRecordRequest
from app.schemas.delivery import DeliveryEventCreate, NDRActionCreate
from app.services.audit_service import AuditService
from app.services.decision_engine import DecisionEngineService
from app.services.delivery_service import DeliveryService
from app.services.reconciliation_service import ReconciliationService


class DemoService:

    @staticmethod
    def reset_demo_data(org_id: UUID, session: Session, user_id: UUID) -> int:
        """Safely removes ONLY demo-seeded records for this tenant (external_order_id like 'DEMO-%')."""
        demo_orders = list(
            session.scalars(
                select(Order).where(Order.org_id == org_id, Order.external_order_id.like("DEMO-%"))
            ).all()
        )
        count = len(demo_orders)
        for order in demo_orders:
            session.delete(order)

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=user_id,
            action="DEMO_DATA_RESET",
            resource_type="Organization",
            resource_id=str(org_id),
            payload={"deleted_demo_orders_count": count},
        )
        session.commit()
        return count

    @staticmethod
    def seed_demo_data(org_id: UUID, session: Session, user_id: UUID) -> Dict[str, Any]:
        """Seeds realistic, clearly-labelled simulated demo records for demonstration."""
        # 1. Clean existing demo data first to ensure idempotency
        DemoService.reset_demo_data(org_id=org_id, session=session, user_id=user_id)

        economics = session.scalar(select(MerchantEconomics).where(MerchantEconomics.org_id == org_id))
        if not economics:
            economics = MerchantEconomics(org_id=org_id)
            session.add(economics)
            session.flush()

        seeded_orders = []

        # Order 1: High-ticket COD order ready for 8-step journey
        ord1 = Order(
            id=uuid4(),
            org_id=org_id,
            external_order_id="DEMO-COD-JOURNEY-001",
            order_date=datetime.now(timezone.utc),
            order_value=Decimal("1850.00"),
            payment_method="COD",
            status="PENDING",
            customer_name="Aarav Sharma",
            customer_phone="9820112233",
            customer_email="aarav.demo@example.com",
            shipping_address1="102, Palm Grove, Hiranandani Estate",
            shipping_city="Thane",
            shipping_state="Maharashtra",
            shipping_pincode="400607",
            source_channel="SHOPIFY (Simulated)",
        )
        session.add(ord1)
        session.flush()

        item1 = OrderItem(
            org_id=org_id,
            order_id=ord1.id,
            sku="DEMO-SKU-AUDIO-01",
            product_name="Wireless Noise Cancelling Earbuds",
            quantity=1,
            unit_price=Decimal("1850.00"),
            unit_cost=Decimal("550.00"),
            total_price=Decimal("1850.00"),
        )
        session.add(item1)
        seeded_orders.append(ord1.external_order_id)

        # Order 2: Delivered Prepaid order
        ord2 = Order(
            id=uuid4(),
            org_id=org_id,
            external_order_id="DEMO-PREPAID-DELIV-002",
            order_date=datetime.now(timezone.utc),
            order_value=Decimal("1200.00"),
            payment_method="PREPAID",
            status="DELIVERED",
            fulfillment_status="FULFILLED",
            customer_name="Pooja Rao",
            customer_phone="9845098450",
            customer_email="pooja.demo@example.com",
            shipping_address1="Flat 4B, Green Glen Layout, Bellandur",
            shipping_city="Bengaluru",
            shipping_state="Karnataka",
            shipping_pincode="560103",
            courier_name="BlueDart (Simulated)",
            tracking_number="BD-DEMO-991122",
            source_channel="SHOPIFY (Simulated)",
        )
        session.add(ord2)
        session.flush()
        # Reconcile ord2
        ReconciliationService.reconcile_order(org_id=org_id, order_id=ord2.id, session=session, actor_user_id=user_id)
        seeded_orders.append(ord2.external_order_id)

        # Order 3: Active NDR Case ready for rescue
        ord3 = Order(
            id=uuid4(),
            org_id=org_id,
            external_order_id="DEMO-NDR-ACTIVE-003",
            order_date=datetime.now(timezone.utc),
            order_value=Decimal("2900.00"),
            payment_method="COD",
            status="NDR",
            fulfillment_status="FULFILLED",
            customer_name="Vikram Singh",
            customer_phone="9988776655",
            customer_email="vikram.demo@example.com",
            shipping_address1="House 24, Sector 14",
            shipping_city="Gurugram",
            shipping_state="Haryana",
            shipping_pincode="122001",
            courier_name="Delhivery (Simulated)",
            tracking_number="DEL-DEMO-773322",
            source_channel="CSV_IMPORT (Simulated)",
        )
        session.add(ord3)
        session.flush()

        # Trigger NDR case for ord3
        evt3 = DeliveryEvent(
            org_id=org_id,
            order_id=ord3.id,
            event_id="demo-ndr-scan-003",
            event_type="DELIVERY_ATTEMPT_FAILED",
            new_status="NDR",
            event_source="COURIER_WEBHOOK_SIMULATED",
            is_simulated=True,
            carrier_name="Delhivery (Simulated)",
            reason_code="CUSTOMER_UNAVAILABLE",
            reason_description="Customer phone switched off at delivery gate.",
            occurred_at=datetime.now(timezone.utc),
        )
        session.add(evt3)
        session.flush()
        DeliveryService._handle_ndr_trigger(order=ord3, delivery_event=evt3, session=session)
        seeded_orders.append(ord3.external_order_id)

        session.commit()
        return {
            "status": "success",
            "message": f"Seeded {len(seeded_orders)} simulated demonstration orders.",
            "seeded_orders": seeded_orders,
        }

    @staticmethod
    def run_complete_journey(org_id: UUID, session: Session, user_id: UUID) -> Dict[str, Any]:
        """Runs the entire 8-step journey on DEMO-COD-JOURNEY-001 and returns the execution transcript."""
        # Ensure demo order exists
        order = session.scalar(
            select(Order).where(Order.org_id == org_id, Order.external_order_id == "DEMO-COD-JOURNEY-001")
        )
        if not order:
            DemoService.seed_demo_data(org_id=org_id, session=session, user_id=user_id)
            order = session.scalar(
                select(Order).where(Order.org_id == org_id, Order.external_order_id == "DEMO-COD-JOURNEY-001")
            )

        economics = session.scalar(select(MerchantEconomics).where(MerchantEconomics.org_id == org_id))
        transcript: List[Dict[str, Any]] = []

        # ---------------------------------------------------------------------
        # Step 1: Order Intake
        # ---------------------------------------------------------------------
        transcript.append({
            "step": 1,
            "title": "Order Ingested (Checkout Agreed)",
            "details": f"COD Order #{order.external_order_id} recorded with immutable GMV ₹{order.order_value}.",
            "order_status": order.status,
            "order_value": str(order.order_value),
        })

        # ---------------------------------------------------------------------
        # Step 2: 5-Action Decision Engine Risk Evaluation
        # ---------------------------------------------------------------------
        eval_result = DecisionEngineService.evaluate_order(
            order=order,
            economics=economics,
            session=session,
            evaluated_by_user_id=user_id,
        )
        transcript.append({
            "step": 2,
            "title": "Profit-Aware Decision Evaluation",
            "details": f"Engine evaluated 5 candidate actions. Recommended: {eval_result.recommended_action} with expected lift +₹{eval_result.recommended_lift}.",
            "recommended_action": eval_result.recommended_action,
            "expected_lift": str(eval_result.recommended_lift),
            "ship_as_is_ec": str(eval_result.ship_as_is_ec),
            "best_ec": str(eval_result.best_ec),
        })

        # ---------------------------------------------------------------------
        # Step 3: Action Recorded & Pre-Dispatch Intervention Executed
        # ---------------------------------------------------------------------
        rec_action = eval_result.recommended_action
        override_reason = (
            "Demonstration standardizing on OTP verification journey."
            if rec_action != "VERIFY_OTP"
            else None
        )
        dec_result = DecisionEngineService.record_decision(
            order_id=order.id,
            org_id=org_id,
            user_id=user_id,
            action="VERIFY_OTP",
            override_reason=override_reason,
            session=session,
        )
        # Record successful OTP verification
        DecisionEngineService.record_intervention_outcome(
            order_id=order.id,
            org_id=org_id,
            user_id=user_id,
            outcome="OTP_VERIFIED",
            notes="Customer confirmed purchase via WhatsApp OTP verification.",
            session=session,
        )
        transcript.append({
            "step": 3,
            "title": "Intervention Recorded & Verified",
            "details": f"Operator accepted VERIFY_OTP. Customer verified OTP successfully (Cost: ₹{economics.otp_verification_cost}). Order confirmed.",
            "decision_status": "ACCEPTED",
            "intervention_status": "OTP_VERIFIED",
            "order_status": order.status,
        })

        # ---------------------------------------------------------------------
        # Step 4: Dispatch & Failed First Delivery Attempt
        # ---------------------------------------------------------------------
        # Progress order to SHIPPED
        DeliveryService.record_delivery_event(
            org_id=org_id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type="READY_TO_SHIP",
                event_source="COURIER_WEBHOOK_SIMULATED",
                is_simulated=True,
            ),
            session=session,
            actor_user_id=user_id,
        )
        DeliveryService.record_delivery_event(
            org_id=org_id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type="SHIPPED",
                carrier_name="Delhivery (Simulated)",
                tracking_number="DEL-DEMO-100200",
                event_source="COURIER_WEBHOOK_SIMULATED",
                is_simulated=True,
            ),
            session=session,
            actor_user_id=user_id,
        )
        DeliveryService.record_delivery_event(
            org_id=org_id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type="OUT_FOR_DELIVERY",
                event_source="COURIER_WEBHOOK_SIMULATED",
                is_simulated=True,
            ),
            session=session,
            actor_user_id=user_id,
        )
        # Attempt 1 fails
        DeliveryService.record_delivery_event(
            org_id=org_id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type="DELIVERY_ATTEMPT_FAILED",
                reason_code="CUSTOMER_UNAVAILABLE",
                reason_description="Customer phone unreachable at apartment gate.",
                event_source="COURIER_WEBHOOK_SIMULATED",
                is_simulated=True,
            ),
            session=session,
            actor_user_id=user_id,
        )
        transcript.append({
            "step": 4,
            "title": "Delivery Attempt Failed (NDR Triggered)",
            "details": "Courier scan reported DELIVERY_ATTEMPT_FAILED: CUSTOMER_UNAVAILABLE. Order transitioned to NDR.",
            "order_status": order.status,
            "reason_code": "CUSTOMER_UNAVAILABLE",
        })

        # ---------------------------------------------------------------------
        # Step 5: NDR Case Inspection
        # ---------------------------------------------------------------------
        ndr_case = session.scalar(
            select(NDRCase).where(NDRCase.org_id == org_id, NDRCase.order_id == order.id)
        )
        transcript.append({
            "step": 5,
            "title": "NDR Recovery Case Created",
            "details": f"Case #{ndr_case.case_number} created in queue. Priority: {ndr_case.priority}. Recommended Action: {ndr_case.recommended_recovery_action}.",
            "case_number": ndr_case.case_number,
            "case_status": ndr_case.status,
            "expected_recovery_lift": str(ndr_case.expected_recovery_lift),
        })

        # ---------------------------------------------------------------------
        # Step 6: Recovery Action Executed
        # ---------------------------------------------------------------------
        DeliveryService.record_ndr_action(
            org_id=org_id,
            case_id=ndr_case.id,
            action_in=NDRActionCreate(
                action_type="CONTACT_CUSTOMER",
                contact_method="WHATSAPP",
                customer_response="Customer confirmed they were at office; requested delivery tomorrow after 3 PM.",
            ),
            session=session,
            actor_user_id=user_id,
        )
        DeliveryService.record_ndr_action(
            org_id=org_id,
            case_id=ndr_case.id,
            action_in=NDRActionCreate(
                action_type="SCHEDULE_REATTEMPT",
                reattempt_date=datetime.now(timezone.utc),
            ),
            session=session,
            actor_user_id=user_id,
        )
        transcript.append({
            "step": 6,
            "title": "Recovery Interventions Executed",
            "details": "Operator contacted customer via WhatsApp and scheduled reattempt. Status updated to REATTEMPT_SCHEDULED.",
            "case_status": ndr_case.status,
            "customer_contacted": ndr_case.customer_contacted,
        })

        # ---------------------------------------------------------------------
        # Step 7: Successful Reattempt Delivery
        # ---------------------------------------------------------------------
        DeliveryService.record_delivery_event(
            org_id=org_id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type="OUT_FOR_DELIVERY",
                event_source="COURIER_WEBHOOK_SIMULATED",
                is_simulated=True,
            ),
            session=session,
            actor_user_id=user_id,
        )
        DeliveryService.record_delivery_event(
            org_id=org_id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type="DELIVERED",
                event_source="COURIER_WEBHOOK_SIMULATED",
                is_simulated=True,
            ),
            session=session,
            actor_user_id=user_id,
        )
        transcript.append({
            "step": 7,
            "title": "Reattempt Successful — Order DELIVERED",
            "details": "Courier delivered package on second attempt. Cash collected. NDR case automatically marked RESOLVED_DELIVERED.",
            "order_status": order.status,
            "case_status": ndr_case.status,
        })

        # ---------------------------------------------------------------------
        # Step 8: Authoritative Financial Reconciliation
        # ---------------------------------------------------------------------
        recon = ReconciliationService.reconcile_order(
            org_id=org_id,
            order_id=order.id,
            session=session,
            actor_user_id=user_id,
        )
        transcript.append({
            "step": 8,
            "title": "Authoritative Financial Reconciliation",
            "details": f"Final Realized Contribution reconciled: ₹{recon.realized_contribution}. Reverse shipping avoided. Sunk forward shipping accounted for once.",
            "order_value_gmv": str(recon.order_value),
            "collected_revenue": str(recon.collected_revenue),
            "cogs": str(recon.cogs),
            "forward_shipping": str(recon.forward_shipping_cost),
            "reverse_shipping": str(recon.reverse_shipping_cost),
            "payment_fee": str(recon.payment_fee),
            "pre_dispatch_cost": str(recon.pre_dispatch_intervention_cost),
            "ndr_recovery_cost": str(recon.ndr_recovery_intervention_cost),
            "realized_contribution": str(recon.realized_contribution),
            "reconciliation_status": recon.reconciliation_status,
        })

        return {
            "status": "success",
            "order_id": str(order.id),
            "external_order_id": order.external_order_id,
            "steps_completed": len(transcript),
            "transcript": transcript,
            "final_reconciliation": {
                "order_value": str(recon.order_value),
                "collected_revenue": str(recon.collected_revenue),
                "realized_contribution": str(recon.realized_contribution),
                "status": recon.reconciliation_status,
            },
        }
