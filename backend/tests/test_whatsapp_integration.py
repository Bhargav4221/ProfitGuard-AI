"""Comprehensive Test Suite for Meta WhatsApp Business Cloud API Integration.

Covers:
1. Cryptographic HMAC-SHA256 signature verification (X-Hub-Signature-256).
2. Phone number normalization (E.164) and intent classification.
3. Multi-tenant credential lifecycle, encryption, and tenant isolation.
4. Official Meta GET webhook challenge verification handshake.
5. Inbound webhook POST signature enforcement and error handling.
6. Message delivery status tracking (QUEUED -> SENT -> DELIVERED -> READ / FAILED).
7. Webhook event deduplication and idempotency.
8. Customer opt-out compliance (STOP / UNSUBSCRIBE).
9. Pre-dispatch COD OTP verification flow and customer CONFIRM reply.
10. Customer CANCEL reply safety invariant (held on HOLD for operator review; no autonomous cancellation).
11. NDR customer recovery messaging flow.
"""

import hashlib
import hmac
import json
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.crypto import AESGCMCryptoService, crypto_service
from app.core.tenant import OrganizationRole
from app.models.delivery import DeliveryEvent, NDRCase
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.whatsapp import (
    WhatsAppConfig,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppWebhookEvent,
)
from app.services.integrations.whatsapp_adapter import WhatsAppAdapter
from app.services.whatsapp_service import WhatsAppService


def compute_whatsapp_signature(body: bytes, secret: str) -> str:
    """Helper to compute valid Meta X-Hub-Signature-256."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def whatsapp_test_setup(db_session, create_org, create_user, create_member, auth_headers):
    """Sets up Tenant A, an operator user, economics, and a configured WhatsApp integration."""
    org = create_org(name="WhatsApp Test Org A")
    user = create_user(email="whatsapp_operator_a@test.com")
    create_member(org.id, user.id, OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    if not econ:
        econ = MerchantEconomics(org_id=org.id)
        db_session.add(econ)
        db_session.commit()

    app_secret = "test_meta_app_secret_1234567890abcdef"
    access_token = "EAAB_test_mock_system_user_token_abc"
    phone_number_id = "109876543210123"

    config = WhatsAppConfig(
        org_id=org.id,
        phone_number_id=phone_number_id,
        business_account_id="101928374650123",
        access_token_encrypted=crypto_service.encrypt(access_token),
        app_secret_encrypted=crypto_service.encrypt(app_secret),
        webhook_verify_token="test_verify_token_custom_123",
        operating_mode="MOCK",
        status="ACTIVE",
        api_version="v20.0",
    )
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)

    return {
        "org": org,
        "user": user,
        "headers": headers,
        "config": config,
        "app_secret": app_secret,
        "access_token": access_token,
        "phone_number_id": phone_number_id,
        "verify_token": "test_verify_token_custom_123",
    }


# =============================================================================
# 1. Adapter Unit Tests
# =============================================================================


def test_whatsapp_adapter_signature_verification():
    adapter = WhatsAppAdapter()
    body = b'{"object":"whatsapp_business_account","entry":[]}'
    secret = "my_app_secret_key"

    valid_sig = compute_whatsapp_signature(body, secret)
    assert adapter.verify_signature(body, valid_sig, secret) is True
    # Without sha256= prefix
    assert adapter.verify_signature(body, valid_sig.replace("sha256=", ""), secret) is True

    # Tampered signature
    assert adapter.verify_signature(body, "sha256=" + "0" * 64, secret) is False
    # Wrong secret
    assert adapter.verify_signature(body, valid_sig, "wrong_secret") is False
    # Empty inputs
    assert adapter.verify_signature(b"", valid_sig, secret) is False
    assert adapter.verify_signature(body, "", secret) is False
    assert adapter.verify_signature(body, valid_sig, "") is False


def test_whatsapp_adapter_phone_normalization_and_intent():
    adapter = WhatsAppAdapter()

    # Normalization
    assert adapter.normalize_phone_number("9876543210") == "+919876543210"
    assert adapter.normalize_phone_number("+91 98765-43210") == "+919876543210"
    assert adapter.normalize_phone_number("(987) 654-3210") == "+919876543210"
    assert adapter.normalize_phone_number("+1 (650) 555-0100") == "+16505550100"

    # Opt-Out Detection
    assert adapter.detect_opt_out("STOP") is True
    assert adapter.detect_opt_out("  stop  ") is True
    assert adapter.detect_opt_out("UNSUBSCRIBE") is True
    assert adapter.detect_opt_out("OPT OUT") is True
    assert adapter.detect_opt_out("Hello please confirm") is False

    # Intent Detection
    assert adapter.detect_intent("CONFIRM") == "CONFIRM"
    assert adapter.detect_intent("yes") == "CONFIRM"
    assert adapter.detect_intent("1") == "CONFIRM"
    assert adapter.detect_intent("CANCEL") == "CANCEL"
    assert adapter.detect_intent("no") == "CANCEL"
    assert adapter.detect_intent("Updated address: Flat 402, Green Glen") == "ADDRESS_UPDATE"
    assert adapter.detect_intent("Hello when will it arrive?") == "OTHER"


# =============================================================================
# 2. Configuration & Multi-Tenant Credential Isolation Tests
# =============================================================================


def test_whatsapp_configuration_and_tenant_isolation(client: TestClient, whatsapp_test_setup, db_session, create_org, create_user, create_member, auth_headers):
    setup_a = whatsapp_test_setup
    headers_a = setup_a["headers"]

    # 1. Tenant A fetches config: raw tokens are NOT exposed
    res = client.get("/api/v1/integrations/whatsapp", headers=headers_a)
    assert res.status_code == 200
    data = res.json()
    assert data["phone_number_id"] == setup_a["phone_number_id"]
    assert data["operating_mode"] == "MOCK"
    assert data["has_access_token"] is True
    assert data["has_app_secret"] is True
    assert "access_token" not in data
    assert "app_secret" not in data

    # 2. Tenant B logs in: cannot access Tenant A's config
    org_b = create_org(name="WhatsApp Org B")
    user_b = create_user(email="operator_b@test.com")
    create_member(org_b.id, user_b.id, OrganizationRole.OPERATOR)
    headers_b = auth_headers(user_b, org_b)

    res_b = client.get("/api/v1/integrations/whatsapp", headers=headers_b)
    assert res_b.status_code == 200
    assert res_b.json() is None

    # 3. Test connection endpoint returns healthy mock diagnostic
    res_diag = client.post("/api/v1/integrations/whatsapp/test-connection", headers=headers_a)
    assert res_diag.status_code == 200
    diag_data = res_diag.json()
    assert diag_data["connected"] is True
    assert diag_data["operating_mode"] == "MOCK"

    # 4. Disconnect clears credentials
    res_disc = client.post("/api/v1/integrations/whatsapp/disconnect", headers=headers_a)
    assert res_disc.status_code == 200
    res_after = client.get("/api/v1/integrations/whatsapp", headers=headers_a)
    assert res_after.json()["status"] == "DISCONNECTED"
    assert res_after.json()["has_access_token"] is False


# =============================================================================
# 3. Webhook GET Challenge Verification Tests
# =============================================================================


def test_whatsapp_webhook_get_challenge_handshake(client: TestClient, whatsapp_test_setup):
    setup = whatsapp_test_setup
    verify_token = setup["verify_token"]
    challenge_val = "1158201444"

    # Valid challenge verification
    res = client.get(
        f"/api/v1/integrations/whatsapp/webhook?hub.mode=subscribe&hub.verify_token={verify_token}&hub.challenge={challenge_val}"
    )
    assert res.status_code == 200
    assert res.text == challenge_val

    # Invalid verify token -> 403 Forbidden
    res_bad = client.get(
        f"/api/v1/integrations/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge={challenge_val}"
    )
    assert res_bad.status_code == 403

    # Missing parameters -> 403 Forbidden
    res_missing = client.get("/api/v1/integrations/whatsapp/webhook")
    assert res_missing.status_code == 403


# =============================================================================
# 4. Webhook POST HMAC Signature Verification Tests
# =============================================================================


def test_whatsapp_webhook_post_signature_verification(client: TestClient, whatsapp_test_setup):
    setup = whatsapp_test_setup
    app_secret = setup["app_secret"]
    phone_id = setup["phone_number_id"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "101928374650123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "+15550100", "phone_number_id": phone_id},
                            "statuses": [
                                {
                                    "id": "wamid.test_status_123",
                                    "status": "delivered",
                                    "timestamp": "1710000005",
                                    "recipient_id": "919876543210",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    body_bytes = json.dumps(payload).encode("utf-8")
    valid_sig = compute_whatsapp_signature(body_bytes, app_secret)

    # 1. Valid Signature -> 200 OK
    res_valid = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["status"] == "success"

    # 2. Forged Signature -> 401 Unauthorized
    res_invalid = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=invalidhash000000000000000000"},
    )
    assert res_invalid.status_code == 401


# =============================================================================
# 5. Message Delivery Status Transitions & Idempotency Tests
# =============================================================================


def test_whatsapp_delivery_status_transitions_and_idempotency(client: TestClient, whatsapp_test_setup, db_session):
    setup = whatsapp_test_setup
    org = setup["org"]
    app_secret = setup["app_secret"]
    phone_id = setup["phone_number_id"]

    # Create an outbound message in QUEUED state
    wamid = f"wamid.test_transition_{uuid4().hex[:12]}"
    msg = WhatsAppMessage(
        org_id=org.id,
        wamid=wamid,
        direction="OUTBOUND",
        recipient_phone="+919876543210",
        message_type="TEMPLATE",
        status="QUEUED",
        intervention_cost=Decimal("0.80"),
    )
    db_session.add(msg)
    db_session.commit()

    # 1. Process "delivered" status callback
    payload_delivered = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "101928374650123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_id},
                            "statuses": [
                                {
                                    "id": wamid,
                                    "status": "delivered",
                                    "timestamp": "1710000010",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload_delivered).encode("utf-8")
    sig = compute_whatsapp_signature(body, app_secret)

    res = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200

    db_session.refresh(msg)
    assert msg.status == "DELIVERED"
    assert msg.delivered_at is not None

    # 2. Idempotency Check: send exact same webhook again
    res_dup = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res_dup.status_code == 200
    # Processed events should be 0 because it's a deduplicated duplicate
    assert res_dup.json()["processed_events"] == 0

    # 3. Process "read" status callback
    payload_read = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "101928374650123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_id},
                            "statuses": [
                                {
                                    "id": wamid,
                                    "status": "read",
                                    "timestamp": "1710000020",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body_read = json.dumps(payload_read).encode("utf-8")
    sig_read = compute_whatsapp_signature(body_read, app_secret)

    res_read = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body_read,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig_read},
    )
    assert res_read.status_code == 200
    db_session.refresh(msg)
    assert msg.status == "READ"
    assert msg.read_at is not None


# =============================================================================
# 6. Customer Opt-Out (STOP) Compliance Tests
# =============================================================================


def test_whatsapp_customer_opt_out_compliance(client: TestClient, whatsapp_test_setup, db_session):
    setup = whatsapp_test_setup
    org = setup["org"]
    headers = setup["headers"]
    app_secret = setup["app_secret"]
    phone_id = setup["phone_number_id"]
    customer_phone = "+919876543210"

    # 1. Customer sends inbound "STOP" webhook
    msg_id = f"wamid.optout_{uuid4().hex[:12]}"
    payload_stop = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "101928374650123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [
                                {
                                    "id": msg_id,
                                    "from": "919876543210",
                                    "timestamp": "1710000030",
                                    "type": "text",
                                    "text": {"body": "STOP"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload_stop).encode("utf-8")
    sig = compute_whatsapp_signature(body, app_secret)

    res = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200

    # Verify registered in WhatsAppOptOut table
    opt_out = db_session.query(WhatsAppOptOut).filter_by(org_id=org.id, phone_number=customer_phone).first()
    assert opt_out is not None

    # Verify visible in /opt-outs endpoint
    res_list = client.get("/api/v1/integrations/whatsapp/opt-outs", headers=headers)
    assert res_list.status_code == 200
    assert any(o["phone_number"] == customer_phone for o in res_list.json())

    # 2. Attempting to send an outbound message to this customer is strictly BLOCKED
    res_blocked = client.post(
        "/api/v1/integrations/whatsapp/send-test",
        json={"recipient_phone": customer_phone, "message_text": "Marketing promo"},
        headers=headers,
    )
    assert res_blocked.status_code == 400
    assert "opted out" in res_blocked.json()["detail"].lower()


# =============================================================================
# 7. Pre-Dispatch COD OTP Verification & Customer CONFIRM Reply Flow
# =============================================================================


def test_whatsapp_cod_otp_verification_flow(client: TestClient, whatsapp_test_setup, db_session):
    setup = whatsapp_test_setup
    org = setup["org"]
    headers = setup["headers"]
    app_secret = setup["app_secret"]
    phone_id = setup["phone_number_id"]
    customer_phone = "+919988776655"

    # 1. Create a COD order
    order = Order(
        org_id=org.id,
        external_order_id="ORD-WA-COD-1",
        order_value=Decimal("2499.00"),
        payment_method="COD",
        status="HOLD",
        fulfillment_status="HOLD",
        customer_name="Rohit Sharma",
        customer_phone=customer_phone,
        shipping_country="India",
        source_channel="SHOPIFY",
    )
    db_session.add(order)
    db_session.flush()

    # Create Evaluation with VERIFY_OTP
    eval_rec = OrderEvaluation(
        org_id=org.id,
        order_id=order.id,
        recommended_action="VERIFY_OTP",
        selected_action="VERIFY_OTP",
        decision_status="ACCEPTED",
        intervention_status="PENDING",
        recommended_lift=Decimal("150.00"),
        ship_as_is_ec=Decimal("800.00"),
        best_ec=Decimal("950.00"),
        profit_at_risk=Decimal("500.00"),
        baseline_p_rto=Decimal("0.45"),
        uncertainty_score=Decimal("0.10"),
        risk_tier="HIGH",
        comparison_data=[],
        explanation_data={"primary_reason": "High RTO risk COD order requires OTP verification"},
    )
    db_session.add(eval_rec)
    db_session.commit()

    # 2. Dispatch WhatsApp OTP
    res_otp = client.post(
        "/api/v1/integrations/whatsapp/send-otp",
        json={"order_id": str(order.id)},
        headers=headers,
    )
    assert res_otp.status_code == 200
    otp_data = res_otp.json()
    assert otp_data["status"] == "SENT"
    assert otp_data["recipient_phone"] == customer_phone
    assert Decimal(str(otp_data["intervention_cost"])) == Decimal("0.80")

    # 3. Customer replies "CONFIRM" via WhatsApp
    msg_id = f"wamid.reply_confirm_{uuid4().hex[:12]}"
    payload_confirm = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "101928374650123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [
                                {
                                    "id": msg_id,
                                    "from": "919988776655",
                                    "timestamp": "1710000040",
                                    "type": "button",
                                    "button": {"payload": "CONFIRM_ORDER", "text": "CONFIRM"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload_confirm).encode("utf-8")
    sig = compute_whatsapp_signature(body, app_secret)

    res_webhook = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res_webhook.status_code == 200

    # 4. Verify order transitioned to CONFIRMED
    db_session.refresh(order)
    db_session.refresh(eval_rec)
    assert order.status == "CONFIRMED"
    assert eval_rec.intervention_status == "OTP_VERIFIED"


# =============================================================================
# 8. Customer CANCEL Reply Safety Invariant Tests
# =============================================================================


def test_whatsapp_customer_cancel_held_for_review(client: TestClient, whatsapp_test_setup, db_session):
    setup = whatsapp_test_setup
    org = setup["org"]
    app_secret = setup["app_secret"]
    phone_id = setup["phone_number_id"]
    customer_phone = "+919876500000"

    order = Order(
        org_id=org.id,
        external_order_id="ORD-WA-COD-CANCEL-1",
        order_value=Decimal("1999.00"),
        payment_method="COD",
        status="PENDING",
        customer_name="Pooja Hegde",
        customer_phone=customer_phone,
        shipping_country="India",
        source_channel="SHOPIFY",
    )
    db_session.add(order)
    db_session.commit()

    # Customer replies "CANCEL" via WhatsApp
    msg_id = f"wamid.reply_cancel_{uuid4().hex[:12]}"
    payload_cancel = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "101928374650123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [
                                {
                                    "id": msg_id,
                                    "from": "919876500000",
                                    "timestamp": "1710000050",
                                    "type": "text",
                                    "text": {"body": "CANCEL"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload_cancel).encode("utf-8")
    sig = compute_whatsapp_signature(body, app_secret)

    res = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200

    # Invariant Verification: Order is held on HOLD, NEVER cancelled automatically without operator review
    db_session.refresh(order)
    assert order.status == "HOLD"
    assert order.status != "CANCELLED"


# =============================================================================
# 9. NDR Customer Recovery Flow Tests
# =============================================================================


def test_whatsapp_ndr_recovery_flow(client: TestClient, whatsapp_test_setup, db_session):
    setup = whatsapp_test_setup
    org = setup["org"]
    headers = setup["headers"]
    customer_phone = "+919112233445"

    order = Order(
        org_id=org.id,
        external_order_id="ORD-WA-NDR-1",
        order_value=Decimal("3200.00"),
        payment_method="COD",
        status="NDR",
        customer_name="Sunil Gavaskar",
        customer_phone=customer_phone,
        shipping_country="India",
        source_channel="SHOPIFY",
    )
    db_session.add(order)
    db_session.flush()

    ndr_case = NDRCase(
        org_id=org.id,
        order_id=order.id,
        case_number="NDR-WA-001",
        status="OPEN",
        priority="HIGH",
        reason_code="CUSTOMER_UNAVAILABLE",
    )
    db_session.add(ndr_case)
    db_session.commit()

    # Dispatch WhatsApp NDR Recovery
    res_ndr = client.post(
        "/api/v1/integrations/whatsapp/send-ndr-recovery",
        json={"ndr_case_id": str(ndr_case.id), "notes": "Dispatched automated WhatsApp template"},
        headers=headers,
    )
    assert res_ndr.status_code == 200
    ndr_res_data = res_ndr.json()
    assert ndr_res_data["status"] == "SENT"
    assert ndr_res_data["recipient_phone"] == customer_phone
    assert Decimal(str(ndr_res_data["intervention_cost"])) == Decimal("0.80")

    db_session.refresh(ndr_case)
    assert ndr_case.customer_contacted is True
    assert ndr_case.contact_method == "WHATSAPP"
    assert ndr_case.status == "IN_PROGRESS"
