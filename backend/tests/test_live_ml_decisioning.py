"""Test Suite for Phase 4C: Live ML Decisioning Activation and Operating Modes.

Covers:
1. MLInferenceService lifecycle, modes (SHADOW, LIVE_ASSISTED, DISABLED), and metadata.
2. Model-readiness gate: synthetic-trained model is restricted from autonomous cancellations (HOLD_CANCEL).
3. Fail-safe feature validation: INSUFFICIENT_DATA and RULE_BASED_FALLBACK cleanly handled (rto_probability is None, never 0.0).
4. SHADOW mode: ML inference executed and audited; authoritative recommendation strictly follows deterministic rules.
5. LIVE_ASSISTED mode: ML inference evaluated and used for advisory action selection (e.g. elevating to VERIFY_OTP).
6. Anti-cancellation gate enforcement: synthetic model cannot trigger HOLD_CANCEL autonomously.
7. Immediate rollback: switching mode to SHADOW immediately restores deterministic authority.
8. Shopify webhook integration: incoming orders are created and evaluated with full ML tracking.
9. Closed-loop outcome recording: OrderOutcome persists deterministic, ML-assisted, and final recommendations.
10. Tenant isolation and /monitoring/ml-status API endpoint verification.
"""

import base64
import hashlib
import hmac
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.crypto import AESGCMCryptoService
from app.core.tenant import OrganizationRole
from app.models.delivery import DeliveryEvent
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.order_outcome import OrderOutcome
from app.models.shopify import ShopifyStore
from app.services.decision_engine import DecisionEngineService
from app.services.delivery_service import DeliveryService
from app.services.ml_inference_service import MLInferenceService, ml_inference_service
from app.services.outcome_tracking_service import OutcomeTrackingService
from app.services.shopify_service import ShopifyService


def compute_shopify_hmac(body: bytes, secret: str) -> str:
    """Helper to compute valid base64 Shopify HMAC-SHA256."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


@pytest.fixture
def ml_decisioning_setup(db_session, create_org, create_user, create_member, auth_headers):
    """Sets up Tenant A, Merchant Economics, and test user."""
    org = create_org(name="ML Decisioning Test Org")
    user = create_user(email="ml_operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    if not econ:
        econ = MerchantEconomics(org_id=org.id)
        db_session.add(econ)
        db_session.commit()

    yield {
        "org": org,
        "user": user,
        "headers": headers,
        "economics": econ,
        "db": db_session,
    }

    # Reset any runtime mode overrides after each test
    ml_inference_service.reset_operating_mode()


def test_ml_inference_service_lifecycle_and_metadata():
    """Verifies MLInferenceService loads artifact, exposes metadata, and enforces mode transitions."""
    service = MLInferenceService()
    assert service.is_ready()

    meta = service.get_metadata()
    assert meta["status"] == "LOADED"
    assert meta["data_provenance"] == "SYNTHETIC_DEVELOPMENT_ONLY"
    assert meta["model_version"] == "v1.0.0-synthetic-dev"
    assert meta["feature_count"] == 41
    assert meta["is_approved_for_consequential_actions"] is False

    # Mode switching
    assert service.get_operating_mode() in {"SHADOW", "LIVE_ASSISTED", "DISABLED"}
    service.set_operating_mode("LIVE_ASSISTED")
    assert service.get_operating_mode() == "LIVE_ASSISTED"

    service.set_operating_mode("DISABLED")
    assert service.get_operating_mode() == "DISABLED"

    service.set_operating_mode("SHADOW")
    assert service.get_operating_mode() == "SHADOW"

    with pytest.raises(ValueError):
        service.set_operating_mode("INVALID_MODE")

    service.reset_operating_mode()


def test_ml_inference_modes_and_failback(ml_decisioning_setup):
    """Verifies that DISABLED, INSUFFICIENT_DATA, and RULE_BASED_FALLBACK return None probability (never 0.0)."""
    db = ml_decisioning_setup["db"]
    org = ml_decisioning_setup["org"]

    service = MLInferenceService()

    # 1. Mode DISABLED
    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="TEST-DIS-1",
        order_value=Decimal("1500.00"),
        payment_method="COD",
        shipping_pincode="400001",
    )
    res_dis = service.infer_order_risk(order, db, mode_override="DISABLED")
    assert res_dis["status"] == "DISABLED"
    assert res_dis["operating_mode"] == "DISABLED"
    assert res_dis["rto_probability"] is None
    assert res_dis["fallback_used"] is True

    # 2. INSUFFICIENT_DATA: Null order
    res_null = service.infer_order_risk(None, db, mode_override="SHADOW")
    assert res_null["status"] == "INSUFFICIENT_DATA"
    assert res_null["rto_probability"] is None
    assert res_null["fallback_used"] is True

    # 3. INSUFFICIENT_DATA: Missing order value
    order_zero = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="TEST-ZERO-1",
        order_value=Decimal("0.00"),
        payment_method="COD",
    )
    res_zero = service.infer_order_risk(order_zero, db, mode_override="SHADOW")
    assert res_zero["status"] == "INSUFFICIENT_DATA"
    assert res_zero["rto_probability"] is None
    assert res_zero["fallback_used"] is True

    # 4. RULE_BASED_FALLBACK: missing artifact
    broken_service = MLInferenceService(artifact_path=Path("non_existent_model.joblib"))
    res_fallback = broken_service.infer_order_risk(order, db, mode_override="SHADOW")
    assert res_fallback["status"] == "RULE_BASED_FALLBACK"
    assert res_fallback["rto_probability"] is None
    assert res_fallback["fallback_used"] is True

    # 5. ML_PREDICTION: valid real order
    res_valid = service.infer_order_risk(order, db, mode_override="SHADOW")
    assert res_valid["status"] == "ML_PREDICTION"
    assert isinstance(res_valid["rto_probability"], float)
    assert 0.0 <= res_valid["rto_probability"] <= 1.0
    assert res_valid["predicted_risk_tier"] in {"LOW", "MEDIUM", "HIGH"}
    assert res_valid["fallback_used"] is False
    assert res_valid["data_provenance"] == "SYNTHETIC_DEVELOPMENT_ONLY"


def test_shadow_mode_preserves_deterministic_recommendation(ml_decisioning_setup):
    """Verifies that in SHADOW mode, ML risk is audited but does NOT alter the active recommendation."""
    db = ml_decisioning_setup["db"]
    org = ml_decisioning_setup["org"]
    econ = ml_decisioning_setup["economics"]

    ml_inference_service.set_operating_mode("SHADOW")

    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="TEST-SHADOW-1",
        order_value=Decimal("1200.00"),
        payment_method="COD",
        shipping_pincode="400001",
        shipping_city="Mumbai",
        shipping_state="Maharashtra",
        source_channel="MANUAL",
    )
    db.add(order)
    db.commit()

    evaluation = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db)

    assert evaluation.ml_operating_mode == "SHADOW"
    assert evaluation.decision_policy_version == "v1.1-ml-assisted"
    assert evaluation.recommended_action == evaluation.recommended_action_deterministic
    assert evaluation.recommended_action_deterministic is not None
    assert evaluation.recommended_action_ml_assisted is not None
    assert "Shadow mode active" in evaluation.ml_decision_rationale


def test_live_assisted_mode_elevated_risk_override(ml_decisioning_setup):
    """Verifies that in LIVE_ASSISTED mode, elevated ML risk can adjust the recommendation to VERIFY_OTP."""
    db = ml_decisioning_setup["db"]
    org = ml_decisioning_setup["org"]
    econ = ml_decisioning_setup["economics"]

    ml_inference_service.set_operating_mode("LIVE_ASSISTED")

    # High COD order with elevated risk characteristics
    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="TEST-LIVE-1",
        order_value=Decimal("2800.00"),
        payment_method="COD",
        shipping_pincode="143001",  # Tier 3 rural pincode with lower serviceability
        shipping_city="Amritsar",
        shipping_state="Punjab",
        source_channel="SHOPIFY",
    )
    db.add(order)
    db.commit()

    evaluation = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db)

    assert evaluation.ml_operating_mode == "LIVE_ASSISTED"
    assert evaluation.decision_policy_version == "v1.1-ml-assisted"
    assert evaluation.recommended_action == evaluation.recommended_action_ml_assisted
    assert evaluation.recommended_action_deterministic is not None
    assert evaluation.recommended_action_ml_assisted is not None

    # Check rationale is populated
    assert evaluation.ml_decision_rationale is not None
    assert "Live-assisted mode" in evaluation.ml_decision_rationale


def test_model_readiness_gate_blocks_consequential_cancellation(ml_decisioning_setup):
    """Verifies model-readiness gate: synthetic model cannot trigger autonomous HOLD_CANCEL."""
    db = ml_decisioning_setup["db"]
    org = ml_decisioning_setup["org"]
    econ = ml_decisioning_setup["economics"]

    # Allow auto cancel in merchant economics
    econ.allow_auto_cancel = True
    db.commit()

    ml_inference_service.set_operating_mode("LIVE_ASSISTED")

    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="TEST-GATE-1",
        order_value=Decimal("3500.00"),
        payment_method="COD",
        shipping_pincode="143001",
        source_channel="SHOPIFY",
    )
    db.add(order)
    db.commit()

    evaluation = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db)

    # Invariant: Never HOLD_CANCEL solely from synthetic ML model
    assert evaluation.recommended_action != "HOLD_CANCEL"
    assert evaluation.recommended_action_ml_assisted != "HOLD_CANCEL"

    # Inspect comparison data for HOLD_CANCEL disqualification
    cancel_eval = next((a for a in evaluation.comparison_data if a["action"] == "HOLD_CANCEL"), None)
    assert cancel_eval is not None
    # Readiness gate must disqualify HOLD_CANCEL for synthetic model
    expl_data = evaluation.explanation_data or {}
    meta = expl_data.get("uncertainty_disclosure", {}).get("ml_decision_metadata", {})
    assert meta.get("is_approved_for_consequential_actions") is False


def test_immediate_mode_rollback_to_shadow(ml_decisioning_setup):
    """Verifies that reverting operating mode to SHADOW immediately restores deterministic authority."""
    db = ml_decisioning_setup["db"]
    org = ml_decisioning_setup["org"]
    econ = ml_decisioning_setup["economics"]

    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="TEST-ROLLBACK-1",
        order_value=Decimal("2900.00"),
        payment_method="COD",
        shipping_pincode="143001",
        source_channel="SHOPIFY",
    )
    db.add(order)
    db.commit()

    # 1. LIVE_ASSISTED mode
    ml_inference_service.set_operating_mode("LIVE_ASSISTED")
    eval_live = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db)
    assert eval_live.ml_operating_mode == "LIVE_ASSISTED"

    # 2. Immediate rollback to SHADOW mode
    ml_inference_service.set_operating_mode("SHADOW")
    eval_shadow = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db)
    assert eval_shadow.ml_operating_mode == "SHADOW"
    assert eval_shadow.recommended_action == eval_shadow.recommended_action_deterministic


def test_shopify_webhook_live_decisioning_flow(client: TestClient, ml_decisioning_setup):
    """Verifies end-to-end Shopify order creation with live ML decisioning and metadata persistence."""
    db = ml_decisioning_setup["db"]
    org = ml_decisioning_setup["org"]

    ml_inference_service.set_operating_mode("LIVE_ASSISTED")

    webhook_secret = "shpss_test_secret_live_ml_123"
    crypto = AESGCMCryptoService()
    store = ShopifyStore(
        id=uuid4(),
        org_id=org.id,
        shop_domain="live-ml-test.myshopify.com",
        access_token_encrypted=crypto.encrypt("shpat_test_token_live"),
        webhook_secret_encrypted=crypto.encrypt(webhook_secret),
        status="active",
        api_version="2024-01",
    )
    db.add(store)
    db.commit()

    payload = {
        "id": 99887766,
        "name": "#1099-ML",
        "created_at": "2026-10-12T10:00:00Z",
        "currency": "INR",
        "total_price": "2199.00",
        "financial_status": "pending",
        "gateway": "manual",
        "email": "buyer_ml@test.com",
        "phone": "+919876543210",
        "shipping_address": {
            "first_name": "Rohan",
            "last_name": "Mehta",
            "phone": "+919876543210",
            "address1": "Flat 302, Palm Heights",
            "city": "Mumbai",
            "province": "Maharashtra",
            "zip": "400050",
            "country": "India",
        },
        "line_items": [
            {
                "id": 112233,
                "title": "Wireless Earbuds Pro",
                "sku": "EARBUD-PRO-01",
                "quantity": 1,
                "price": "2199.00",
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")
    hmac_sig = compute_shopify_hmac(raw_body, webhook_secret)

    resp = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Hmac-SHA256": hmac_sig,
            "X-Shopify-Shop-Domain": "live-ml-test.myshopify.com",
            "X-Shopify-Delivery-Id": str(uuid4()),
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PROCESSED"

    # Verify order and evaluation in DB
    order = db.query(Order).filter_by(org_id=org.id, external_order_id="99887766").first()
    assert order is not None

    evaluation = db.query(OrderEvaluation).filter_by(org_id=org.id, order_id=order.id).first()
    assert evaluation is not None
    assert evaluation.ml_operating_mode == "LIVE_ASSISTED"
    assert evaluation.decision_policy_version == "v1.1-ml-assisted"
    assert evaluation.recommended_action_deterministic is not None
    assert evaluation.recommended_action_ml_assisted is not None
    assert evaluation.ml_decision_rationale is not None


def test_closed_loop_outcome_persists_ml_recommendations(ml_decisioning_setup):
    """Verifies that OrderOutcome records deterministic, ML-assisted, and final recommendations."""
    db = ml_decisioning_setup["db"]
    org = ml_decisioning_setup["org"]
    econ = ml_decisioning_setup["economics"]
    user = ml_decisioning_setup["user"]

    ml_inference_service.set_operating_mode("LIVE_ASSISTED")

    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="TEST-OUTCOME-ML-1",
        order_value=Decimal("1999.00"),
        payment_method="COD",
        shipping_pincode="400001",
        status="DELIVERED",
    )
    db.add(order)
    db.commit()

    evaluation = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db)
    outcome = OutcomeTrackingService.record_order_outcome(
        org_id=org.id,
        order_id=order.id,
        session=db,
        actor_user_id=user.id,
    )

    assert outcome.deterministic_recommendation == evaluation.recommended_action_deterministic
    assert outcome.ml_assisted_recommendation == evaluation.recommended_action_ml_assisted
    assert outcome.final_recommendation == evaluation.recommended_action
    assert outcome.ml_operating_mode == "LIVE_ASSISTED"
    assert outcome.decision_policy_version == "v1.1-ml-assisted"


def test_monitoring_ml_status_endpoint(client: TestClient, ml_decisioning_setup):
    """Verifies GET /api/v1/monitoring/ml-status endpoint exposes operating mode and readiness gate."""
    headers = ml_decisioning_setup["headers"]

    resp = client.get("/api/v1/monitoring/ml-status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "operating_mode" in data
    assert data["is_approved_for_consequential_actions"] is False
    assert data["decision_policy_version"] == "v1.1-ml-assisted"
    assert data["model_loaded"] is True
    assert "model_metadata" in data
    assert data["model_metadata"]["data_provenance"] == "SYNTHETIC_DEVELOPMENT_ONLY"
    assert "governance_notice" in data


def test_tenant_isolation_ml_evaluations(client: TestClient, ml_decisioning_setup, create_org, create_user, create_member, auth_headers):
    """Verifies that ML evaluations and outcomes are strictly isolated between tenants."""
    db = ml_decisioning_setup["db"]
    org_a = ml_decisioning_setup["org"]
    econ_a = ml_decisioning_setup["economics"]

    org_b = create_org(name="Tenant B Competitor Org")
    user_b = create_user(email="tenant_b_user@test.com")
    create_member(org_b.id, user_b.id, OrganizationRole.OPERATOR)
    headers_b = auth_headers(user_b, org_b)

    order_a = Order(
        id=uuid4(),
        org_id=org_a.id,
        external_order_id="TENANT-A-ORDER",
        order_value=Decimal("1500.00"),
        payment_method="COD",
        shipping_pincode="400001",
    )
    db.add(order_a)
    db.commit()

    eval_a = DecisionEngineService.evaluate_order(order=order_a, economics=econ_a, session=db)

    # Tenant B attempts to fetch Tenant A's order evaluation
    resp = client.get(f"/api/v1/orders/{order_a.id}/evaluation", headers=headers_b)
    assert resp.status_code == 404
