"""Comprehensive Customer Journey and Tenant Isolation Verification Test.

Covers:
Register -> Onboarding -> Create Order -> Evaluate Decision -> Confirm Order
-> Record Shipment Events (READY_TO_SHIP -> SHIPPED -> OUT_FOR_DELIVERY)
-> Create NDR Case (DELIVERY_ATTEMPT_FAILED)
-> Record Recovery / RTO (REQUEST_RTO)
-> Reconcile Financial Ledger (Authoritative Realized Contribution)
-> Register Merchant B and verify complete multi-tenant data isolation
-> Logout / Token Revocation -> verify protected endpoints require authentication.
"""

from decimal import Decimal
import pytest


def test_complete_fresh_customer_journey_and_isolation(client):
    # -------------------------------------------------------------------------
    # 1. Register Merchant A
    # -------------------------------------------------------------------------
    reg_a = client.post("/api/v1/auth/register", json={
        "email": "fresh_merchant_a@example.com",
        "password": "StrongPassword123!",
        "full_name": "Merchant Alpha",
        "organization_name": "Alpha Brands Pvt Ltd",
    })
    assert reg_a.status_code == 201, reg_a.text
    token_a = reg_a.json()["access_token"]

    orgs_res_a = client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token_a}"})
    assert orgs_res_a.status_code == 200, orgs_res_a.text
    org_a_id = str(orgs_res_a.json()[0]["org_id"])
    headers_a = {
        "Authorization": f"Bearer {token_a}",
        "X-Org-Id": org_a_id,
    }

    # -------------------------------------------------------------------------
    # 2. Complete Onboarding for Merchant A (Set Unit Economics)
    # -------------------------------------------------------------------------
    onboard_a = client.put("/api/v1/economics", json={
        "default_cogs_percent": "32.00",
        "forward_shipping_cost": "75.00",
        "reverse_shipping_cost": "70.00",
        "packaging_cost": "22.00",
        "cod_carrier_fee": "38.00",
        "cod_fee_incurred_on": "UPON_DELIVERY_ONLY",
        "payment_gateway_percent": "2.10",
        "payment_gateway_flat": "3.00",
        "allow_auto_cancel": False,
    }, headers=headers_a)
    assert onboard_a.status_code == 200, onboard_a.text

    # -------------------------------------------------------------------------
    # 3. Create Order for Merchant A
    # -------------------------------------------------------------------------
    create_ord_a = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-ALPHA-1001",
        "order_value": "1250.00",
        "payment_method": "COD",
        "customer_name": "Rahul Verma",
        "customer_phone": "+919876543210",
        "customer_email": "rahul@example.com",
        "shipping_address1": "Flat 402, Sunset Heights",
        "shipping_address2": "Koramangala 4th Block",
        "shipping_city": "Bengaluru",
        "shipping_pincode": "560034",
    }, headers=headers_a)
    assert create_ord_a.status_code == 201, create_ord_a.text
    order_a = create_ord_a.json()
    order_a_id = order_a["id"]
    assert order_a["status"] == "PENDING"
    assert Decimal(order_a["order_value"]) == Decimal("1250.00")

    # -------------------------------------------------------------------------
    # 4. Evaluate Order Decision
    # -------------------------------------------------------------------------
    eval_a = client.post(f"/api/v1/orders/{order_a_id}/evaluate", headers=headers_a)
    assert eval_a.status_code == 200, eval_a.text
    eval_data_a = eval_a.json()
    assert eval_data_a["recommended_action"] in {
        "SHIP_AS_IS", "VERIFY_OTP", "INCENTIVIZE_PREPAID", "MANUAL_REVIEW", "HOLD_CANCEL"
    }
    assert "operational_probability_assumptions" in eval_data_a["explanation_data"]
    assert "uncertainty_disclosure" in eval_data_a["explanation_data"]

    # -------------------------------------------------------------------------
    # 5. Confirm Order
    # -------------------------------------------------------------------------
    confirm_res = client.post(
        f"/api/v1/orders/{order_a_id}/confirm",
        headers=headers_a,
    )
    assert confirm_res.status_code == 200, confirm_res.text
    assert confirm_res.json()["status"] == "CONFIRMED"

    # -------------------------------------------------------------------------
    # 6. Record Shipment Lifecycle Events
    # -------------------------------------------------------------------------
    # Event: READY_TO_SHIP
    evt_rts = client.post("/api/v1/delivery/events", json={
        "order_id": order_a_id,
        "event_type": "READY_TO_SHIP",
        "carrier_name": "Delhivery",
        "tracking_number": "TRK-ALPHA-001",
    }, headers=headers_a)
    assert evt_rts.status_code == 201, evt_rts.text

    # Event: SHIPPED
    evt_ship = client.post("/api/v1/delivery/events", json={
        "order_id": order_a_id,
        "event_type": "SHIPPED",
        "carrier_name": "Delhivery",
        "tracking_number": "TRK-ALPHA-001",
    }, headers=headers_a)
    assert evt_ship.status_code == 201, evt_ship.text

    # Event: OUT_FOR_DELIVERY
    evt_ofd = client.post("/api/v1/delivery/events", json={
        "order_id": order_a_id,
        "event_type": "OUT_FOR_DELIVERY",
        "carrier_name": "Delhivery",
        "tracking_number": "TRK-ALPHA-001",
    }, headers=headers_a)
    assert evt_ofd.status_code == 201, evt_ofd.text

    # -------------------------------------------------------------------------
    # 7. Create NDR Case (Failed Delivery Attempt)
    # -------------------------------------------------------------------------
    evt_ndr = client.post("/api/v1/delivery/events", json={
        "order_id": order_a_id,
        "event_type": "DELIVERY_ATTEMPT_FAILED",
        "reason_code": "CUSTOMER_UNAVAILABLE",
        "reason_description": "Customer door was locked; phone unreachable",
        "carrier_name": "Delhivery",
        "tracking_number": "TRK-ALPHA-001",
    }, headers=headers_a)
    assert evt_ndr.status_code == 201, evt_ndr.text

    # Verify NDR case exists
    ndr_list = client.get("/api/v1/delivery/ndr", headers=headers_a)
    assert ndr_list.status_code == 200
    cases = ndr_list.json()["cases"]
    assert len(cases) >= 1
    target_case = next(c for c in cases if c["order_id"] == order_a_id)
    case_id = target_case["id"]
    assert target_case["status"] == "OPEN"
    assert target_case["attempt_count"] == 1

    # -------------------------------------------------------------------------
    # 8. Record Recovery Action / RTO Closure
    # -------------------------------------------------------------------------
    rto_action = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={
            "action_type": "REQUEST_RTO",
            "closure_reason": "Customer unreachable after 2 followups, return parcel",
        },
        headers=headers_a,
    )
    assert rto_action.status_code == 200, rto_action.text
    assert rto_action.json()["status"] == "RESOLVED_RTO"

    # Verify order status transitioned to RTO
    ord_check = client.get(f"/api/v1/orders/{order_a_id}", headers=headers_a)
    assert ord_check.status_code == 200
    assert ord_check.json()["status"] == "RTO"

    # -------------------------------------------------------------------------
    # 9. Reconcile Authoritative Financial Ledger
    # -------------------------------------------------------------------------
    recon_res = client.get(f"/api/v1/orders/{order_a_id}/reconciliation", headers=headers_a)
    assert recon_res.status_code == 200, recon_res.text
    recon_data = recon_res.json()
    assert recon_data["terminal_status"] == "RTO"
    assert recon_data["reconciliation_status"] == "SETTLED"
    assert Decimal(recon_data["collected_revenue"]) == Decimal("0.00")
    assert Decimal(recon_data["forward_shipping_cost"]) == Decimal("75.00")
    assert Decimal(recon_data["reverse_shipping_cost"]) == Decimal("70.00")
    # Under UPON_DELIVERY_ONLY, payment fee on RTO is 0.00
    assert Decimal(recon_data["payment_fee"]) == Decimal("0.00")
    # Realized contribution is negative loss on RTO
    assert Decimal(recon_data["realized_contribution"]) < 0

    # -------------------------------------------------------------------------
    # 10. Register Merchant B
    # -------------------------------------------------------------------------
    reg_b = client.post("/api/v1/auth/register", json={
        "email": "fresh_merchant_b@example.com",
        "password": "StrongPassword456!",
        "full_name": "Merchant Beta",
        "organization_name": "Beta D2C Ltd",
    })
    assert reg_b.status_code == 201
    token_b = reg_b.json()["access_token"]
    orgs_res_b = client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token_b}"})
    assert orgs_res_b.status_code == 200
    org_b_id = str(orgs_res_b.json()[0]["org_id"])
    headers_b = {
        "Authorization": f"Bearer {token_b}",
        "X-Org-Id": org_b_id,
    }

    # -------------------------------------------------------------------------
    # 11. Multi-Tenant Cross-Access Isolation Checks
    # -------------------------------------------------------------------------
    # Merchant B tries to read Merchant A's order -> 404
    denied_order = client.get(f"/api/v1/orders/{order_a_id}", headers=headers_b)
    assert denied_order.status_code == 404

    # Merchant B tries to read Merchant A's NDR case recommendation -> 404
    denied_ndr = client.get(f"/api/v1/delivery/ndr/{case_id}/recommendation", headers=headers_b)
    assert denied_ndr.status_code == 404

    # Merchant B tries to read Merchant A's reconciliation -> 404
    denied_recon = client.get(f"/api/v1/orders/{order_a_id}/reconciliation", headers=headers_b)
    assert denied_recon.status_code == 404

    # Merchant B orders list does NOT include Merchant A's order
    orders_b = client.get("/api/v1/orders", headers=headers_b).json()["orders"]
    assert not any(o["id"] == order_a_id for o in orders_b)

    # -------------------------------------------------------------------------
    # 12. Sign Out / Token Revocation Verification
    # -------------------------------------------------------------------------
    logout_res = client.post("/api/v1/auth/logout", headers=headers_a)
    assert logout_res.status_code == 200

    # Token A is now revoked; subsequent requests return 401 Unauthorized
    revoked_access = client.get("/api/v1/orders", headers=headers_a)
    assert revoked_access.status_code == 401

    # Completely unauthenticated requests return 401 Unauthorized
    unauth_access = client.get("/api/v1/orders")
    assert unauth_access.status_code == 401
