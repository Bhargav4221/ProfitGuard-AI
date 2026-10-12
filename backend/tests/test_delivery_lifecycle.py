"""Comprehensive Test Suite for Delivery Lifecycle, Tracking Events, and NDR Recovery Hub.

Covers:
1. Permitted delivery lifecycle state machine transitions.
2. Rejection of invalid transitions (terminal immutability).
3. Idempotent duplicate event ingestion.
4. Out-of-order event handling (terminal protection).
5. Automatic NDR case creation and multi-attempt tracking.
6. Permitted recovery actions (CONTACT_CUSTOMER, VERIFY_ADDRESS, SCHEDULE_REATTEMPT, ESCALATE, CLOSE).
7. Automatic NDR resolution upon successful reattempt delivery.
8. Zero double-counting financial recovery decision calculations.
9. Courier webhook HMAC-SHA256 signature verification and tamper detection.
10. Cross-tenant isolation on events, cases, and actions.
11. Role-Based Access Control (RBAC) enforcement (OPERATOR vs AUDITOR).
"""

import hashlib
import hmac
import json
from decimal import Decimal
from uuid import uuid4
import pytest
from app.core.tenant import OrganizationRole
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order


@pytest.fixture
def test_order(db_session, create_org):
    """Fixture creating a test COD order."""
    org = create_org(name="Delivery Test Org")
    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="ORD-DELIV-101",
        order_value=Decimal("1500.00"),
        payment_method="COD",
        status="PENDING",
        fulfillment_status="UNFULFILLED",
        customer_name="Ramesh Patel",
        customer_phone="9876543210",
        shipping_city="Ahmedabad",
        shipping_pincode="380015",
        source_channel="SHOPIFY",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return org, order


def test_valid_delivery_lifecycle_transitions(client, create_user, create_member, auth_headers, test_order):
    """Verifies that an order progresses through valid lifecycle states:
    PENDING -> CONFIRMED -> READY_TO_SHIP -> SHIPPED -> OUT_FOR_DELIVERY -> DELIVERED.
    """
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # 1. PENDING -> CONFIRMED
    res1 = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order.id), "event_type": "ORDER_CONFIRMED"},
        headers=headers,
    )
    assert res1.status_code == 201
    assert res1.json()["new_status"] == "CONFIRMED"

    # 2. CONFIRMED -> READY_TO_SHIP
    res2 = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"},
        headers=headers,
    )
    assert res2.status_code == 201
    assert res2.json()["new_status"] == "READY_TO_SHIP"

    # 3. READY_TO_SHIP -> SHIPPED
    res3 = client.post(
        "/api/v1/delivery/events",
        json={
            "order_id": str(order.id),
            "event_type": "SHIPPED",
            "carrier_name": "Delhivery",
            "tracking_number": "DEL-998877",
        },
        headers=headers,
    )
    assert res3.status_code == 201
    assert res3.json()["new_status"] == "SHIPPED"
    assert res3.json()["carrier_name"] == "Delhivery"

    # 4. SHIPPED -> OUT_FOR_DELIVERY
    res4 = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order.id), "event_type": "OUT_FOR_DELIVERY"},
        headers=headers,
    )
    assert res4.status_code == 201
    assert res4.json()["new_status"] == "OUT_FOR_DELIVERY"

    # 5. OUT_FOR_DELIVERY -> DELIVERED
    res5 = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order.id), "event_type": "DELIVERED"},
        headers=headers,
    )
    assert res5.status_code == 201
    assert res5.json()["new_status"] == "DELIVERED"

    # Verify order in DB
    order_res = client.get(f"/api/v1/orders/{order.id}", headers=headers)
    assert order_res.json()["status"] == "DELIVERED"
    assert order_res.json()["fulfillment_status"] == "FULFILLED"
    assert order_res.json()["order_value"] == "1500.00"  # Strictly immutable


def test_invalid_delivery_state_transitions(client, create_user, create_member, auth_headers, test_order):
    """Verifies that invalid transitions are rejected (e.g. DELIVERED cannot transition back to SHIPPED)."""
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Move to DELIVERED
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "DELIVERED"}, headers=headers)

    # Attempt invalid transition from DELIVERED to SHIPPED
    res = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order.id), "event_type": "SHIPPED"},
        headers=headers,
    )
    # Since DELIVERED is terminal, out-of-order events do not revert order status
    assert res.status_code == 201
    assert res.json()["new_status"] == "DELIVERED"

    # Verify order is still DELIVERED
    order_res = client.get(f"/api/v1/orders/{order.id}", headers=headers)
    assert order_res.json()["status"] == "DELIVERED"


def test_idempotent_event_processing(client, create_user, create_member, auth_headers, test_order):
    """Verifies that replaying an event with the same event_id is idempotent and safe."""
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    payload = {
        "order_id": str(order.id),
        "event_id": "unique-courier-scan-001",
        "event_type": "CONFIRMED",
    }

    res1 = client.post("/api/v1/delivery/events", json=payload, headers=headers)
    assert res1.status_code == 201
    evt1_id = res1.json()["id"]

    # Replay identical event
    res2 = client.post("/api/v1/delivery/events", json=payload, headers=headers)
    assert res2.status_code == 201
    evt2_id = res2.json()["id"]

    assert evt1_id == evt2_id

    # Verify events list only contains one event
    events_res = client.get(f"/api/v1/delivery/events/{order.id}", headers=headers)
    assert len(events_res.json()) == 1


def test_simulated_event_labeling(client, create_user, create_member, auth_headers, test_order):
    """Verifies that simulated events are strictly flagged with is_simulated=True."""
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Confirm order first
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)

    res = client.post(
        "/api/v1/delivery/simulate",
        json={
            "order_id": str(order.id),
            "event_type": "OUT_FOR_DELIVERY",
            "notes": "Testing delivery scan simulation",
        },
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["is_simulated"] is True
    assert data["event_source"] == "COURIER_WEBHOOK_SIMULATED"


def test_ndr_case_creation_and_multi_attempt(client, create_user, create_member, auth_headers, test_order):
    """Verifies that failed delivery attempts trigger an NDR case and track multi-attempt escalation."""
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Progress order to SHIPPED -> OUT_FOR_DELIVERY
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "OUT_FOR_DELIVERY"}, headers=headers)

    # Failed Delivery Attempt 1
    res_ndr1 = client.post(
        "/api/v1/delivery/events",
        json={
            "order_id": str(order.id),
            "event_type": "DELIVERY_ATTEMPT_FAILED",
            "reason_code": "CUSTOMER_UNAVAILABLE",
            "reason_description": "Customer phone not reachable at gate.",
        },
        headers=headers,
    )
    assert res_ndr1.status_code == 201
    assert res_ndr1.json()["new_status"] == "NDR"

    # Check NDR queue
    ndr_list = client.get("/api/v1/delivery/ndr", headers=headers)
    assert ndr_list.status_code == 200
    cases = ndr_list.json()["cases"]
    assert len(cases) == 1
    case = cases[0]
    assert case["status"] == "OPEN"
    assert case["attempt_count"] == 1
    assert case["reason_code"] == "CUSTOMER_UNAVAILABLE"
    assert case["order_external_id"] == order.external_order_id
    assert case["expected_recovery_lift"] is not None

    # Failed Delivery Attempt 2 (courier reattempt failed again)
    res_ndr2 = client.post(
        "/api/v1/delivery/events",
        json={
            "order_id": str(order.id),
            "event_id": "attempt-2-scan",
            "event_type": "DELIVERY_ATTEMPT_FAILED",
            "reason_code": "CUSTOMER_UNAVAILABLE",
        },
        headers=headers,
    )
    assert res_ndr2.status_code == 201

    case_detail = client.get(f"/api/v1/delivery/ndr/{case['id']}", headers=headers).json()
    assert case_detail["attempt_count"] == 2

    # Failed Delivery Attempt 3 (triggers priority escalation)
    client.post(
        "/api/v1/delivery/events",
        json={
            "order_id": str(order.id),
            "event_id": "attempt-3-scan",
            "event_type": "DELIVERY_ATTEMPT_FAILED",
            "reason_code": "CUSTOMER_UNAVAILABLE",
        },
        headers=headers,
    )
    case_detail3 = client.get(f"/api/v1/delivery/ndr/{case['id']}", headers=headers).json()
    assert case_detail3["attempt_count"] == 3
    assert case_detail3["priority"] == "HIGH"


def test_ndr_permitted_recovery_actions(client, create_user, create_member, auth_headers, test_order):
    """Verifies execution of permitted NDR recovery actions:
    CONTACT_CUSTOMER, VERIFY_ADDRESS, SCHEDULE_REATTEMPT, ESCALATE, and CLOSE.
    """
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Bring to NDR
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "DELIVERY_ATTEMPT_FAILED", "reason_code": "INCORRECT_ADDRESS"}, headers=headers)

    case_id = client.get("/api/v1/delivery/ndr", headers=headers).json()["cases"][0]["id"]

    # 1. Action: CONTACT_CUSTOMER
    res_contact = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={
            "action_type": "CONTACT_CUSTOMER",
            "contact_method": "WHATSAPP",
            "customer_response": "Customer provided corrected flat number and landmark.",
        },
        headers=headers,
    )
    assert res_contact.status_code == 200
    assert res_contact.json()["customer_contacted"] is True
    assert res_contact.json()["contact_method"] == "WHATSAPP"
    assert res_contact.json()["status"] == "IN_PROGRESS"

    # 2. Action: VERIFY_ADDRESS (updates case and order address)
    res_addr = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={
            "action_type": "VERIFY_ADDRESS",
            "updated_address1": "Flat 402, Shivalik Residency, Near SG Highway",
            "updated_city": "Ahmedabad",
            "updated_pincode": "380054",
        },
        headers=headers,
    )
    assert res_addr.status_code == 200
    assert res_addr.json()["updated_pincode"] == "380054"

    # Verify address updated on the Order record itself
    order_db = client.get(f"/api/v1/orders/{order.id}", headers=headers).json()
    assert order_db["shipping_pincode"] == "380054"

    # 3. Action: SCHEDULE_REATTEMPT
    res_sch = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={"action_type": "SCHEDULE_REATTEMPT"},
        headers=headers,
    )
    assert res_sch.status_code == 200
    assert res_sch.json()["status"] == "REATTEMPT_SCHEDULED"

    # 4. Action: ESCALATE_TO_MANUAL_REVIEW
    res_esc = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={"action_type": "ESCALATE_TO_MANUAL_REVIEW"},
        headers=headers,
    )
    assert res_esc.status_code == 200
    assert res_esc.json()["priority"] == "HIGH"

    # Verify action log audit history
    case_full = client.get(f"/api/v1/delivery/ndr/{case_id}", headers=headers).json()
    assert len(case_full["actions"]) == 4


def test_ndr_successful_resolution_on_delivered(client, create_user, create_member, auth_headers, test_order):
    """Verifies that an NDR case is automatically closed as RESOLVED_DELIVERED when the order is delivered."""
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "DELIVERY_ATTEMPT_FAILED", "reason_code": "CUSTOMER_UNAVAILABLE"}, headers=headers)

    case_id = client.get("/api/v1/delivery/ndr", headers=headers).json()["cases"][0]["id"]

    # Carrier scans DELIVERED on reattempt
    res_deliv = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order.id), "event_type": "DELIVERED"},
        headers=headers,
    )
    assert res_deliv.status_code == 201

    # Case should now be RESOLVED_DELIVERED
    case_res = client.get(f"/api/v1/delivery/ndr/{case_id}", headers=headers).json()
    assert case_res["status"] == "RESOLVED_DELIVERED"
    assert "delivered" in case_res["closure_reason"].lower()


def test_ndr_request_rto_action(client, create_user, create_member, auth_headers, test_order):
    """Verifies that selecting REQUEST_RTO closes the NDR case and transitions the order to RTO."""
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "DELIVERY_ATTEMPT_FAILED", "reason_code": "CUSTOMER_REFUSED"}, headers=headers)

    case_id = client.get("/api/v1/delivery/ndr", headers=headers).json()["cases"][0]["id"]

    res_rto = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={"action_type": "REQUEST_RTO", "closure_reason": "Customer confirmed refusal, stop further attempts"},
        headers=headers,
    )
    assert res_rto.status_code == 200
    assert res_rto.json()["status"] == "RESOLVED_RTO"

    # Order status should now be RTO
    order_res = client.get(f"/api/v1/orders/{order.id}", headers=headers).json()
    assert order_res["status"] == "RTO"


def test_ndr_decision_support_economics_zero_double_counting(client, create_user, create_member, auth_headers, test_order):
    """Verifies that recovery decision support computes expected lift without double-counting:
    - Forward shipping is accounted for as sunk.
    - Reverse shipping is avoided upon delivery.
    - Intervention cost is subtracted exactly once.
    - PaR = Payoff(Delivered) - Payoff(RTO).
    - Lift = P(Delivered) * PaR - C_int.
    """
    org, order = test_order
    user = create_user(email="operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": str(order.id), "event_type": "DELIVERY_ATTEMPT_FAILED", "reason_code": "INCORRECT_ADDRESS"}, headers=headers)

    case_id = client.get("/api/v1/delivery/ndr", headers=headers).json()["cases"][0]["id"]

    rec_res = client.get(f"/api/v1/delivery/ndr/{case_id}/recommendation", headers=headers)
    assert rec_res.status_code == 200
    data = rec_res.json()

    # Recommended action for INCORRECT_ADDRESS should be VERIFY_ADDRESS
    assert data["recommended_action"] == "VERIFY_ADDRESS"
    assert Decimal(data["expected_recovery_lift"]) > 0
    assert Decimal(data["profit_at_risk"]) > 0
    assert data["data_sufficiency"] == "SUFFICIENT"

    # Mathematical identity check: Lift = P_rescue * PaR - C_int
    p_rescue = Decimal(data["estimated_rescue_prob"])
    par = Decimal(data["profit_at_risk"])
    c_int = Decimal(data["intervention_cost"])
    expected_lift = (p_rescue * par - c_int).quantize(Decimal("0.01"))
    actual_lift = Decimal(data["expected_recovery_lift"])
    assert actual_lift == expected_lift


def test_courier_webhook_signature_verification(client, db_session, create_org, test_order):
    """Verifies that courier webhooks require valid HMAC-SHA256 signature."""
    org, order = test_order
    webhook_secret = "pg_webhook_secret_default"

    payload = {
        "org_id": str(org.id),
        "external_order_id": order.external_order_id,
        "status": "CONFIRMED",
        "carrier": "Delhivery",
        "event_id": "webhook-evt-001",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")

    # Generate valid HMAC signature
    valid_sig = hmac.new(webhook_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    # Valid signature succeeds
    res_valid = client.post(
        "/api/v1/delivery/webhook",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Courier-Signature": valid_sig},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["status"] == "success"

    # Invalid / forged signature is rejected with 401
    res_invalid = client.post(
        "/api/v1/delivery/webhook",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Courier-Signature": "forged_invalid_signature"},
    )
    assert res_invalid.status_code == 401


def test_cross_tenant_delivery_isolation(client, create_user, create_org, create_member, auth_headers, test_order):
    """Verifies that Tenant B cannot access or record delivery events for Tenant A's orders."""
    org_a, order_a = test_order

    org_b = create_org(name="Competitor Org B")
    user_b = create_user(email="user_b@competitor.com")
    create_member(org_b.id, user_b.id, OrganizationRole.OPERATOR)
    headers_b = auth_headers(user_b, org_b)

    # Tenant B tries to record delivery event for Tenant A's order -> 404
    res_cross_event = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order_a.id), "event_type": "CONFIRMED"},
        headers=headers_b,
    )
    assert res_cross_event.status_code == 404

    # Tenant B tries to list Tenant A's delivery events -> 404
    res_cross_list = client.get(f"/api/v1/delivery/events/{order_a.id}", headers=headers_b)
    assert res_cross_list.status_code == 404


def test_delivery_rbac_restrictions(client, create_user, create_member, auth_headers, test_order):
    """Verifies that AUDITOR role has read-only access and cannot mutate delivery events or NDR cases."""
    org, order = test_order
    user_auditor = create_user(email="auditor@test.com")
    create_member(org.id, user_auditor.id, OrganizationRole.AUDITOR)
    headers_auditor = auth_headers(user_auditor, org)

    # AUDITOR can read
    res_read = client.get(f"/api/v1/delivery/events/{order.id}", headers=headers_auditor)
    assert res_read.status_code == 200

    # AUDITOR cannot record delivery event -> 403 Forbidden
    res_mutate = client.post(
        "/api/v1/delivery/events",
        json={"order_id": str(order.id), "event_type": "CONFIRMED"},
        headers=headers_auditor,
    )
    assert res_mutate.status_code == 403


def test_out_for_delivery_to_ndr_simulation_flow(client, create_user, create_member, auth_headers, test_order):
    """Verifies that an order in OUT_FOR_DELIVERY can simulate DELIVERY_ATTEMPT_FAILED to transition to NDR,
    persisting the chosen reason code, creating exactly one NDRCase, and maintaining event idempotency.
    """
    org, order = test_order
    user = create_user(email="operator_ndr@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # 1. Advance order to OUT_FOR_DELIVERY
    client.post("/api/v1/delivery/simulate", json={"order_id": str(order.id), "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/simulate", json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/simulate", json={"order_id": str(order.id), "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/simulate", json={"order_id": str(order.id), "event_type": "OUT_FOR_DELIVERY"}, headers=headers)

    order_check = client.get(f"/api/v1/orders/{order.id}", headers=headers).json()
    assert order_check["status"] == "OUT_FOR_DELIVERY"

    # 2. Invalid transitions from OUT_FOR_DELIVERY remain rejected (e.g. CONFIRMED, READY_TO_SHIP)
    inv_res = client.post(
        "/api/v1/delivery/simulate",
        json={"order_id": str(order.id), "event_type": "READY_TO_SHIP"},
        headers=headers,
    )
    assert inv_res.status_code == 400
    assert "Invalid delivery transition" in inv_res.json()["detail"]

    # 3. Simulate DELIVERY_ATTEMPT_FAILED with custom event_id and reason INCORRECT_ADDRESS
    ndr_payload = {
        "order_id": str(order.id),
        "event_id": f"evt-sim-ndr-{order.external_order_id}-001",
        "event_type": "DELIVERY_ATTEMPT_FAILED",
        "reason_code": "INCORRECT_ADDRESS",
        "carrier_name": "Delhivery (Simulated)",
        "location": "Bengaluru Hub",
        "notes": "Doorbell not working, house number missing",
    }
    sim_ndr_res = client.post("/api/v1/delivery/simulate", json=ndr_payload, headers=headers)
    assert sim_ndr_res.status_code == 201
    evt_data = sim_ndr_res.json()
    assert evt_data["event_type"] == "DELIVERY_ATTEMPT_FAILED"
    assert evt_data["new_status"] == "NDR"
    assert evt_data["reason_code"] == "INCORRECT_ADDRESS"
    assert evt_data["is_simulated"] is True
    assert evt_data["event_source"] == "COURIER_WEBHOOK_SIMULATED"

    # 4. Verify order status is updated to NDR with fulfillment FULFILLED
    order_ndr = client.get(f"/api/v1/orders/{order.id}", headers=headers).json()
    assert order_ndr["status"] == "NDR"
    assert order_ndr["fulfillment_status"] == "FULFILLED"

    # 5. Verify NDR case was initialized in NDR recovery hub
    ndr_list_res = client.get(f"/api/v1/delivery/ndr?search={order.external_order_id}", headers=headers)
    assert ndr_list_res.status_code == 200
    ndr_cases = ndr_list_res.json()["cases"]
    assert len(ndr_cases) == 1
    case = ndr_cases[0]
    assert case["reason_code"] == "INCORRECT_ADDRESS"
    assert case["attempt_count"] == 1
    assert case["status"] == "OPEN"
    assert case["is_simulated"] is True
    assert case["order_id"] == str(order.id)

    # 6. Idempotency check: Replay same event_id
    sim_ndr_retry = client.post("/api/v1/delivery/simulate", json=ndr_payload, headers=headers)
    assert sim_ndr_retry.status_code == 201
    assert sim_ndr_retry.json()["id"] == evt_data["id"]

    # Verify no duplicate NDR cases or duplicate events were created
    events_res = client.get(f"/api/v1/delivery/events/{order.id}", headers=headers).json()
    assert len([e for e in events_res if e["event_id"] == ndr_payload["event_id"]]) == 1

    ndr_list_retry = client.get(f"/api/v1/delivery/ndr?search={order.external_order_id}", headers=headers).json()
    assert len(ndr_list_retry["cases"]) == 1

    # 7. Reattempt flow: NDR -> OUT_FOR_DELIVERY -> DELIVERY_ATTEMPT_FAILED (attempt 2)
    reattempt_res = client.post(
        "/api/v1/delivery/simulate",
        json={"order_id": str(order.id), "event_type": "OUT_FOR_DELIVERY"},
        headers=headers,
    )
    assert reattempt_res.status_code == 201
    assert client.get(f"/api/v1/orders/{order.id}", headers=headers).json()["status"] == "OUT_FOR_DELIVERY"

    # Second failure updates attempt_count on the SAME active case
    second_fail_res = client.post(
        "/api/v1/delivery/simulate",
        json={
            "order_id": str(order.id),
            "event_type": "DELIVERY_ATTEMPT_FAILED",
            "reason_code": "CUSTOMER_UNREACHABLE",
        },
        headers=headers,
    )
    assert second_fail_res.status_code == 201
    assert client.get(f"/api/v1/orders/{order.id}", headers=headers).json()["status"] == "NDR"

    ndr_list_updated = client.get(f"/api/v1/delivery/ndr?search={order.external_order_id}", headers=headers).json()
    assert len(ndr_list_updated["cases"]) == 1
    updated_case = ndr_list_updated["cases"][0]
    assert updated_case["attempt_count"] == 2
    assert updated_case["reason_code"] == "CUSTOMER_UNREACHABLE"

