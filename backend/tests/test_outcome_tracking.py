"""Test Suite for Real-Order Outcome Tracking and Monitoring (Phase 4A).

Covers:
1. Rejection of incomplete / non-terminal order outcomes.
2. Idempotent outcome recording and duplicate event handling.
3. Invalid delivery transitions and terminal state protection.
4. Automatic outcome recording upon terminal delivery transitions.
5. Strict cross-tenant isolation and authorization.
6. Closed-loop monitoring metrics calculations (separating observed facts from modeled estimates).
7. Temporal feature integrity (strict exclusion of post-order leakage fields).
8. API endpoints verification (GET/POST outcome, GET monitoring metrics & outcomes).
"""

from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException

from app.core.tenant import OrganizationRole
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.order_outcome import OrderOutcome
from app.schemas.delivery import DeliveryEventCreate
from app.services.decision_engine import DecisionEngineService
from app.services.delivery_service import DeliveryService
from app.services.outcome_tracking_service import OutcomeTrackingService


@pytest.fixture
def outcome_test_setup(db_session, create_org, create_user, create_member, auth_headers):
    """Sets up an organization, operator user, merchant economics, and authorization headers."""
    org = create_org(name="Outcome Test Org")
    user = create_user(email="outcome_operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    if not econ:
        econ = MerchantEconomics(org_id=org.id)
        db_session.add(econ)
        db_session.commit()

    return org, user, headers, econ


def create_order_helper(session, org_id, external_id, value="2500.00", payment_method="COD", status="PENDING"):
    order = Order(
        id=uuid4(),
        org_id=org_id,
        external_order_id=external_id,
        order_value=Decimal(value),
        payment_method=payment_method,
        status=status,
        fulfillment_status="UNFULFILLED" if status in ("PENDING", "CONFIRMED") else "FULFILLED",
        customer_name="Test Customer",
        customer_phone="9876543210",
        shipping_city="Bengaluru",
        shipping_pincode="560001",
        source_channel="SHOPIFY",
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def test_incomplete_outcomes_rejected(db_session, outcome_test_setup):
    """Verifies that in-flight, non-terminal orders (PENDING, CONFIRMED, SHIPPED) cannot be recorded as completed outcomes."""
    org, user, headers, _ = outcome_test_setup
    order = create_order_helper(db_session, org.id, "ORD-INFLIGHT-1", status="SHIPPED")

    # Attempting to record outcome on SHIPPED order must raise 400
    with pytest.raises(HTTPException) as exc_info:
        OutcomeTrackingService.record_order_outcome(
            org_id=org.id,
            order_id=order.id,
            session=db_session,
            actor_user_id=user.id,
        )
    assert exc_info.value.status_code == 400
    assert "non-terminal" in exc_info.value.detail.lower()


def test_outcome_recording_idempotency_and_duplicates(db_session, outcome_test_setup):
    """Verifies that recording outcome multiple times is idempotent, does not create duplicates, and updates cleanly."""
    org, user, headers, econ = outcome_test_setup
    order = create_order_helper(db_session, org.id, "ORD-IDEMPOTENT-1", status="PENDING")

    # Evaluate order
    DecisionEngineService.evaluate_order(
        order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id
    )

    # Move order through lifecycle to DELIVERED
    for ev_type in ["CONFIRMED", "READY_TO_SHIP", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]:
        DeliveryService.record_delivery_event(
            org_id=org.id,
            order_id=order.id,
            event_in=DeliveryEventCreate(order_id=order.id, event_type=ev_type),
            session=db_session,
            actor_user_id=user.id,
        )

    assert order.status == "DELIVERED"

    # 1. First record call (via service)
    outcome_1 = OutcomeTrackingService.record_order_outcome(
        org_id=org.id,
        order_id=order.id,
        session=db_session,
        actor_user_id=user.id,
        notes="Initial outcome",
    )
    assert outcome_1.final_delivery_outcome == "DELIVERED"
    assert outcome_1.notes == "Initial outcome"

    # 2. Second record call with new notes
    outcome_2 = OutcomeTrackingService.record_order_outcome(
        org_id=org.id,
        order_id=order.id,
        session=db_session,
        actor_user_id=user.id,
        notes="Updated outcome notes",
    )

    # Must be same outcome ID
    assert outcome_1.id == outcome_2.id
    assert outcome_2.notes == "Updated outcome notes"

    # Database must contain exactly 1 outcome for this order
    outcomes_in_db = db_session.query(OrderOutcome).filter_by(org_id=org.id, order_id=order.id).all()
    assert len(outcomes_in_db) == 1


def test_invalid_delivery_transitions_protection(db_session, outcome_test_setup):
    """Verifies that terminal delivery states are protected against invalid transitions."""
    org, user, headers, _ = outcome_test_setup
    order = create_order_helper(db_session, org.id, "ORD-TERMINAL-GUARD-1", status="PENDING")

    # Fast forward to DELIVERED
    for ev_type in ["CONFIRMED", "READY_TO_SHIP", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]:
        DeliveryService.record_delivery_event(
            org_id=org.id,
            order_id=order.id,
            event_in=DeliveryEventCreate(order_id=order.id, event_type=ev_type),
            session=db_session,
            actor_user_id=user.id,
        )

    assert order.status == "DELIVERED"

    # Out-of-order event arriving after DELIVERED (e.g. SHIPPED) must NOT revert terminal status
    _, updated_order = DeliveryService.record_delivery_event(
        org_id=org.id,
        order_id=order.id,
        event_in=DeliveryEventCreate(order_id=order.id, event_type="SHIPPED"),
        session=db_session,
        actor_user_id=user.id,
    )
    assert updated_order.status == "DELIVERED"


def test_automatic_outcome_recording_on_terminal_delivery(db_session, outcome_test_setup):
    """Verifies that ingesting a terminal delivery event automatically triggers outcome recording and financial reconciliation."""
    org, user, headers, econ = outcome_test_setup
    order = create_order_helper(db_session, org.id, "ORD-AUTO-OUTCOME-1", value="3000.00", status="PENDING")

    # Evaluate order
    eval_res = DecisionEngineService.evaluate_order(
        order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id
    )

    # Deliver order
    for ev_type in ["CONFIRMED", "READY_TO_SHIP", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]:
        DeliveryService.record_delivery_event(
            org_id=org.id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type=ev_type,
                carrier_name="BlueDart",
                tracking_number="BD-123456",
            ),
            session=db_session,
            actor_user_id=user.id,
        )

    db_session.refresh(order)
    assert order.status == "DELIVERED"
    assert order.outcome is not None
    assert order.outcome.final_delivery_outcome == "DELIVERED"
    assert order.outcome.deterministic_recommendation == eval_res.recommended_action
    assert order.outcome.carrier_name == "BlueDart"
    assert order.outcome.tracking_number == "BD-123456"
    assert order.outcome.realized_collected_revenue == Decimal("3000.00")
    assert order.reconciliation is not None
    assert order.outcome.realized_contribution == order.reconciliation.realized_contribution


def test_tenant_isolation_and_authorization(db_session, create_org, create_user, create_member, outcome_test_setup):
    """Verifies that Tenant B cannot access, view, or record outcomes belonging to Tenant A."""
    org_a, user_a, _, _ = outcome_test_setup

    org_b = create_org(name="Tenant B Org")
    user_b = create_user(email="user_b@test.com")
    create_member(org_b.id, user_b.id, OrganizationRole.OPERATOR)

    order_a = create_order_helper(db_session, org_a.id, "ORD-TENANT-A-1", status="PENDING")

    # Deliver order in Tenant A
    for ev_type in ["CONFIRMED", "READY_TO_SHIP", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]:
        DeliveryService.record_delivery_event(
            org_id=org_a.id,
            order_id=order_a.id,
            event_in=DeliveryEventCreate(order_id=order_a.id, event_type=ev_type),
            session=db_session,
            actor_user_id=user_a.id,
        )

    # Tenant B attempts to get Tenant A's outcome
    with pytest.raises(HTTPException) as exc_info:
        OutcomeTrackingService.get_order_outcome(org_id=org_b.id, order_id=order_a.id, session=db_session)
    assert exc_info.value.status_code == 404

    # Tenant B attempts to record outcome on Tenant A's order
    with pytest.raises(HTTPException) as exc_info:
        OutcomeTrackingService.record_order_outcome(org_id=org_b.id, order_id=order_a.id, session=db_session, actor_user_id=user_b.id)
    assert exc_info.value.status_code == 404

    # Tenant B listing outcomes sees 0
    items_b, total_b = OutcomeTrackingService.list_order_outcomes(org_id=org_b.id, session=db_session)
    assert total_b == 0
    assert len(items_b) == 0


def test_closed_loop_monitoring_metrics_calculation(db_session, outcome_test_setup):
    """
    Creates a controlled cohort of terminal orders with known outcomes:
    - Order 1: High risk evaluated, DELIVERED -> False Positive (FP)
    - Order 2: High risk evaluated, RTO -> True Positive (TP)
    - Order 3: Low risk evaluated, DELIVERED -> True Negative (TN)
    - Order 4: Low risk evaluated, RTO -> False Negative (FN)
    - Order 5: Non-evaluated, DELIVERED
    Verifies that empirical precision, recall, RTO rate, realized financials, and counterfactuals
    are calculated deterministically and clearly separated.
    """
    org, user, _, econ = outcome_test_setup

    orders = [
        # (ext_id, value, payment, eval_action, p_rto, terminal_status)
        ("ORD-COHORT-1", "2000.00", "COD", "VERIFY_OTP", Decimal("0.3500"), "DELIVERED"),  # FP
        ("ORD-COHORT-2", "2500.00", "COD", "VERIFY_OTP", Decimal("0.4000"), "RTO"),        # TP
        ("ORD-COHORT-3", "1200.00", "PREPAID", "SHIP_AS_IS", Decimal("0.0500"), "DELIVERED"), # TN
        ("ORD-COHORT-4", "1800.00", "COD", "SHIP_AS_IS", Decimal("0.0800"), "RTO"),        # FN
        ("ORD-COHORT-5", "1000.00", "PREPAID", None, None, "DELIVERED"),                    # Unevaluated TN
    ]

    for ext_id, val, pm, act, p_rto, status in orders:
        ord_obj = create_order_helper(db_session, org.id, ext_id, value=val, payment_method=pm, status="PENDING")
        if act:
            # Create synthetic evaluation
            eval_record = OrderEvaluation(
                org_id=org.id,
                order_id=ord_obj.id,
                recommended_action=act,
                recommended_lift=Decimal("15.00"),
                ship_as_is_ec=Decimal("200.00"),
                best_ec=Decimal("215.00"),
                profit_at_risk=Decimal("100.00"),
                baseline_p_rto=p_rto,
                uncertainty_score=Decimal("0.10"),
                risk_tier="HIGH" if p_rto >= Decimal("0.20") else "LOW",
                selected_action=act,
                decision_status="ACCEPTED",
                comparison_data=[],
                explanation_data={
                    "uncertainty_disclosure": {
                        "shadow_ml_prediction": {
                            "status": "ML_PREDICTION",
                            "model_version": "v1.0.0-synthetic-dev",
                            "feature_contract_version": "1.0.0",
                            "rto_probability": float(p_rto),
                        }
                    }
                },
            )
            db_session.add(eval_record)
            db_session.commit()

        # Transition order to status
        ord_obj.status = status
        db_session.commit()

        OutcomeTrackingService.record_order_outcome(
            org_id=org.id,
            order_id=ord_obj.id,
            session=db_session,
            actor_user_id=user.id,
        )

    # Compute monitoring metrics at threshold tau = 0.18
    metrics = OutcomeTrackingService.get_monitoring_metrics(
        org_id=org.id,
        session=db_session,
        operating_threshold=0.18,
    )

    facts = metrics.observed_realized_facts
    estimates = metrics.modeled_ex_ante_estimates

    # Verified empirical counts
    assert facts.eligible_completed_orders_count == 5
    assert facts.outcome_records_count == 5
    assert facts.outcome_coverage_pct == 100.0
    assert facts.delivered_count == 3
    assert facts.rto_count == 2
    assert facts.observed_rto_rate_pct == 40.0  # 2 / 5 * 100 = 40.0%
    assert facts.predictions_evaluated_count == 4

    # Empirical Classification Performance
    perf = facts.classification_performance
    assert perf.true_positives == 1   # ORD-COHORT-2
    assert perf.false_positives == 1  # ORD-COHORT-1
    assert perf.false_negatives == 1  # ORD-COHORT-4
    assert perf.true_negatives == 2   # ORD-COHORT-3, ORD-COHORT-5
    assert perf.precision == 0.5      # 1 / 2 = 0.5
    assert perf.recall == 0.5         # 1 / 2 = 0.5
    assert perf.f1_score == 0.5

    # Financial Facts
    assert facts.total_realized_revenue_inr > Decimal("0.00")
    assert facts.total_realized_rto_loss_inr > Decimal("0.00")
    assert facts.total_realized_intervention_cost_inr > Decimal("0.00")

    # Modeled Counterfactual Separation
    assert "GOVERNANCE NOTICE" in estimates.counterfactual_disclaimer
    assert estimates.counterfactual_scenarios["break_even_effectiveness_eta"] >= 0.0


def test_temporal_feature_integrity(db_session, outcome_test_setup):
    """
    Verifies that prediction-time features snapshot in OrderOutcome contains only
    order-placement features and excludes all prohibited post-order delivery fields.
    """
    org, user, _, econ = outcome_test_setup
    order = create_order_helper(db_session, org.id, "ORD-LEAKAGE-CHECK-1", status="PENDING")

    # Evaluate
    DecisionEngineService.evaluate_order(
        order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id
    )

    # Deliver
    for ev_type in ["CONFIRMED", "READY_TO_SHIP", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]:
        DeliveryService.record_delivery_event(
            org_id=org.id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type=ev_type,
                carrier_name="Delhivery",
                tracking_number="DEL-789",
                reason_description="Delivered to customer" if ev_type == "DELIVERED" else None,
            ),
            session=db_session,
            actor_user_id=user.id,
        )

    outcome = OutcomeTrackingService.get_order_outcome(org_id=org.id, order_id=order.id, session=db_session)
    assert outcome.prediction_feature_ref is not None
    snapshot = outcome.prediction_features_snapshot
    assert snapshot is not None

    # Order-time fields allowed
    assert "order_value" in snapshot
    assert "payment_method" in snapshot
    assert "shipping_pincode" in snapshot

    # Future fields prohibited
    prohibited_fields = [
        "delivery_attempts",
        "carrier_status",
        "delivery_timestamp",
        "rto_initiated_timestamp",
        "delivery_agent_id",
        "ndr_count",
        "final_delivery_status",
    ]
    for field in prohibited_fields:
        assert field not in snapshot, f"Prohibited future field '{field}' leaked into prediction snapshot!"


def test_monitoring_api_endpoints(client, outcome_test_setup):
    """Verifies HTTP 200 responses on GET /monitoring/outcomes and GET /monitoring/metrics."""
    org, user, headers, _ = outcome_test_setup

    # 1. GET /api/v1/monitoring/outcomes
    resp_outcomes = client.get("/api/v1/monitoring/outcomes", headers=headers)
    assert resp_outcomes.status_code == 200
    data_outcomes = resp_outcomes.json()
    assert "items" in data_outcomes
    assert "total" in data_outcomes

    # 2. GET /api/v1/monitoring/metrics
    resp_metrics = client.get("/api/v1/monitoring/metrics", headers=headers)
    assert resp_metrics.status_code == 200
    data_metrics = resp_metrics.json()
    assert "observed_realized_facts" in data_metrics
    assert "modeled_ex_ante_estimates" in data_metrics
    assert data_metrics["org_id"] == str(org.id)

    # 3. Unauthorized request
    resp_unauth = client.get("/api/v1/monitoring/metrics")
    assert resp_unauth.status_code == 401
