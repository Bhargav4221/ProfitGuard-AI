"""Tests for Judge-Controlled Manual Order Creation and Interactive Decision Flow."""

from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
client = TestClient(app)


def test_manual_order_creation_and_financial_validation():
    """Verifies that a merchant/judge can manually create an order with line items."""
    unique = str(uuid.uuid4())[:8]
    email = f"judge_{unique}@profitguard.ai"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Judge Evaluator",
            "organization_name": f"Judge Brand {unique}",
        },
    )
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]
    orgs_res = client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_res.json()[0]["org_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    # 1. Invalid phone number should fail with 422
    invalid_phone_res = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "external_order_id": f"ORD-ERR-PHONE-{unique}",
            "order_value": "1299.00",
            "payment_method": "COD",
            "customer_phone": "12345",  # Invalid Indian phone
            "shipping_pincode": "560001",
        },
    )
    assert invalid_phone_res.status_code == 422

    # 2. Invalid pincode should fail with 422
    invalid_pincode_res = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "external_order_id": f"ORD-ERR-PIN-{unique}",
            "order_value": "1299.00",
            "payment_method": "COD",
            "customer_phone": "9876543210",
            "shipping_pincode": "012345",  # Cannot start with 0
        },
    )
    assert invalid_pincode_res.status_code == 422

    # 3. Valid order creation with line item COGS
    order_res = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "external_order_id": f"ORD-JUDGE-{unique}",
            "order_value": "1499.00",
            "payment_method": "COD",
            "customer_name": "Rohan Sharma",
            "customer_phone": "9876543210",
            "customer_email": "rohan@example.com",
            "shipping_address1": "Flat 402, Lotus Greens, Indiranagar",
            "shipping_city": "Bengaluru",
            "shipping_state": "Karnataka",
            "shipping_pincode": "560038",
            "items": [
                {
                    "sku": "SKU-PREM-SHIRT",
                    "product_name": "Premium Linen Shirt",
                    "quantity": 1,
                    "unit_price": "1499.00",
                    "unit_cost": "450.00",
                }
            ],
        },
    )
    assert order_res.status_code == 201
    created_order = order_res.json()
    order_id = created_order["id"]
    assert created_order["external_order_id"] == f"ORD-JUDGE-{unique}"
    assert Decimal(created_order["order_value"]) == Decimal("1499.00")
    assert len(created_order["items"]) == 1
    assert Decimal(created_order["items"][0]["unit_cost"]) == Decimal("450.00")

    # 4. Verify tenant summary metrics updated
    summary_res = client.get("/api/v1/orders/summary", headers=headers)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_orders"] >= 1
    assert Decimal(str(summary["total_gmv"])) >= Decimal("1499.00")
    assert summary["payment_method_breakdown"].get("COD", 0) >= 1

    # 5. Interactive Decision Evaluation
    eval_res = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    evaluation = eval_res.json()
    assert "comparison_data" in evaluation
    actions = {act["action"]: act for act in evaluation["comparison_data"]}
    assert "SHIP_AS_IS" in actions
    assert "VERIFY_OTP" in actions
    assert "INCENTIVIZE_PREPAID" in actions
    assert "MANUAL_REVIEW" in actions
    assert "HOLD_CANCEL" in actions

    # 6. Record decision override / selection
    dec_res = client.post(
        f"/api/v1/orders/{order_id}/decision",
        headers=headers,
        json={"action": "VERIFY_OTP", "override_reason": "Judge interactive verification test"},
    )
    assert dec_res.status_code == 200
    assert dec_res.json()["selected_action"] == "VERIFY_OTP"

    # 7. Record intervention outcome (OTP confirmed)
    out_res = client.post(
        f"/api/v1/orders/{order_id}/intervention-outcome",
        headers=headers,
        json={"outcome": "OTP_VERIFIED", "notes": "Customer confirmed order via OTP"},
    )
    assert out_res.status_code == 200
    assert out_res.json()["intervention_status"] == "OTP_VERIFIED"

    # 8. Simulate delivery lifecycle events according to state machine rules
    for event_type, carrier in [
        ("READY_TO_SHIP", None),
        ("SHIPPED", "BlueDart Express"),
        ("DELIVERED", "BlueDart Express"),
    ]:
        sim_res = client.post(
            "/api/v1/delivery/simulate",
            headers=headers,
            json={
                "order_id": order_id,
                "event_type": event_type,
                "carrier_name": carrier,
                "notes": f"Event {event_type} [SIMULATED]",
            },
        )
        assert sim_res.status_code == 201

    # 9. Settle authoritative realized financial reconciliation
    recon_res = client.post(f"/api/v1/orders/{order_id}/reconcile", headers=headers)
    assert recon_res.status_code == 200
    recon = recon_res.json()
    assert recon["reconciliation_status"] == "SETTLED"
    assert Decimal(str(recon["order_value"])) == Decimal("1499.00")
    assert Decimal(str(recon["cogs"])) == Decimal("450.00")
    assert Decimal(str(recon["realized_contribution"])) > Decimal("0.00")


def test_order_confirm_and_resume_lifecycle():
    """Verifies complete permitted lifecycle:
    PENDING -> CONFIRMED -> READY_TO_SHIP -> SHIPPED -> OUT_FOR_DELIVERY -> NDR -> DELIVERED
    and confirms that invalid jumps (e.g. PENDING -> NDR) are strictly blocked with 400.
    """
    unique = str(uuid.uuid4())[:8]
    email = f"lifecycle_{unique}@profitguard.ai"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Lifecycle Evaluator",
            "organization_name": f"Lifecycle Brand {unique}",
        },
    )
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]
    orgs_res = client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_res.json()[0]["org_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    # 1. Create fresh order in PENDING
    order_res = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "external_order_id": f"ORD-LC-{unique}",
            "order_value": "1899.00",
            "payment_method": "COD",
            "customer_name": "Aarav Gupta",
            "customer_phone": "9876543211",
            "shipping_pincode": "110001",
            "items": [
                {
                    "sku": "SKU-WATCH-01",
                    "product_name": "Classic Watch",
                    "quantity": 1,
                    "unit_price": "1899.00",
                    "unit_cost": "600.00",
                }
            ],
        },
    )
    assert order_res.status_code == 201
    order = order_res.json()
    order_id = order["id"]
    assert order["status"] == "PENDING"
    assert order["fulfillment_status"] == "UNFULFILLED"

    # 2. Attempt invalid jump: PENDING -> NDR (must be rejected with 400)
    bad_jump_res = client.post(
        "/api/v1/delivery/simulate",
        headers=headers,
        json={
            "order_id": order_id,
            "event_type": "DELIVERY_ATTEMPT_FAILED",
            "reason_code": "CUSTOMER_UNAVAILABLE",
        },
    )
    assert bad_jump_res.status_code == 400
    assert "Invalid delivery transition" in bad_jump_res.json()["detail"]

    # 3. Confirm order via dedicated /confirm endpoint
    confirm_res = client.post(f"/api/v1/orders/{order_id}/confirm", headers=headers)
    assert confirm_res.status_code == 200
    confirmed_order = confirm_res.json()
    assert confirmed_order["status"] == "CONFIRMED"
    assert confirmed_order["fulfillment_status"] == "UNFULFILLED"

    # Idempotent call to /confirm returns successfully without error
    confirm_again_res = client.post(f"/api/v1/orders/{order_id}/confirm", headers=headers)
    assert confirm_again_res.status_code == 200
    assert confirm_again_res.json()["status"] == "CONFIRMED"

    # 4. Advance: CONFIRMED -> READY_TO_SHIP
    rts_res = client.post(
        "/api/v1/delivery/simulate",
        headers=headers,
        json={"order_id": order_id, "event_type": "READY_TO_SHIP"},
    )
    assert rts_res.status_code == 201
    order_data = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_data["status"] == "READY_TO_SHIP"
    assert order_data["fulfillment_status"] == "UNFULFILLED"

    # 5. Advance: READY_TO_SHIP -> SHIPPED
    ship_res = client.post(
        "/api/v1/delivery/simulate",
        headers=headers,
        json={"order_id": order_id, "event_type": "SHIPPED", "carrier_name": "Delhivery"},
    )
    assert ship_res.status_code == 201
    order_data = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_data["status"] == "SHIPPED"
    assert order_data["fulfillment_status"] == "FULFILLED"

    # 6. Advance: SHIPPED -> OUT_FOR_DELIVERY
    ofd_res = client.post(
        "/api/v1/delivery/simulate",
        headers=headers,
        json={"order_id": order_id, "event_type": "OUT_FOR_DELIVERY"},
    )
    assert ofd_res.status_code == 201
    order_data = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_data["status"] == "OUT_FOR_DELIVERY"
    assert order_data["fulfillment_status"] == "FULFILLED"

    # 7. Advance: OUT_FOR_DELIVERY -> DELIVERY_ATTEMPT_FAILED (triggers NDR)
    ndr_res = client.post(
        "/api/v1/delivery/simulate",
        headers=headers,
        json={
            "order_id": order_id,
            "event_type": "DELIVERY_ATTEMPT_FAILED",
            "reason_code": "CUSTOMER_UNAVAILABLE",
        },
    )
    assert ndr_res.status_code == 201
    order_data = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_data["status"] == "NDR"
    assert order_data["fulfillment_status"] == "FULFILLED"

    # Verify NDR case was initialized
    ndr_list_res = client.get(f"/api/v1/delivery/ndr?search=ORD-LC-{unique}", headers=headers)
    assert ndr_list_res.status_code == 200
    ndr_cases = ndr_list_res.json()["cases"]
    assert len(ndr_cases) == 1
    assert ndr_cases[0]["reason_code"] == "CUSTOMER_UNAVAILABLE"

    # 8. Advance: NDR -> OUT_FOR_DELIVERY (reattempt)
    reattempt_res = client.post(
        "/api/v1/delivery/simulate",
        headers=headers,
        json={"order_id": order_id, "event_type": "OUT_FOR_DELIVERY"},
    )
    assert reattempt_res.status_code == 201
    order_data = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_data["status"] == "OUT_FOR_DELIVERY"

    # 9. Terminal settlement: OUT_FOR_DELIVERY -> DELIVERED
    deliv_res = client.post(
        "/api/v1/delivery/simulate",
        headers=headers,
        json={"order_id": order_id, "event_type": "DELIVERED"},
    )
    assert deliv_res.status_code == 201
    order_data = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_data["status"] == "DELIVERED"
    assert order_data["fulfillment_status"] == "FULFILLED"

    # Verify audit event history has all events
    events_res = client.get(f"/api/v1/delivery/events/{order_id}", headers=headers)
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 6
    assert all(e["is_simulated"] for e in events if e["event_source"] == "COURIER_WEBHOOK_SIMULATED")


def test_hold_and_resume_order():
    """Verifies that placing an order on HOLD and calling /resume lifts the hold."""
    unique = str(uuid.uuid4())[:8]
    email = f"hold_{unique}@profitguard.ai"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Hold Evaluator",
            "organization_name": f"Hold Brand {unique}",
        },
    )
    token = reg_res.json()["access_token"]
    orgs_res = client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_res.json()[0]["org_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    # 1. Create order
    order_res = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "external_order_id": f"ORD-HOLD-{unique}",
            "order_value": "999.00",
            "payment_method": "COD",
            "customer_phone": "9876543212",
            "shipping_pincode": "400001",
        },
    )
    order_id = order_res.json()["id"]

    # 2. Cannot resume an order that is not on HOLD
    not_hold_res = client.post(f"/api/v1/orders/{order_id}/resume", headers=headers)
    assert not_hold_res.status_code == 400

    # 3. Put order on HOLD via update
    patch_res = client.patch(
        f"/api/v1/orders/{order_id}",
        headers=headers,
        json={"status": "HOLD"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "HOLD"
    assert patch_res.json()["fulfillment_status"] == "HOLD"

    # 4. Resume order to CONFIRMED
    resume_res = client.post(f"/api/v1/orders/{order_id}/resume", headers=headers)
    assert resume_res.status_code == 200
    resumed = resume_res.json()
    assert resumed["status"] == "CONFIRMED"
    assert resumed["fulfillment_status"] == "UNFULFILLED"


def test_patch_order_status_validation():
    """Verifies PATCH /orders/{order_id} enforces state machine transition guards."""
    unique = str(uuid.uuid4())[:8]
    email = f"guard_{unique}@profitguard.ai"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Guard Evaluator",
            "organization_name": f"Guard Brand {unique}",
        },
    )
    token = reg_res.json()["access_token"]
    orgs_res = client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_res.json()[0]["org_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    order_res = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "external_order_id": f"ORD-GUARD-{unique}",
            "order_value": "599.00",
            "payment_method": "PREPAID",
            "customer_phone": "9876543213",
            "shipping_pincode": "600001",
        },
    )
    order_id = order_res.json()["id"]

    # Invalid jump: PENDING -> DELIVERED
    invalid_patch = client.patch(
        f"/api/v1/orders/{order_id}",
        headers=headers,
        json={"status": "DELIVERED"},
    )
    assert invalid_patch.status_code == 400
    assert "Invalid transition" in invalid_patch.json()["detail"]

    # Valid transition: PENDING -> CANCELLED
    valid_patch = client.patch(
        f"/api/v1/orders/{order_id}",
        headers=headers,
        json={"status": "CANCELLED"},
    )
    assert valid_patch.status_code == 200
    assert valid_patch.json()["status"] == "CANCELLED"

