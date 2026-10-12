from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from app.core.tenant import OrganizationRole
from app.models.audit_log import AuditLog
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.schemas.economics import MerchantEconomicsBase
from app.services.decision_engine import DecisionEngineService, DecisionAssumptions
from app.services.reconciliation_service import ReconciliationService


def test_decision_engine_fixture_reproduction(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies the engine produces the exact numerical values specified in Fixtures 1-9."""
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme D2C Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Economics fixture setup (matches Fixture constants)
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.default_cogs_percent = Decimal("30.00")
    econ.forward_shipping_cost = Decimal("70.00")
    econ.reverse_shipping_cost = Decimal("65.00")
    econ.packaging_cost = Decimal("20.00")
    econ.cod_carrier_fee = Decimal("35.00")
    econ.cod_fee_incurred_on = "UPON_DELIVERY_ONLY"
    econ.payment_gateway_percent = Decimal("2.00")
    econ.payment_gateway_flat = Decimal("3.00")
    econ.inventory_damage_rate = Decimal("0.0500")
    econ.otp_verification_cost = Decimal("0.50")
    econ.manual_review_cost = Decimal("18.00")
    econ.prepaid_incentive_discount = Decimal("50.00")
    econ.prepaid_comms_cost = Decimal("0.50")
    econ.allow_auto_cancel = True
    db_session.commit()

    # Create COD order with V = 1000.00
    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-FIXTURE-100",
        "order_value": "1000.00",
        "payment_method": "COD",
        "customer_name": "Test Customer",
        "shipping_address1": "House 10, MG Road",
        "shipping_address2": "Indiranagar Phase 1",
        "shipping_city": "Bengaluru",
        "shipping_pincode": "560038",
    }, headers=headers)
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    # Evaluate order with override_p_rto = 0.30 to verify exact test fixture math
    order = db_session.get(Order, order_id)
    from app.services.decision_engine import DecisionEngineService
    eval_record = DecisionEngineService.evaluate_order(
        order=order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.3000"),
    )

    # Check 5 actions match exact fixture expectations:
    comp_map = {a["action"]: a for a in eval_record.comparison_data}

    # Fixture 5: SHIP_AS_IS
    assert Decimal(str(comp_map["SHIP_AS_IS"]["expected_contribution"])) == Decimal("351.50")
    assert Decimal(str(comp_map["SHIP_AS_IS"]["lift_vs_ship_as_is"])) == Decimal("0.00")

    # Fixture 6: VERIFY_OTP
    assert Decimal(str(comp_map["VERIFY_OTP"]["expected_contribution"])) == Decimal("363.70")
    assert Decimal(str(comp_map["VERIFY_OTP"]["lift_vs_ship_as_is"])) == Decimal("12.20")

    # Fixture 7: INCENTIVIZE_PREPAID
    assert Decimal(str(comp_map["INCENTIVIZE_PREPAID"]["expected_contribution"])) == Decimal("381.00")
    assert Decimal(str(comp_map["INCENTIVIZE_PREPAID"]["lift_vs_ship_as_is"])) == Decimal("29.50")

    # Fixture 8: MANUAL_REVIEW
    assert Decimal(str(comp_map["MANUAL_REVIEW"]["expected_contribution"])) == Decimal("382.40")
    assert Decimal(str(comp_map["MANUAL_REVIEW"]["lift_vs_ship_as_is"])) == Decimal("30.90")

    # Fixture 9: HOLD_CANCEL
    assert Decimal(str(comp_map["HOLD_CANCEL"]["expected_contribution"])) == Decimal("0.00")

    # Best recommendation is MANUAL_REVIEW (highest expected contribution: 382.40)
    assert eval_record.recommended_action == "MANUAL_REVIEW"
    assert eval_record.best_ec == Decimal("382.40")
    assert eval_record.recommended_lift == Decimal("30.90")


def test_prepaid_order_disqualifies_incentivize_prepaid(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Create PREPAID order
    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-PREPAID-1",
        "order_value": "1200.00",
        "payment_method": "PREPAID",
    }, headers=headers)
    order_id = order_res.json()["id"]

    eval_res = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    data = eval_res.json()

    prep_action = [a for a in data["comparison_data"] if a["action"] == "INCENTIVIZE_PREPAID"][0]
    assert prep_action["is_policy_eligible"] is False
    assert "already prepaid" in prep_action["disqualification_reason"].lower()


def test_hold_cancel_disqualification_when_auto_cancel_disabled(client, create_user, create_org, create_member, auth_headers, db_session):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Ensure allow_auto_cancel is False
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = False
    db_session.commit()

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-NOCANCEL",
        "order_value": "500.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    eval_res = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    data = eval_res.json()

    cancel_action = [a for a in data["comparison_data"] if a["action"] == "HOLD_CANCEL"][0]
    assert cancel_action["is_policy_eligible"] is False
    assert "allow_auto_cancel" in cancel_action["disqualification_reason"]


def test_high_order_value_safety_cap_policy_guard(client, create_user, create_org, create_member, auth_headers, db_session):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Safety cap = 3500.00
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.safety_value_cap = Decimal("3500.00")
    db_session.commit()

    # Create order above safety cap: ₹5,000.00
    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-HIGH-VAL",
        "order_value": "5000.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    eval_res = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    data = eval_res.json()

    # SHIP_AS_IS must be disqualified because order value exceeds safety cap
    ship_action = [a for a in data["comparison_data"] if a["action"] == "SHIP_AS_IS"][0]
    assert ship_action["is_policy_eligible"] is False
    assert "exceeds safety cap" in ship_action["disqualification_reason"]
    # Recommended action must be a verification action (OTP or Review)
    assert data["recommended_action"] in {"VERIFY_OTP", "MANUAL_REVIEW", "INCENTIVIZE_PREPAID"}


def test_order_decision_record_accept_and_override(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-DECISION-1",
        "order_value": "800.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    # 1. Evaluate order
    eval_res = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    rec_action = eval_res.json()["recommended_action"]

    # 2. Accept recommended action
    accept_res = client.post(f"/api/v1/orders/{order_id}/decision", json={
        "action": rec_action,
    }, headers=headers)
    assert accept_res.status_code == 200
    accept_data = accept_res.json()
    assert accept_data["decision_status"] == "ACCEPTED"
    assert accept_data["selected_action"] == rec_action

    # 3. Override without reason -> fails with 400
    other_action = "HOLD_CANCEL" if rec_action != "HOLD_CANCEL" else "SHIP_AS_IS"
    fail_override = client.post(f"/api/v1/orders/{order_id}/decision", json={
        "action": other_action,
    }, headers=headers)
    assert fail_override.status_code == 400
    assert "override_reason" in fail_override.json()["detail"]

    # 4. Override with reason -> succeeds
    override_res = client.post(f"/api/v1/orders/{order_id}/decision", json={
        "action": other_action,
        "override_reason": "Customer called support directly and confirmed address via WhatsApp.",
    }, headers=headers)
    assert override_res.status_code == 200
    override_data = override_res.json()
    assert override_data["decision_status"] == "OVERRIDDEN"
    assert override_data["selected_action"] == other_action


def test_record_intervention_outcome(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-INTERVENT-1",
        "order_value": "1200.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    # Evaluate and set decision to VERIFY_OTP
    client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    client.post(f"/api/v1/orders/{order_id}/decision", json={
        "action": "VERIFY_OTP",
    }, headers=headers)

    # Record intervention outcome: OTP_VERIFIED
    outcome_res = client.post(f"/api/v1/orders/{order_id}/intervention-outcome", json={
        "outcome": "OTP_VERIFIED",
        "notes": "Customer submitted OTP via SMS link.",
    }, headers=headers)
    assert outcome_res.status_code == 200
    outcome_data = outcome_res.json()
    assert outcome_data["intervention_status"] == "OTP_VERIFIED"

    # Order status should now be CONFIRMED
    get_order = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert get_order.json()["status"] == "CONFIRMED"


def test_cross_tenant_decision_isolation(client, create_user, create_org, create_member, auth_headers):
    user1 = create_user(email="u1@tenant1.com")
    org1 = create_org(name="Tenant 1")
    create_member(org1.id, user1.id, role=OrganizationRole.OPERATOR)
    headers1 = auth_headers(user1, org1)

    user2 = create_user(email="u2@tenant2.com")
    org2 = create_org(name="Tenant 2")
    create_member(org2.id, user2.id, role=OrganizationRole.OPERATOR)
    headers2 = auth_headers(user2, org2)

    # Tenant 1 creates order and evaluates
    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-T1-DECISION",
        "order_value": "900.00",
        "payment_method": "COD",
    }, headers=headers1)
    order1_id = order_res.json()["id"]
    client.post(f"/api/v1/orders/{order1_id}/evaluate", headers=headers1)

    # Tenant 2 attempts to evaluate Tenant 1's order -> 404
    eval_denied = client.post(f"/api/v1/orders/{order1_id}/evaluate", headers=headers2)
    assert eval_denied.status_code == 404

    # Tenant 2 attempts to read Tenant 1's decision -> 404
    get_denied = client.get(f"/api/v1/orders/{order1_id}/decision", headers=headers2)
    assert get_denied.status_code == 404

    # Tenant 2 attempts to record decision -> 404
    post_denied = client.post(f"/api/v1/orders/{order1_id}/decision", json={"action": "HOLD_CANCEL"}, headers=headers2)
    assert post_denied.status_code == 404


def test_auditor_role_cannot_evaluate_or_decide(client, create_user, create_org, create_member, auth_headers):
    user_op = create_user(email="op@merchant.com")
    user_aud = create_user(email="aud@merchant.com")
    org = create_org(name="Merchant")
    create_member(org.id, user_op.id, role=OrganizationRole.OPERATOR)
    create_member(org.id, user_aud.id, role=OrganizationRole.AUDITOR)

    op_headers = auth_headers(user_op, org)
    aud_headers = auth_headers(user_aud, org)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-RBAC-DEC",
        "order_value": "1100.00",
        "payment_method": "COD",
    }, headers=op_headers)
    order_id = order_res.json()["id"]

    # Auditor evaluate -> 403 Forbidden
    aud_eval = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=aud_headers)
    assert aud_eval.status_code == 403

    # Operator evaluates
    client.post(f"/api/v1/orders/{order_id}/evaluate", headers=op_headers)

    # Auditor can read decision -> 200 OK
    aud_get = client.get(f"/api/v1/orders/{order_id}/decision", headers=aud_headers)
    assert aud_get.status_code == 200

    # Auditor cannot record decision -> 403 Forbidden
    aud_record = client.post(f"/api/v1/orders/{order_id}/decision", json={"action": "SHIP_AS_IS"}, headers=aud_headers)
    assert aud_record.status_code == 403


def test_pincode_safeguards_sparse_data_blocks_auto_cancel(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies that sparse data (N < 15) in a pincode blocks automated cancellation."""
    user = create_user(email="merchant_sparse@example.com")
    org = create_org(name="Sparse Pincode Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = True
    db_session.commit()

    # Seed only 3 historical delivered orders for pincode 560099
    now = datetime.now(timezone.utc)
    for i in range(3):
        hist_order = Order(
            org_id=org.id,
            external_order_id=f"HIST-SPARSE-{i}",
            order_value=Decimal("800.00"),
            payment_method="COD",
            customer_name=f"Customer {i}",
            customer_phone=f"+91990000000{i}",
            shipping_pincode="560099",
            status="DELIVERED",
            created_at=now - timedelta(days=10),
        )
        db_session.add(hist_order)
    db_session.commit()

    # Create current order with very high risk making ec_ship_as_is < 0
    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-SPARSE-TARGET",
        "order_value": "400.00",
        "payment_method": "COD",
        "shipping_pincode": "560099",
    }, headers=headers)
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    order = db_session.get(Order, order_id)
    # Override p_rto = 0.95 to guarantee negative shipping contribution
    eval_record = DecisionEngineService.evaluate_order(
        order=order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.9500"),
    )

    disclosure = eval_record.explanation_data["uncertainty_disclosure"]
    assert disclosure["sample_size"] == 3
    assert disclosure["can_auto_cancel"] is False
    assert Decimal(str(disclosure["uncertainty_score"])) > DecisionAssumptions.MAX_UNCERTAINTY_THRESHOLD

    # HOLD_CANCEL must be disqualified due to sparse data
    cancel_action = next(a for a in eval_record.comparison_data if a["action"] == "HOLD_CANCEL")
    assert cancel_action["is_policy_eligible"] is False
    assert "Sparse or high-uncertainty data" in cancel_action["disqualification_reason"]
    assert eval_record.recommended_action != "HOLD_CANCEL"


def test_pincode_safeguards_stale_data_blocks_auto_cancel(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies that historical orders older than 180 days are excluded from pincode evidence."""
    user = create_user(email="merchant_stale@example.com")
    org = create_org(name="Stale Data Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = True
    db_session.commit()

    # Seed 20 historical delivered orders from 200 days ago (> 180 days freshness window)
    now = datetime.now(timezone.utc)
    for i in range(20):
        hist_order = Order(
            org_id=org.id,
            external_order_id=f"HIST-STALE-{i}",
            order_value=Decimal("800.00"),
            payment_method="COD",
            customer_name=f"Customer {i}",
            customer_phone=f"+9199000000{i:02d}",
            shipping_pincode="560088",
            status="DELIVERED",
            created_at=now - timedelta(days=200),
        )
        db_session.add(hist_order)
    db_session.commit()

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-STALE-TARGET",
        "order_value": "400.00",
        "payment_method": "COD",
        "shipping_pincode": "560088",
    }, headers=headers)
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    order = db_session.get(Order, order_id)
    eval_record = DecisionEngineService.evaluate_order(
        order=order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.9500"),
    )

    disclosure = eval_record.explanation_data["uncertainty_disclosure"]
    # All 20 orders are stale; fresh sample size must be 0
    assert disclosure["sample_size"] == 0
    assert disclosure["can_auto_cancel"] is False

    cancel_action = next(a for a in eval_record.comparison_data if a["action"] == "HOLD_CANCEL")
    assert cancel_action["is_policy_eligible"] is False
    assert "Sparse or high-uncertainty data" in cancel_action["disqualification_reason"]


def test_pincode_safeguards_duplicate_customers_vs_distinct_identities(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies that 20 orders from a single customer phone only count as 1 distinct customer."""
    user = create_user(email="merchant_repeat@example.com")
    org = create_org(name="Repeat Buyer Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = True
    db_session.commit()

    # Seed 20 historical delivered orders all sharing the same phone
    now = datetime.now(timezone.utc)
    for i in range(20):
        hist_order = Order(
            org_id=org.id,
            external_order_id=f"HIST-REPEAT-{i}",
            order_value=Decimal("800.00"),
            payment_method="COD",
            customer_name="Same Person",
            customer_phone="+919999999999",
            shipping_pincode="560077",
            status="DELIVERED",
            created_at=now - timedelta(days=20),
        )
        db_session.add(hist_order)
    db_session.commit()

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-REPEAT-TARGET",
        "order_value": "400.00",
        "payment_method": "COD",
        "shipping_pincode": "560077",
    }, headers=headers)
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    order = db_session.get(Order, order_id)
    eval_record = DecisionEngineService.evaluate_order(
        order=order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.9500"),
    )

    disclosure = eval_record.explanation_data["uncertainty_disclosure"]
    assert disclosure["sample_size"] == 20
    assert disclosure["distinct_customers"] == 1
    # distinct_customers < 15, so can_auto_cancel must be False
    assert disclosure["can_auto_cancel"] is False

    cancel_action = next(a for a in eval_record.comparison_data if a["action"] == "HOLD_CANCEL")
    assert cancel_action["is_policy_eligible"] is False


def test_pincode_safeguards_sufficient_fresh_distinct_data_allows_auto_cancel(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies that with N >= 15 fresh orders from 15 distinct customers, auto-cancellation is permitted."""
    user = create_user(email="merchant_sufficient@example.com")
    org = create_org(name="Sufficient Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = True
    db_session.commit()

    # Seed 16 fresh orders from 16 distinct customer phones
    now = datetime.now(timezone.utc)
    for i in range(16):
        hist_order = Order(
            org_id=org.id,
            external_order_id=f"HIST-SUFF-{i}",
            order_value=Decimal("800.00"),
            payment_method="COD",
            customer_name=f"Customer {i}",
            customer_phone=f"+9198000000{i:02d}",
            shipping_pincode="560066",
            status="DELIVERED",
            created_at=now - timedelta(days=15),
        )
        db_session.add(hist_order)
    db_session.commit()

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-SUFF-TARGET",
        "order_value": "150.00",
        "payment_method": "COD",
        "shipping_pincode": "560066",
    }, headers=headers)
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    order = db_session.get(Order, order_id)
    eval_record = DecisionEngineService.evaluate_order(
        order=order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.9500"),
    )

    disclosure = eval_record.explanation_data["uncertainty_disclosure"]
    assert disclosure["sample_size"] == 16
    assert disclosure["distinct_customers"] == 16
    assert Decimal(str(disclosure["uncertainty_score"])) <= DecisionAssumptions.MAX_UNCERTAINTY_THRESHOLD
    assert disclosure["can_auto_cancel"] is True

    cancel_action = next(a for a in eval_record.comparison_data if a["action"] == "HOLD_CANCEL")
    assert cancel_action["is_policy_eligible"] is True
    assert eval_record.recommended_action == "HOLD_CANCEL"


def test_cod_fee_policy_upon_manifest_vs_upon_delivery_only():
    """Verifies that RTO payoff respects UPON_MANIFEST vs UPON_DELIVERY_ONLY."""
    order_val = Decimal("1000.00")
    cogs = Decimal("300.00")
    fwd = Decimal("70.00")
    rev = Decimal("65.00")
    pkg = Decimal("20.00")
    dmg = Decimal("0.0500")
    cod_fee = Decimal("35.00")
    gw_fee = Decimal("0.00")

    # In UPON_DELIVERY_ONLY, COD fee is waived/refunded on RTO
    rto_delivery_only = DecisionEngineService.calculate_base_rto(
        order_value=order_val,
        is_cod=True,
        cogs=cogs,
        fwd_shipping=fwd,
        rev_shipping=rev,
        packaging=pkg,
        damage_rate=dmg,
        cod_fee=cod_fee,
        cod_fee_incurred_on="UPON_DELIVERY_ONLY",
        gateway_fee=gw_fee,
    )
    # Loss = packaging (20) + fwd (70) + rev (65) + damage (0.05*300 = 15) = 170.00 -> payoff = -170.00
    assert rto_delivery_only == Decimal("-170.00")

    # In UPON_MANIFEST, COD fee is charged on initial dispatch regardless of RTO
    rto_manifest = DecisionEngineService.calculate_base_rto(
        order_value=order_val,
        is_cod=True,
        cogs=cogs,
        fwd_shipping=fwd,
        rev_shipping=rev,
        packaging=pkg,
        damage_rate=dmg,
        cod_fee=cod_fee,
        cod_fee_incurred_on="UPON_MANIFEST",
        gateway_fee=gw_fee,
    )
    # Loss = cod_fee (35) + 170.00 = 205.00 -> payoff = -205.00
    assert rto_manifest == Decimal("-205.00")
    assert rto_delivery_only - rto_manifest == cod_fee


def test_economics_schema_cod_fee_validation_and_migration():
    """Verifies that the schema validates UPON_DELIVERY_ONLY and UPON_MANIFEST, and migrates legacy aliases."""
    # Valid options
    econ_deliv = MerchantEconomicsBase(cod_fee_incurred_on="UPON_DELIVERY_ONLY")
    assert econ_deliv.cod_fee_incurred_on == "UPON_DELIVERY_ONLY"

    econ_manif = MerchantEconomicsBase(cod_fee_incurred_on="UPON_MANIFEST")
    assert econ_manif.cod_fee_incurred_on == "UPON_MANIFEST"

    # Legacy migrations
    econ_leg1 = MerchantEconomicsBase(cod_fee_incurred_on="DELIVERY_ATTEMPT_1")
    assert econ_leg1.cod_fee_incurred_on == "UPON_MANIFEST"

    econ_leg2 = MerchantEconomicsBase(cod_fee_incurred_on="UPON_DISPATCH")
    assert econ_leg2.cod_fee_incurred_on == "UPON_MANIFEST"

    econ_leg3 = MerchantEconomicsBase(cod_fee_incurred_on="DELIVERED_ONLY")
    assert econ_leg3.cod_fee_incurred_on == "UPON_DELIVERY_ONLY"

    # Case-insensitive whitespace stripping
    econ_ws = MerchantEconomicsBase(cod_fee_incurred_on=" upon_manifest ")
    assert econ_ws.cod_fee_incurred_on == "UPON_MANIFEST"

    # Invalid trigger raises ValueError
    with pytest.raises(ValueError):
        MerchantEconomicsBase(cod_fee_incurred_on="UNKNOWN_POLICY")


def test_prepaid_discount_reconciliation_not_incurred_when_declined(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies that when a prepaid conversion is declined or cancelled, only comms cost (₹0.50) is booked."""
    user = create_user(email="recon_declined@example.com")
    org = create_org(name="Recon Declined Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-RECON-DECLINED",
        "order_value": "1000.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    # Evaluate order
    client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)

    # Merchant decides INCENTIVIZE_PREPAID
    dec_res = client.post(f"/api/v1/orders/{order_id}/decision", json={
        "action": "INCENTIVIZE_PREPAID",
        "override_reason": "Testing prepaid discount reconciliation",
    }, headers=headers)
    assert dec_res.status_code == 200

    # Customer declines prepaid conversion
    outcome_res = client.post(
        f"/api/v1/orders/{order_id}/intervention-outcome",
        json={"outcome": "PREPAID_DECLINED", "notes": "Customer prefers cash upon delivery"},
        headers=headers,
    )
    assert outcome_res.status_code == 200

    # Cancel the order
    order = db_session.get(Order, order_id)
    order.status = "CANCELLED"
    db_session.commit()

    # Reconcile order
    recon = ReconciliationService.reconcile_order(
        org_id=org.id,
        order_id=order.id,
        session=db_session,
    )

    # Pre-dispatch cost should be ONLY the communication cost (0.50), NOT including the 50.00 discount
    assert recon.pre_dispatch_intervention_cost == Decimal("0.50")
    # Realized RC for pre-dispatch cancelled order is -0.50
    assert recon.realized_contribution == Decimal("-0.50")


def test_prepaid_discount_reconciliation_incurred_when_converted(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies that when a prepaid conversion succeeds, both comms cost and incentive discount are booked."""
    user = create_user(email="recon_converted@example.com")
    org = create_org(name="Recon Converted Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-RECON-CONVERTED",
        "order_value": "1000.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    dec_res = client.post(f"/api/v1/orders/{order_id}/decision", json={
        "action": "INCENTIVIZE_PREPAID",
        "override_reason": "Testing prepaid discount reconciliation",
    }, headers=headers)
    assert dec_res.status_code == 200

    # Customer converts to prepaid
    outcome_res = client.post(
        f"/api/v1/orders/{order_id}/intervention-outcome",
        json={"outcome": "PREPAID_CONVERTED", "notes": "Paid online via UPI link with ₹50 discount"},
        headers=headers,
    )
    assert outcome_res.status_code == 200

    order = db_session.get(Order, order_id)
    order.status = "DELIVERED"
    db_session.commit()

    recon = ReconciliationService.reconcile_order(
        org_id=org.id,
        order_id=order.id,
        session=db_session,
    )

    # Pre-dispatch cost should include both comms cost (0.50) + granted discount (50.00) = 50.50
    assert recon.pre_dispatch_intervention_cost == Decimal("50.50")


def test_operational_probability_assumptions_in_explanation(client, create_user, create_org, create_member, auth_headers):
    """Verifies that decision evaluations disclose operational probability assumptions explicitly."""
    user = create_user(email="assumptions@example.com")
    org = create_org(name="Assumptions Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-ASSUMPTIONS-1",
        "order_value": "1000.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    eval_res = client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    data = eval_res.json()

    explanation = data["explanation_data"]
    assert "operational_probability_assumptions" in explanation
    ops = explanation["operational_probability_assumptions"]
    assert "otp_confirmation_rate" in ops
    assert "prepaid_conversion_rate" in ops
    assert "manual_review_approval_rate" in ops
    assert "disclosure" in ops
    assert "operational baseline assumptions, not trained ML predictions" in ops["disclosure"]


def test_pincode_safeguards_exact_sample_size_boundaries(create_user, create_org, create_member, db_session):
    """Verifies uncertainty calculation and eligibility across sample size boundaries: 14, 15, 16, and 75."""
    user = create_user(email="boundaries@example.com")
    org = create_org(name="Boundaries Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = True
    db_session.commit()

    now = datetime.now(timezone.utc)
    cases = [
        (14, False, Decimal("0.8006")),  # N=14 < 15: Ineligible, U = sqrt(25/39) = 0.8006 > 0.7910
        (15, True, Decimal("0.7906")),   # N=15 >= 15: Eligible, U = sqrt(25/40) = 0.7906 <= 0.7910
        (16, True, Decimal("0.7809")),   # N=16 >= 15: Eligible, U = sqrt(25/41) = 0.7809 <= 0.7910
        (75, True, Decimal("0.5000")),   # N=75 >= 15: Eligible, U = sqrt(25/100) = 0.5000 <= 0.7910
    ]

    for n_count, expected_eligible, expected_u in cases:
        pincode = f"560{n_count:03d}"
        for i in range(n_count):
            hist_order = Order(
                org_id=org.id,
                external_order_id=f"HIST-N{n_count}-{i}",
                order_value=Decimal("800.00"),
                payment_method="COD",
                customer_phone=f"+918800{n_count:02d}{i:04d}",
                shipping_pincode=pincode,
                status="DELIVERED",
                created_at=now - timedelta(days=10),
            )
            db_session.add(hist_order)
        db_session.commit()

        target_order = Order(
            org_id=org.id,
            external_order_id=f"TGT-N{n_count}",
            order_value=Decimal("200.00"),
            payment_method="COD",
            shipping_pincode=pincode,
            status="PENDING",
            created_at=now,
        )
        db_session.add(target_order)
        db_session.commit()

        eval_rec = DecisionEngineService.evaluate_order(
            order=target_order,
            economics=econ,
            session=db_session,
            evaluated_by_user_id=user.id,
        )
        disclosure = eval_rec.explanation_data["uncertainty_disclosure"]
        assert disclosure["sample_size"] == n_count
        assert disclosure["distinct_customers"] == n_count
        assert Decimal(str(disclosure["uncertainty_score"])) == expected_u
        assert disclosure["can_auto_cancel"] is expected_eligible


def test_pincode_safeguards_missing_identities_fails_safe(create_user, create_org, create_member, db_session):
    """Verifies that missing customer identities (null/empty phone and email) fail safely to distinct_customers=0."""
    user = create_user(email="missing_ids@example.com")
    org = create_org(name="Missing IDs Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = True
    db_session.commit()

    now = datetime.now(timezone.utc)
    pincode = "560098"
    for i in range(20):
        hist_order = Order(
            org_id=org.id,
            external_order_id=f"HIST-NOID-{i}",
            order_value=Decimal("800.00"),
            payment_method="COD",
            customer_name=f"Anonymous {i}",
            customer_phone=None,
            customer_email="",
            shipping_pincode=pincode,
            status="DELIVERED",
            created_at=now - timedelta(days=10),
        )
        db_session.add(hist_order)
    db_session.commit()

    target_order = Order(
        org_id=org.id,
        external_order_id="TGT-NOID",
        order_value=Decimal("200.00"),
        payment_method="COD",
        shipping_pincode=pincode,
        status="PENDING",
        created_at=now,
    )
    db_session.add(target_order)
    db_session.commit()

    eval_rec = DecisionEngineService.evaluate_order(
        order=target_order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.9500"),
    )
    disclosure = eval_rec.explanation_data["uncertainty_disclosure"]
    assert disclosure["sample_size"] == 20
    assert disclosure["distinct_customers"] == 0
    assert disclosure["can_auto_cancel"] is False

    cancel_action = next(a for a in eval_rec.comparison_data if a["action"] == "HOLD_CANCEL")
    assert cancel_action["is_policy_eligible"] is False


def test_pincode_safeguards_only_counts_completed_delivery_outcomes(create_user, create_org, create_member, db_session):
    """Verifies that in-flight or cancelled orders do not count towards empirical pincode evidence."""
    user = create_user(email="incomplete@example.com")
    org = create_org(name="Incomplete Status Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = True
    db_session.commit()

    now = datetime.now(timezone.utc)
    pincode = "560097"
    statuses = ["PENDING", "CONFIRMED", "SHIPPED", "CANCELLED", "OUT_FOR_DELIVERY"]
    for i, st in enumerate(statuses * 4):  # 20 orders total
        hist_order = Order(
            org_id=org.id,
            external_order_id=f"HIST-INCOMP-{i}",
            order_value=Decimal("800.00"),
            payment_method="COD",
            customer_phone=f"+91770000{i:04d}",
            shipping_pincode=pincode,
            status=st,
            created_at=now - timedelta(days=10),
        )
        db_session.add(hist_order)
    db_session.commit()

    target_order = Order(
        org_id=org.id,
        external_order_id="TGT-INCOMP",
        order_value=Decimal("200.00"),
        payment_method="COD",
        shipping_pincode=pincode,
        status="PENDING",
        created_at=now,
    )
    db_session.add(target_order)
    db_session.commit()

    eval_rec = DecisionEngineService.evaluate_order(
        order=target_order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
    )
    disclosure = eval_rec.explanation_data["uncertainty_disclosure"]
    # Only DELIVERED and RTO count; none of these 20 orders should count
    assert disclosure["sample_size"] == 0
    assert disclosure["distinct_customers"] == 0
    assert disclosure["can_auto_cancel"] is False


def test_pincode_safeguards_sufficient_evidence_alone_cannot_trigger_cancellation(create_user, create_org, create_member, db_session):
    """Verifies that sufficient empirical data alone CANNOT trigger cancellation unless ec_ship_as_is < 0 AND allow_auto_cancel is True."""
    user = create_user(email="sufficient_guards@example.com")
    org = create_org(name="Guard Checks Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = False  # Auto-cancel disabled
    db_session.commit()

    now = datetime.now(timezone.utc)
    pincode = "560096"
    # Seed 75 distinct delivered orders
    for i in range(75):
        hist_order = Order(
            org_id=org.id,
            external_order_id=f"HIST-75-{i}",
            order_value=Decimal("800.00"),
            payment_method="COD",
            customer_phone=f"+91991100{i:04d}",
            shipping_pincode=pincode,
            status="DELIVERED",
            created_at=now - timedelta(days=10),
        )
        db_session.add(hist_order)
    db_session.commit()

    target_order = Order(
        org_id=org.id,
        external_order_id="TGT-75-DISALLOWED",
        order_value=Decimal("200.00"),
        payment_method="COD",
        shipping_pincode=pincode,
        status="PENDING",
        created_at=now,
    )
    db_session.add(target_order)
    db_session.commit()

    # Case 1: allow_auto_cancel = False -> HOLD_CANCEL disqualified despite N=75 and U=0.5000
    eval_rec1 = DecisionEngineService.evaluate_order(
        order=target_order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.9500"),
    )
    disclosure1 = eval_rec1.explanation_data["uncertainty_disclosure"]
    assert disclosure1["can_auto_cancel"] is True  # Pincode uncertainty passed
    cancel_action1 = next(a for a in eval_rec1.comparison_data if a["action"] == "HOLD_CANCEL")
    assert cancel_action1["is_policy_eligible"] is False
    assert "allow_auto_cancel' is False" in cancel_action1["disqualification_reason"]

    # Case 2: allow_auto_cancel = True, but ec_ship_as_is >= 0 -> HOLD_CANCEL disqualified
    econ.allow_auto_cancel = True
    db_session.commit()

    target_order_profitable = Order(
        org_id=org.id,
        external_order_id="TGT-75-PROFITABLE",
        order_value=Decimal("2500.00"),
        payment_method="COD",
        shipping_pincode=pincode,
        status="PENDING",
        created_at=now,
    )
    db_session.add(target_order_profitable)
    db_session.commit()

    eval_rec2 = DecisionEngineService.evaluate_order(
        order=target_order_profitable,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id,
        override_p_rto=Decimal("0.0500"),  # Highly profitable order
    )
    cancel_action2 = next(a for a in eval_rec2.comparison_data if a["action"] == "HOLD_CANCEL")
    assert cancel_action2["is_policy_eligible"] is False
    assert "positive expected contribution" in cancel_action2["disqualification_reason"]


def test_cod_fee_policies_delivered_and_rto_reconciliation(create_user, create_org, create_member, db_session):
    """Verifies that ReconciliationService correctly calculates COD fees across all 4 combinations of policy and outcome."""
    user = create_user(email="cod_policy_matrix@example.com")
    org = create_org(name="COD Matrix Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.cod_carrier_fee = Decimal("35.00")
    db_session.commit()

    # Case 1: UPON_DELIVERY_ONLY, DELIVERED -> COD fee charged (35.00)
    econ.cod_fee_incurred_on = "UPON_DELIVERY_ONLY"
    db_session.commit()
    ord1 = Order(org_id=org.id, external_order_id="COD-M-1", order_value=Decimal("1000.00"), payment_method="COD", status="DELIVERED")
    db_session.add(ord1)
    db_session.commit()
    recon1 = ReconciliationService.reconcile_order(org_id=org.id, order_id=ord1.id, session=db_session)
    assert recon1.payment_fee == Decimal("35.00")

    # Case 2: UPON_MANIFEST, DELIVERED -> COD fee charged (35.00)
    econ.cod_fee_incurred_on = "UPON_MANIFEST"
    db_session.commit()
    ord2 = Order(org_id=org.id, external_order_id="COD-M-2", order_value=Decimal("1000.00"), payment_method="COD", status="DELIVERED")
    db_session.add(ord2)
    db_session.commit()
    recon2 = ReconciliationService.reconcile_order(org_id=org.id, order_id=ord2.id, session=db_session)
    assert recon2.payment_fee == Decimal("35.00")

    # Case 3: UPON_DELIVERY_ONLY, RTO -> COD fee waived (0.00)
    econ.cod_fee_incurred_on = "UPON_DELIVERY_ONLY"
    db_session.commit()
    ord3 = Order(org_id=org.id, external_order_id="COD-M-3", order_value=Decimal("1000.00"), payment_method="COD", status="RTO")
    db_session.add(ord3)
    db_session.commit()
    recon3 = ReconciliationService.reconcile_order(org_id=org.id, order_id=ord3.id, session=db_session)
    assert recon3.payment_fee == Decimal("0.00")

    # Case 4: UPON_MANIFEST, RTO -> COD fee charged upon manifest (35.00)
    econ.cod_fee_incurred_on = "UPON_MANIFEST"
    db_session.commit()
    ord4 = Order(org_id=org.id, external_order_id="COD-M-4", order_value=Decimal("1000.00"), payment_method="COD", status="RTO")
    db_session.add(ord4)
    db_session.commit()
    recon4 = ReconciliationService.reconcile_order(org_id=org.id, order_id=ord4.id, session=db_session)
    assert recon4.payment_fee == Decimal("35.00")


def test_prepaid_discount_pending_status_does_not_book_discount(client, create_user, create_org, create_member, auth_headers, db_session):
    """Verifies that while INCENTIVIZE_PREPAID is PENDING, reconciliation books only comms cost (₹0.50), not the discount."""
    user = create_user(email="recon_pending@example.com")
    org = create_org(name="Recon Pending Store")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-RECON-PENDING",
        "order_value": "1000.00",
        "payment_method": "COD",
    }, headers=headers)
    order_id = order_res.json()["id"]

    client.post(f"/api/v1/orders/{order_id}/evaluate", headers=headers)
    dec_res = client.post(f"/api/v1/orders/{order_id}/decision", json={
        "action": "INCENTIVIZE_PREPAID",
        "override_reason": "Sent WhatsApp message with prepaid link",
    }, headers=headers)
    assert dec_res.json()["intervention_status"] == "PENDING"

    order = db_session.get(Order, order_id)
    recon = ReconciliationService.reconcile_order(
        org_id=org.id,
        order_id=order.id,
        session=db_session,
    )
    # Only the ₹0.50 comms cost is booked; ₹50.00 discount is NOT booked while pending
    assert recon.pre_dispatch_intervention_cost == Decimal("0.50")

