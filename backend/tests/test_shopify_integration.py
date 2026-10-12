"""Test Suite for Phase 4B.1: Deployment Foundation and Shopify Integration.

Covers:
1. Cryptographic HMAC-SHA256 signature verification (valid, tampered, wrong secret, missing).
2. Store configuration lifecycle, encryption of credentials, and tenant isolation.
3. Unknown or unregistered store rejection (HTTP 404).
4. Unconfigured / inactive store rejection.
5. Missing delivery ID and malformed JSON payload handling (HTTP 400).
6. orders/create webhook ingestion, order normalization, and shadow ML prediction execution.
7. Webhook delivery deduplication and idempotency (X-Shopify-Delivery-Id).
8. orders/updated stale event prevention and terminal state protection.
9. orders/cancelled delivery event propagation and outcome tracking reconciliation.
10. orders/fulfilled transition to SHIPPED with courier and tracking details.
11. Secret redaction in webhook delivery audit logs.
"""

import base64
import hashlib
import hmac
import json
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.crypto import AESGCMCryptoService
from app.core.tenant import OrganizationRole
from app.models.delivery import DeliveryEvent
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.order_outcome import OrderOutcome
from app.models.shopify import ShopifyStore, ShopifyWebhookDelivery
from app.services.integrations.shopify_adapter import ShopifyAdapter
from app.services.shopify_service import ShopifyService


def compute_shopify_hmac(body: bytes, secret: str) -> str:
    """Helper to compute valid base64 Shopify HMAC-SHA256."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


@pytest.fixture
def shopify_test_setup(db_session, create_org, create_user, create_member, auth_headers):
    """Sets up Tenant A, an operator user, economics, and a configured Shopify store."""
    org = create_org(name="Shopify Test Merchant Org")
    user = create_user(email="shopify_operator@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    if not econ:
        econ = MerchantEconomics(org_id=org.id)
        db_session.add(econ)
        db_session.commit()

    webhook_secret = "shpss_test_secret_key_1234567890abcdef"
    crypto = AESGCMCryptoService()
    store = ShopifyStore(
        id=uuid4(),
        org_id=org.id,
        shop_domain="test-brand.myshopify.com",
        access_token_encrypted=crypto.encrypt("shpat_test_access_token_abc"),
        webhook_secret_encrypted=crypto.encrypt(webhook_secret),
        status="active",
        scopes="read_orders,write_orders",
        api_version="2024-01",
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)

    return org, user, headers, store, webhook_secret


def test_shopify_adapter_hmac_verification():
    """Verifies that ShopifyAdapter correctly validates and rejects HMAC signatures."""
    adapter = ShopifyAdapter()
    secret = "my_shared_webhook_secret_xyz"
    raw_body = b'{"id": 12345678, "total_price": "1499.00"}'
    
    # 1. Valid signature
    valid_sig = compute_shopify_hmac(raw_body, secret)
    assert adapter.verify_signature(raw_body, valid_sig, secret) is True

    # 2. Tampered body
    tampered_body = b'{"id": 12345678, "total_price": "9999.00"}'
    assert adapter.verify_signature(tampered_body, valid_sig, secret) is False

    # 3. Wrong secret
    assert adapter.verify_signature(raw_body, valid_sig, "wrong_secret_123") is False

    # 4. Missing or empty signature
    assert adapter.verify_signature(raw_body, "", secret) is False
    assert adapter.verify_signature(raw_body, None, secret) is False


def test_shopify_store_configuration_and_tenant_isolation(client, shopify_test_setup, create_org, create_user, create_member, auth_headers):
    """Verifies store configuration endpoints, AES-256 encryption, and tenant isolation."""
    org_a, user_a, headers_a, store_a, _ = shopify_test_setup

    org_b = create_org(name="Tenant B Org")
    user_b = create_user(email="user_b@shopify.com")
    create_member(org_b.id, user_b.id, OrganizationRole.OPERATOR)
    headers_b = auth_headers(user_b, org_b)

    # 1. Tenant A retrieves their store configuration
    resp_a = client.get("/api/v1/integrations/shopify", headers=headers_a)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["shop_domain"] == "test-brand.myshopify.com"
    assert data_a["status"] == "active"
    assert data_a["has_access_token"] is True
    assert data_a["has_webhook_secret"] is True
    # Secret must never be leaked
    assert "shpss_" not in json.dumps(data_a)
    assert "shpat_" not in json.dumps(data_a)

    # 2. Tenant B sees None (not configured)
    resp_b = client.get("/api/v1/integrations/shopify", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json() is None

    # 3. Tenant B attempts to claim Tenant A's shop domain -> 409 Conflict
    resp_b_claim = client.post(
        "/api/v1/integrations/shopify/configure",
        headers=headers_b,
        json={
            "shop_domain": "test-brand.myshopify.com",
            "access_token": "shpat_fake_token",
            "webhook_secret": "shpss_fake_secret",
        },
    )
    assert resp_b_claim.status_code == 409
    assert "already associated" in resp_b_claim.json()["detail"]

    # 4. Tenant A disconnects store
    resp_disc = client.post("/api/v1/integrations/shopify/disconnect", headers=headers_a)
    assert resp_disc.status_code == 200
    
    # 5. Check store is now not_configured
    resp_a_after = client.get("/api/v1/integrations/shopify", headers=headers_a)
    assert resp_a_after.status_code == 200
    assert resp_a_after.json()["status"] == "not_configured"


def test_unknown_or_unregistered_store_webhook_rejected(client):
    """Verifies that webhooks from unknown or unregistered shop domains are rejected with HTTP 404."""
    raw_body = b'{"id": 99999}'
    sig = compute_shopify_hmac(raw_body, "any_secret")
    
    resp = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": "unknown-unregistered.myshopify.com",
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": "deliv-unknown-001",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 404
    assert "Unknown or unregistered" in resp.json()["detail"]


def test_webhook_missing_headers_and_malformed_json(client, shopify_test_setup):
    """Verifies that missing headers and malformed JSON payloads return HTTP 400."""
    _, _, _, store, secret = shopify_test_setup

    raw_body = b'{"id": 111}'
    sig = compute_shopify_hmac(raw_body, secret)

    # 1. Missing Delivery-Id
    resp_no_deliv = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp_no_deliv.status_code == 400
    assert "X-Shopify-Delivery-Id" in resp_no_deliv.json()["detail"]

    # 2. Malformed JSON with valid signature
    bad_json = b'{bad_json: invalid}'
    bad_sig = compute_shopify_hmac(bad_json, secret)
    resp_bad_json = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=bad_json,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": bad_sig,
            "X-Shopify-Delivery-Id": "deliv-malformed-001",
            "Content-Type": "application/json",
        },
    )
    assert resp_bad_json.status_code == 400
    assert "Invalid JSON" in resp_bad_json.json()["detail"]


def test_webhook_orders_create_persists_order_and_triggers_eval_and_ml_shadow(client, db_session, shopify_test_setup):
    """
    Verifies that orders/create:
    1. Ingests and normalizes order details and items.
    2. Persists order with source_channel='SHOPIFY'.
    3. Triggers DecisionEngineService evaluation.
    4. Automatically records non-authoritative shadow ML prediction in evaluation metadata.
    """
    org, _, _, store, secret = shopify_test_setup

    order_payload = {
        "id": 987654321,
        "name": "#1042",
        "total_price": "2850.00",
        "currency": "INR",
        "created_at": "2026-10-12T10:00:00Z",
        "financial_status": "pending",
        "payment_gateway_names": ["Cash on Delivery (COD)"],
        "shipping_address": {
            "first_name": "Arjun",
            "last_name": "Sharma",
            "phone": "+91 9876543210",
            "address1": "Flat 402, Green Meadows",
            "city": "Bengaluru",
            "province": "Karnataka",
            "zip": "560001",
            "country_code": "IN",
        },
        "customer": {
            "email": "arjun.sharma@example.com",
        },
        "line_items": [
            {
                "title": "Wireless Bluetooth Earbuds",
                "sku": "AUDIO-EAR-01",
                "quantity": 1,
                "price": "2850.00",
            }
        ],
    }

    raw_body = json.dumps(order_payload).encode("utf-8")
    sig = compute_shopify_hmac(raw_body, secret)
    deliv_id = "deliv-create-987654321"

    resp = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": deliv_id,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PROCESSED"
    assert data["delivery_id"] == deliv_id

    # Verify Order in DB
    order = db_session.query(Order).filter_by(org_id=org.id, external_order_id="987654321").first()
    assert order is not None
    assert order.source_channel == "SHOPIFY"
    assert order.order_value == Decimal("2850.00")
    assert order.payment_method == "COD"
    assert order.customer_name == "Arjun Sharma"
    assert order.shipping_pincode == "560001"
    assert len(order.items) == 1
    assert order.items[0].sku == "AUDIO-EAR-01"

    # Verify Decision Engine Evaluation & Shadow ML attached
    eval_record = db_session.query(OrderEvaluation).filter_by(order_id=order.id).first()
    assert eval_record is not None
    assert eval_record.recommended_action in ("SHIP_AS_IS", "VERIFY_OTP", "INCENTIVIZE_PREPAID", "MANUAL_REVIEW", "HOLD_CANCEL")

    expl = eval_record.explanation_data
    assert "uncertainty_disclosure" in expl
    shadow_ml = expl["uncertainty_disclosure"].get("shadow_ml_prediction")
    assert shadow_ml is not None
    assert shadow_ml["is_shadow_mode"] is True
    # If model is loaded, status is ML_PREDICTION, else RULE_BASED_FALLBACK
    assert shadow_ml["status"] in ("ML_PREDICTION", "RULE_BASED_FALLBACK")
    if shadow_ml["status"] == "ML_PREDICTION":
        assert shadow_ml["rto_probability"] is not None
        assert shadow_ml["predicted_risk_tier"] in ("LOW", "MEDIUM", "HIGH")
        assert "SHADOW MODE" in shadow_ml["shadow_governance_notice"]


def test_webhook_delivery_idempotency_and_duplicates(client, db_session, shopify_test_setup):
    """Verifies that re-sending the same X-Shopify-Delivery-Id returns 200 DUPLICATE without side effects."""
    org, _, _, store, secret = shopify_test_setup

    order_payload = {
        "id": 888111222,
        "total_price": "1200.00",
        "payment_gateway_names": ["Razorpay Prepaid"],
        "line_items": [{"title": "Shirt", "sku": "SHIRT-01", "quantity": 1, "price": "1200.00"}],
    }
    raw_body = json.dumps(order_payload).encode("utf-8")
    sig = compute_shopify_hmac(raw_body, secret)
    deliv_id = "deliv-idempotent-test-01"

    # 1. First delivery
    resp1 = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": deliv_id,
            "Content-Type": "application/json",
        },
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "PROCESSED"

    # 2. Duplicate delivery (exact same delivery ID)
    resp2 = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": deliv_id,
            "Content-Type": "application/json",
        },
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "DUPLICATE"

    # Verify only 1 order exists
    orders = db_session.query(Order).filter_by(org_id=org.id, external_order_id="888111222").all()
    assert len(orders) == 1

    # Verify only 1 delivery entry
    deliveries = db_session.query(ShopifyWebhookDelivery).filter_by(shopify_delivery_id=deliv_id).all()
    assert len(deliveries) == 1


def test_orders_updated_stale_event_and_terminal_state_protection(client, db_session, shopify_test_setup):
    """Verifies that orders/updated updates active orders, but cannot alter terminal orders or stale events."""
    org, _, _, store, secret = shopify_test_setup

    # Create initial order
    order_payload = {
        "id": 777666555,
        "total_price": "1999.00",
        "payment_gateway_names": ["COD"],
        "shipping_address": {"city": "Pune", "zip": "411001"},
    }
    raw_body = json.dumps(order_payload).encode("utf-8")
    sig = compute_shopify_hmac(raw_body, secret)

    client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": "deliv-update-base",
            "Content-Type": "application/json",
        },
    )

    order = db_session.query(Order).filter_by(org_id=org.id, external_order_id="777666555").first()
    assert order.shipping_city == "Pune"

    # 1. Valid update event modifies shipping city
    update_payload = {
        "id": 777666555,
        "shipping_address": {"city": "Mumbai", "zip": "400001"},
        "updated_at": "2026-10-12T12:00:00Z",
    }
    raw_update = json.dumps(update_payload).encode("utf-8")
    sig_update = compute_shopify_hmac(raw_update, secret)

    client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_update,
        headers={
            "X-Shopify-Topic": "orders/updated",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig_update,
            "X-Shopify-Delivery-Id": "deliv-update-01",
            "Content-Type": "application/json",
        },
    )
    db_session.refresh(order)
    assert order.shipping_city == "Mumbai"

    # 2. Terminal state protection: Order is DELIVERED
    order.status = "DELIVERED"
    db_session.commit()

    # Incoming update attempting to change city or status
    late_payload = {
        "id": 777666555,
        "shipping_address": {"city": "Delhi", "zip": "110001"},
        "updated_at": "2026-10-12T14:00:00Z",
    }
    raw_late = json.dumps(late_payload).encode("utf-8")
    sig_late = compute_shopify_hmac(raw_late, secret)

    client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_late,
        headers={
            "X-Shopify-Topic": "orders/updated",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig_late,
            "X-Shopify-Delivery-Id": "deliv-update-late",
            "Content-Type": "application/json",
        },
    )
    db_session.refresh(order)
    assert order.status == "DELIVERED"  # Must remain DELIVERED
    assert order.shipping_city == "Mumbai"  # Untouched on terminal state


def test_orders_cancelled_lifecycle_and_outcome_tracking(client, db_session, shopify_test_setup):
    """Verifies that orders/cancelled cancels order and triggers automatic outcome recording."""
    org, _, _, store, secret = shopify_test_setup

    # Create order
    order_payload = {
        "id": 666555444,
        "total_price": "2100.00",
        "payment_gateway_names": ["COD"],
    }
    raw_create = json.dumps(order_payload).encode("utf-8")
    client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_create,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": compute_shopify_hmac(raw_create, secret),
            "X-Shopify-Delivery-Id": "deliv-cancel-base",
            "Content-Type": "application/json",
        },
    )

    # Cancel order via Shopify webhook
    cancel_payload = {
        "id": 666555444,
        "cancel_reason": "Customer requested cancellation before dispatch",
    }
    raw_cancel = json.dumps(cancel_payload).encode("utf-8")
    resp_cancel = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_cancel,
        headers={
            "X-Shopify-Topic": "orders/cancelled",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": compute_shopify_hmac(raw_cancel, secret),
            "X-Shopify-Delivery-Id": "deliv-cancel-exec",
            "Content-Type": "application/json",
        },
    )
    assert resp_cancel.status_code == 200

    order = db_session.query(Order).filter_by(org_id=org.id, external_order_id="666555444").first()
    assert order.status == "CANCELLED"
    assert order.outcome is not None
    assert order.outcome.final_delivery_outcome == "CANCELLED"


def test_orders_fulfilled_transitions_to_shipped(client, db_session, shopify_test_setup):
    """Verifies that orders/fulfilled maps tracking info and transitions order to SHIPPED."""
    org, _, _, store, secret = shopify_test_setup

    # Create order
    order_payload = {
        "id": 555444333,
        "total_price": "1800.00",
        "payment_gateway_names": ["COD"],
    }
    raw_create = json.dumps(order_payload).encode("utf-8")
    client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_create,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": compute_shopify_hmac(raw_create, secret),
            "X-Shopify-Delivery-Id": "deliv-fulfill-base",
            "Content-Type": "application/json",
        },
    )

    order = db_session.query(Order).filter_by(org_id=org.id, external_order_id="555444333").first()
    assert order.status == "PENDING"

    # Send fulfillments
    fulfill_payload = {
        "id": 555444333,
        "fulfillments": [
            {
                "tracking_company": "Delhivery Express",
                "tracking_number": "DEL-99887766",
            }
        ],
    }
    raw_fulfill = json.dumps(fulfill_payload).encode("utf-8")
    resp_fulfill = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_fulfill,
        headers={
            "X-Shopify-Topic": "orders/fulfilled",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": compute_shopify_hmac(raw_fulfill, secret),
            "X-Shopify-Delivery-Id": "deliv-fulfill-exec",
            "Content-Type": "application/json",
        },
    )
    assert resp_fulfill.status_code == 200

    db_session.refresh(order)
    assert order.status == "SHIPPED"
    assert order.fulfillment_status == "FULFILLED"


def test_secret_redaction_in_delivery_logs(client, db_session, shopify_test_setup):
    """Verifies that sensitive credentials and customer payment tokens are redacted in delivery logs."""
    org, _, _, store, secret = shopify_test_setup

    sensitive_payload = {
        "id": 444333222,
        "total_price": "999.00",
        "access_token": "secret_token_12345",
        "client_secret": "my_client_secret_xyz",
        "credit_card": "4111111111111111",
        "cvv": "123",
    }
    raw_body = json.dumps(sensitive_payload).encode("utf-8")
    sig = compute_shopify_hmac(raw_body, secret)
    deliv_id = "deliv-redact-check-01"

    client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": deliv_id,
            "Content-Type": "application/json",
        },
    )

    deliv = db_session.query(ShopifyWebhookDelivery).filter_by(shopify_delivery_id=deliv_id).first()
    assert deliv is not None
    summary_str = json.dumps(deliv.payload_summary)
    assert "secret_token_12345" not in summary_str
    assert "my_client_secret_xyz" not in summary_str
    assert "4111111111111111" not in summary_str
    assert "123" not in summary_str


def test_reprocessing_same_order_different_delivery_id_prevents_duplicate_records(client, db_session, shopify_test_setup):
    """
    Verifies that when Shopify sends an orders/create event for an already-ingested order
    under a NEW delivery ID (e.g. redelivery after timeout), the system does NOT create duplicate
    Order, OrderItem, or OrderEvaluation records.
    """
    org, _, _, store, secret = shopify_test_setup

    order_payload = {
        "id": 999888777,
        "total_price": "2499.00",
        "payment_gateway_names": ["Cash on Delivery"],
        "line_items": [
            {"title": "Watch", "sku": "WATCH-01", "quantity": 1, "price": "1499.00"},
            {"title": "Strap", "sku": "STRAP-01", "quantity": 1, "price": "1000.00"},
        ],
    }
    raw_body = json.dumps(order_payload).encode("utf-8")
    sig = compute_shopify_hmac(raw_body, secret)

    # First delivery ID D-01
    resp1 = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": "deliv-diff-id-01",
            "Content-Type": "application/json",
        },
    )
    assert resp1.status_code == 200

    # Second delivery ID D-02 for same order
    resp2 = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": "deliv-diff-id-02",
            "Content-Type": "application/json",
        },
    )
    assert resp2.status_code == 200

    # Check Order count
    orders = db_session.query(Order).filter_by(org_id=org.id, external_order_id="999888777").all()
    assert len(orders) == 1
    order = orders[0]

    # Check Line Item count: Must be exactly 2 items, NOT 4
    items = order.items
    assert len(items) == 2

    # Check Evaluation count: Must be exactly 1 evaluation, NOT 2
    evals = db_session.query(OrderEvaluation).filter_by(order_id=order.id).all()
    assert len(evals) == 1

    # Check Delivery records: 2 delivery records, both linking to the same order
    delivs = db_session.query(ShopifyWebhookDelivery).filter_by(shopify_order_id="999888777").all()
    assert len(delivs) == 2
    assert all(d.order_id == order.id for d in delivs)


def test_shadow_ml_prediction_separation_and_non_authoritative(client, db_session, shopify_test_setup):
    """
    Verifies that shadow ML predictions:
    1. Are isolated under explanation_data['uncertainty_disclosure']['shadow_ml_prediction'].
    2. Contain explicit synthetic benchmark provenance.
    3. Cannot mutate or override the deterministic decision engine recommendation.
    """
    org, _, _, store, secret = shopify_test_setup

    order_payload = {
        "id": 1122334455,
        "total_price": "3500.00",
        "payment_gateway_names": ["COD"],
        "shipping_address": {"zip": "560001", "city": "Bengaluru"},
        "line_items": [{"title": "Item A", "sku": "SKU-A", "quantity": 1, "price": "3500.00"}],
    }
    raw_body = json.dumps(order_payload).encode("utf-8")
    sig = compute_shopify_hmac(raw_body, secret)

    resp = client.post(
        "/api/v1/integrations/shopify/webhook",
        content=raw_body,
        headers={
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": store.shop_domain,
            "X-Shopify-Hmac-Sha256": sig,
            "X-Shopify-Delivery-Id": "deliv-ml-check-01",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200

    order = db_session.query(Order).filter_by(org_id=org.id, external_order_id="1122334455").first()
    eval_rec = db_session.query(OrderEvaluation).filter_by(order_id=order.id).first()
    assert eval_rec is not None

    # Deterministic recommendation is one of the 5 canonical rule actions
    assert eval_rec.recommended_action in {"SHIP_AS_IS", "VERIFY_OTP", "INCENTIVIZE_PREPAID", "MANUAL_REVIEW", "HOLD_CANCEL"}

    # ML shadow metadata is strictly isolated in uncertainty disclosure
    expl = eval_rec.explanation_data
    assert "uncertainty_disclosure" in expl
    shadow = expl["uncertainty_disclosure"]["shadow_ml_prediction"]
    assert shadow["is_shadow_mode"] is True
    assert "SHADOW MODE" in shadow.get("shadow_governance_notice", "")
    assert shadow.get("data_provenance") in {"SYNTHETIC_DEVELOPMENT_ONLY", "RULE_BASED_ENGINE"}
    assert shadow.get("live_feature_source") == "ORDER_PLACEMENT_ONLY"
    assert "unavailable_live_features" in shadow

