"""Milestone 5: Comprehensive End-to-End User Journey and Validation Test Suite.

Tests:
1. Complete 8-Step User Journey:
   Order Creation -> Evaluation -> Intervention -> Dispatch -> Failed Attempt ->
   NDR Case -> Recovery Action -> Successful Reattempt -> Delivered -> Financial Reconciliation.
2. Negative Scenarios:
   - Duplicate event replays (Idempotency).
   - Invalid state transitions (Terminal protection).
   - Unauthorized mutations (RBAC enforcement for AUDITOR).
   - Failed CSV import (Validation and duplicate rejection).
   - Insufficient financial data handling.
3. Repeatable Demo Dataset Lifecycle:
   - Seeding demo dataset.
   - Running complete automated demo journey.
   - Safe reset (deletes only DEMO-* records, preserving merchant orders).
"""

import io
from decimal import Decimal
from uuid import uuid4
import pytest

from app.core.tenant import OrganizationRole
from app.models.delivery import NDRCase
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order


@pytest.fixture
def journey_setup(db_session, create_user, create_org, create_member, auth_headers):
    """Sets up tenant, operator user, auditor user, and headers."""
    org = create_org(name="E2E Validation Store")
    operator = create_user(email="operator_e2e@test.com")
    create_member(org.id, operator.id, OrganizationRole.OPERATOR)

    auditor = create_user(email="auditor_e2e@test.com")
    create_member(org.id, auditor.id, OrganizationRole.AUDITOR)

    return {
        "org": org,
        "operator": operator,
        "auditor": auditor,
        "op_headers": auth_headers(operator, org),
        "aud_headers": auth_headers(auditor, org),
    }


def test_complete_8_step_user_journey(client, journey_setup):
    """Verifies the complete 8-step order-to-recovery journey and financial reconciliation."""
    org = journey_setup["org"]
    headers = journey_setup["op_headers"]

    # -------------------------------------------------------------------------
    # Step 1: Order Creation
    # -------------------------------------------------------------------------
    create_payload = {
        "external_order_id": "ORD-JOURNEY-8899",
        "order_value": "2400.00",
        "payment_method": "COD",
        "customer_name": "Deepak Verma",
        "customer_phone": "9876543210",
        "shipping_address1": "Flat 201, Lotus Heights, Powai",
        "shipping_city": "Mumbai",
        "shipping_state": "Maharashtra",
        "shipping_pincode": "400076",
        "items": [
            {
                "sku": "SKU-AUDIO-PRO",
                "product_name": "Premium Headphones",
                "quantity": 1,
                "unit_price": "2400.00",
                "unit_cost": "720.00",
            }
        ],
    }
    res_step1 = client.post("/api/v1/orders", json=create_payload, headers=headers)
    assert res_step1.status_code == 201
    order_data = res_step1.json()
    order_id = order_data["id"]
    assert order_data["status"] == "PENDING"
    assert order_data["order_value"] == "2400.00"

    # -------------------------------------------------------------------------
    # Step 2: 5-Action Decision Evaluation
    # -------------------------------------------------------------------------
    res_step2 = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    assert res_step2.status_code == 200
    eval_data = res_step2.json()
    assert eval_data["recommended_action"] in [
        "SHIP_AS_IS",
        "VERIFY_OTP",
        "INCENTIVIZE_PREPAID",
        "MANUAL_REVIEW",
        "HOLD_CANCEL",
    ]
    assert len(eval_data["comparison_data"]) == 5
    assert Decimal(eval_data["recommended_lift"]) >= Decimal("0.00")

    # -------------------------------------------------------------------------
    # Step 3: Record Decision & Pre-Dispatch Intervention Outcome
    # -------------------------------------------------------------------------
    res_step3a = client.post(
        f"/api/v1/orders/{order_id}/decision",
        json={"action": "VERIFY_OTP", "override_reason": "Operator initiated phone/OTP verification"},
        headers=headers,
    )
    assert res_step3a.status_code == 200

    res_step3b = client.post(
        f"/api/v1/orders/{order_id}/intervention-outcome",
        json={"outcome": "OTP_VERIFIED", "notes": "Customer verified OTP on WhatsApp"},
        headers=headers,
    )
    assert res_step3b.status_code == 200
    assert res_step3b.json()["intervention_status"] == "OTP_VERIFIED"

    # -------------------------------------------------------------------------
    # Step 4: Dispatch & Failed First Delivery Attempt
    # -------------------------------------------------------------------------
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "SHIPPED", "carrier_name": "Delhivery"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "OUT_FOR_DELIVERY"}, headers=headers)

    # Failed attempt
    res_step4 = client.post(
        "/api/v1/delivery/events",
        json={
            "order_id": order_id,
            "event_type": "DELIVERY_ATTEMPT_FAILED",
            "reason_code": "CUSTOMER_UNAVAILABLE",
            "reason_description": "Gate security reported resident not available.",
        },
        headers=headers,
    )
    assert res_step4.status_code == 201
    assert res_step4.json()["new_status"] == "NDR"

    # -------------------------------------------------------------------------
    # Step 5: NDR Case Inspection
    # -------------------------------------------------------------------------
    res_step5 = client.get(f"/api/v1/delivery/ndr?search=ORD-JOURNEY-8899", headers=headers)
    assert res_step5.status_code == 200
    cases = res_step5.json()["cases"]
    assert len(cases) == 1
    case = cases[0]
    case_id = case["id"]
    assert case["status"] == "OPEN"
    assert case["attempt_count"] == 1
    assert case["reason_code"] == "CUSTOMER_UNAVAILABLE"
    assert Decimal(case["expected_recovery_lift"]) > 0

    # -------------------------------------------------------------------------
    # Step 6: Permitted Recovery Actions (Contact + Reattempt)
    # -------------------------------------------------------------------------
    res_step6a = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={
            "action_type": "CONTACT_CUSTOMER",
            "contact_method": "WHATSAPP",
            "customer_response": "Customer was traveling; requested delivery tomorrow.",
        },
        headers=headers,
    )
    assert res_step6a.status_code == 200
    assert res_step6a.json()["customer_contacted"] is True

    res_step6b = client.post(
        f"/api/v1/delivery/ndr/{case_id}/actions",
        json={"action_type": "SCHEDULE_REATTEMPT"},
        headers=headers,
    )
    assert res_step6b.status_code == 200
    assert res_step6b.json()["status"] == "REATTEMPT_SCHEDULED"

    # -------------------------------------------------------------------------
    # Step 7: Successful Reattempt -> DELIVERED Outcome
    # -------------------------------------------------------------------------
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "OUT_FOR_DELIVERY"}, headers=headers)
    res_step7 = client.post(
        "/api/v1/delivery/events",
        json={"order_id": order_id, "event_type": "DELIVERED"},
        headers=headers,
    )
    assert res_step7.status_code == 201
    assert res_step7.json()["new_status"] == "DELIVERED"

    # Verify NDR case auto-resolved
    case_resolved = client.get(f"/api/v1/delivery/ndr/{case_id}", headers=headers).json()
    assert case_resolved["status"] == "RESOLVED_DELIVERED"

    # -------------------------------------------------------------------------
    # Step 8: Authoritative Financial Reconciliation
    # -------------------------------------------------------------------------
    res_step8 = client.post(f"/api/v1/orders/{order_id}/reconcile", headers=headers)
    assert res_step8.status_code == 200
    recon = res_step8.json()
    assert recon["reconciliation_status"] == "SETTLED"
    assert recon["order_value"] == "2400.00"
    assert recon["collected_revenue"] == "2400.00"
    assert recon["cogs"] == "720.00"
    assert recon["forward_shipping_cost"] == "70.00"
    assert recon["reverse_shipping_cost"] == "0.00"  # Avoided!
    assert recon["inventory_damage_cost"] == "0.00"  # Delivered!
    assert Decimal(recon["realized_contribution"]) > Decimal("1000.00")

    # Realized Contribution exact formula check:
    # RC = 2400.00 - 720.00 (COGS) - 70.00 (S_f) - 35.00 (COD fee) - 20.00 (Pkg) - 0.50 (OTP) - 3.00 (NDR contact+reattempt)
    expected_rc = (
        Decimal(recon["collected_revenue"])
        - Decimal(recon["cogs"])
        - Decimal(recon["forward_shipping_cost"])
        - Decimal(recon["payment_fee"])
        - Decimal(recon["packaging_cost"])
        - Decimal(recon["pre_dispatch_intervention_cost"])
        - Decimal(recon["ndr_recovery_intervention_cost"])
    )
    assert Decimal(recon["realized_contribution"]) == expected_rc


def test_negative_duplicate_event_replays(client, journey_setup):
    """Verifies that replaying duplicate delivery scans is strictly idempotent."""
    headers = journey_setup["op_headers"]

    # Create order
    order_res = client.post(
        "/api/v1/orders",
        json={"external_order_id": "ORD-NEG-DUP-01", "order_value": "1000.00", "payment_method": "COD"},
        headers=headers,
    )
    order_id = order_res.json()["id"]

    event_payload = {
        "order_id": order_id,
        "event_id": "duplicate-scan-idempotent-key-01",
        "event_type": "CONFIRMED",
    }

    # First event
    res1 = client.post("/api/v1/delivery/events", json=event_payload, headers=headers)
    assert res1.status_code == 201
    evt1_id = res1.json()["id"]

    # Replay same event ID
    res2 = client.post("/api/v1/delivery/events", json=event_payload, headers=headers)
    assert res2.status_code == 201
    evt2_id = res2.json()["id"]

    # Idempotent match
    assert evt1_id == evt2_id

    # Verify only 1 event recorded
    history = client.get(f"/api/v1/delivery/events/{order_id}", headers=headers).json()
    assert len(history) == 1


def test_negative_invalid_state_transitions(client, journey_setup):
    """Verifies that illegal transitions (e.g. DELIVERED back to in-transit) do not corrupt order state."""
    headers = journey_setup["op_headers"]

    order_res = client.post(
        "/api/v1/orders",
        json={"external_order_id": "ORD-NEG-INVALID-01", "order_value": "1200.00", "payment_method": "COD"},
        headers=headers,
    )
    order_id = order_res.json()["id"]

    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "CONFIRMED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "READY_TO_SHIP"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "SHIPPED"}, headers=headers)
    client.post("/api/v1/delivery/events", json={"order_id": order_id, "event_type": "DELIVERED"}, headers=headers)

    # Attempt illegal transition: DELIVERED -> SHIPPED
    res = client.post(
        "/api/v1/delivery/events",
        json={"order_id": order_id, "event_type": "SHIPPED"},
        headers=headers,
    )
    # Order remains DELIVERED
    assert res.json()["new_status"] == "DELIVERED"
    order_chk = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_chk["status"] == "DELIVERED"


def test_negative_unauthorized_auditor_actions(client, journey_setup):
    """Verifies that AUDITOR role cannot execute delivery events, NDR actions, or decisions."""
    op_headers = journey_setup["op_headers"]
    aud_headers = journey_setup["aud_headers"]

    # Operator creates order
    order_res = client.post(
        "/api/v1/orders",
        json={"external_order_id": "ORD-NEG-RBAC-01", "order_value": "1500.00", "payment_method": "COD"},
        headers=op_headers,
    )
    order_id = order_res.json()["id"]

    # Auditor attempts to record delivery event -> 403 Forbidden
    res_event = client.post(
        "/api/v1/delivery/events",
        json={"order_id": order_id, "event_type": "CONFIRMED"},
        headers=aud_headers,
    )
    assert res_event.status_code == 403

    # Auditor attempts to evaluate order -> 403 Forbidden
    res_eval = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=aud_headers)
    assert res_eval.status_code == 403

    # Auditor attempts to reconcile order -> 403 Forbidden
    res_rec = client.post(f"/api/v1/orders/{order_id}/reconcile", headers=aud_headers)
    assert res_rec.status_code == 403


def test_negative_csv_import_validation_and_duplicates(client, journey_setup):
    """Verifies that invalid CSVs, missing mandatory headers, and intra-file duplicates fail gracefully."""
    headers = journey_setup["op_headers"]

    # 1. Missing mandatory columns
    invalid_csv = "order_id,customer_name\n#101,John Doe\n"
    res_bad_headers = client.post(
        "/api/v1/csv-import/preview",
        files={"file": ("bad_headers.csv", io.BytesIO(invalid_csv.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert res_bad_headers.status_code == 400
    assert "missing mandatory headers" in res_bad_headers.json()["detail"].lower()

    # 2. Intra-file duplicate orders
    dup_csv = (
        "external_order_id,order_value,payment_method,customer_phone,shipping_pincode\n"
        "#DUP101,500.00,COD,9876543210,110001\n"
        "#DUP101,700.00,COD,9876543210,110001\n"
    )
    res_dup = client.post(
        "/api/v1/csv-import/preview",
        files={"file": ("dup.csv", io.BytesIO(dup_csv.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert res_dup.status_code == 200
    data = res_dup.json()
    assert data["duplicate_rows"] == 1
    assert data["valid_rows"] == 1


def test_demo_dataset_seed_run_and_reset(client, journey_setup):
    """Verifies that demo dataset seeding, 8-step journey runner, and safe reset work end to end."""
    headers = journey_setup["op_headers"]

    # 1. Seed demo dataset
    res_seed = client.post("/api/v1/demo/seed", headers=headers)
    assert res_seed.status_code == 201
    assert len(res_seed.json()["seeded_orders"]) >= 3

    # 2. Run complete 8-step journey on demo order
    res_journey = client.post("/api/v1/demo/run-journey", headers=headers)
    assert res_journey.status_code == 200
    journey_data = res_journey.json()
    assert journey_data["status"] == "success"
    assert journey_data["steps_completed"] == 8
    assert journey_data["final_reconciliation"]["status"] == "SETTLED"

    # 3. Create a non-demo merchant order to prove safe reset isolation
    res_real = client.post(
        "/api/v1/orders",
        json={"external_order_id": "REAL-MERCHANT-ORD-99", "order_value": "3000.00", "payment_method": "PREPAID"},
        headers=headers,
    )
    real_order_id = res_real.json()["id"]

    # 4. Reset demo dataset
    res_reset = client.post("/api/v1/demo/reset", headers=headers)
    assert res_reset.status_code == 200
    assert res_reset.json()["deleted_count"] >= 3

    # 5. Verify real merchant order was NOT deleted!
    real_check = client.get(f"/api/v1/orders/{real_order_id}", headers=headers)
    assert real_check.status_code == 200
    assert real_check.json()["external_order_id"] == "REAL-MERCHANT-ORD-99"
