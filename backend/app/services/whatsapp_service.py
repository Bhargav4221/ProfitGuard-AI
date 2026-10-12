"""Meta WhatsApp Business Cloud API Integration Service.

Provides:
- Tenant-isolated credential configuration and AES-256-GCM token encryption.
- Multi-mode messaging: MOCK (local/CI), META_TEST (Meta test numbers), and LIVE (production WABA).
- Outbound template and interactive messaging for COD OTP verification and NDR delivery recovery.
- Secure GET challenge verification and POST X-Hub-Signature-256 HMAC signature verification.
- Idempotent delivery status tracking (QUEUED -> SENT -> DELIVERED -> READ / FAILED).
- Automatic customer opt-out compliance (STOP / UNSUBSCRIBE).
- Safe customer reply parsing:
  - CONFIRM: sets order intervention to OTP_VERIFIED and transitions order to CONFIRMED.
  - CANCEL: places order on HOLD for operator review (strictly avoids blind autonomous cancellations).
  - ADDRESS_UPDATE: enriches active NDR recovery cases.
- Economic intervention cost tracking recorded for financial reconciliation.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import AESGCMCryptoService, crypto_service
from app.models.delivery import DeliveryEvent, NDRActionLog, NDRCase
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.whatsapp import (
    WhatsAppConfig,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppWebhookEvent,
)
from app.schemas.delivery import DeliveryEventCreate
from app.schemas.whatsapp import (
    WhatsAppConfigIn,
    WhatsAppTestConnectionOut,
)
from app.services.audit_service import AuditService
from app.services.decision_engine import DecisionEngineService
from app.services.delivery_service import DeliveryService
from app.services.integrations.whatsapp_adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)

STANDARD_WHATSAPP_INTERVENTION_COST = Decimal("0.80")


class WhatsAppService:
    adapter = WhatsAppAdapter()

    @classmethod
    def get_config(cls, org_id: UUID, session: Session) -> Optional[WhatsAppConfig]:
        """Returns the WhatsApp configuration record for the given tenant."""
        return session.scalar(
            select(WhatsAppConfig).where(WhatsAppConfig.org_id == org_id)
        )

    @classmethod
    def get_or_create_config(cls, org_id: UUID, session: Session) -> WhatsAppConfig:
        """Retrieves existing config or initializes a default record."""
        conf = cls.get_config(org_id, session)
        if not conf:
            conf = WhatsAppConfig(
                org_id=org_id,
                operating_mode=getattr(settings, "WHATSAPP_OPERATING_MODE", "MOCK"),
                status="NOT_CONFIGURED",
                webhook_verify_token=getattr(
                    settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "profitguard_whatsapp_verify_token_default"
                ),
                api_version=getattr(settings, "WHATSAPP_API_VERSION", "v20.0"),
            )
            session.add(conf)
            session.flush()
        return conf

    @classmethod
    def configure_config(
        cls,
        org_id: UUID,
        config_in: WhatsAppConfigIn,
        session: Session,
        actor_user_id: Optional[UUID] = None,
    ) -> WhatsAppConfig:
        """Configures or updates merchant WhatsApp credentials, encrypting sensitive tokens."""
        conf = cls.get_or_create_config(org_id, session)

        conf.phone_number_id = config_in.phone_number_id.strip()
        conf.business_account_id = config_in.business_account_id.strip() if config_in.business_account_id else None
        conf.operating_mode = config_in.operating_mode
        conf.api_version = config_in.api_version.strip()
        if config_in.webhook_verify_token:
            conf.webhook_verify_token = config_in.webhook_verify_token.strip()

        # Encrypt sensitive tokens using AES-256-GCM
        if config_in.access_token:
            conf.access_token_encrypted = crypto_service.encrypt(config_in.access_token.strip())
        if config_in.app_secret:
            conf.app_secret_encrypted = crypto_service.encrypt(config_in.app_secret.strip())

        conf.status = "ACTIVE"
        conf.last_error = None

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="WHATSAPP_CONFIGURED",
            resource_type="WhatsAppConfig",
            resource_id=str(conf.id),
            payload={
                "phone_number_id": conf.phone_number_id,
                "business_account_id": conf.business_account_id,
                "operating_mode": conf.operating_mode,
                "has_access_token": bool(conf.access_token_encrypted),
                "has_app_secret": bool(conf.app_secret_encrypted),
            },
        )

        session.commit()
        session.refresh(conf)
        return conf

    @classmethod
    def disconnect_config(
        cls,
        org_id: UUID,
        session: Session,
        actor_user_id: Optional[UUID] = None,
    ) -> WhatsAppConfig:
        """Disconnects WhatsApp credentials and sets status to DISCONNECTED."""
        conf = cls.get_config(org_id, session)
        if not conf:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No WhatsApp configuration found for this organization.",
            )

        conf.access_token_encrypted = None
        conf.app_secret_encrypted = None
        conf.status = "DISCONNECTED"

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="WHATSAPP_DISCONNECTED",
            resource_type="WhatsAppConfig",
            resource_id=str(conf.id),
            payload={"status": "DISCONNECTED"},
        )

        session.commit()
        session.refresh(conf)
        return conf

    @classmethod
    def test_connection(cls, org_id: UUID, session: Session) -> WhatsAppTestConnectionOut:
        """Tests live or mock connectivity with Meta WhatsApp Cloud API."""
        conf = cls.get_config(org_id, session)
        mode = conf.operating_mode if conf else getattr(settings, "WHATSAPP_OPERATING_MODE", "MOCK")

        if mode == "MOCK":
            phone_id = conf.phone_number_id if conf else None
            return WhatsAppTestConnectionOut(
                connected=True,
                operating_mode="MOCK",
                phone_number_id=phone_id,
                display_phone_number="+1 555-0100",
                verified_name="ProfitGuard AI",
                quality_rating="GREEN",
                message="Local test connection healthy. Outbound and inbound messages verified locally.",
            )

        # In META_TEST or LIVE, check for credentials
        phone_id = (conf.phone_number_id if conf else None) or getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
        access_token = None
        if conf and conf.access_token_encrypted:
            try:
                access_token = crypto_service.decrypt(conf.access_token_encrypted)
            except Exception as e:
                logger.error("Failed to decrypt WhatsApp access token: %s", e)
        if not access_token:
            access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)

        if not phone_id or not access_token:
            return WhatsAppTestConnectionOut(
                connected=False,
                operating_mode=mode,
                phone_number_id=phone_id,
                message="Missing Phone Number ID or Access Token. Configure credentials first.",
            )

        api_version = (conf.api_version if conf else None) or getattr(settings, "WHATSAPP_API_VERSION", "v20.0")
        url = f"https://graph.facebook.com/{api_version}/{phone_id}?fields=verified_name,code_verification_status,display_phone_number,quality_rating"

        try:
            with httpx.Client(timeout=getattr(settings, "WHATSAPP_REQUEST_TIMEOUT_SECONDS", 10.0)) as client:
                resp = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
                if resp.is_success:
                    data = resp.json()
                    verified_name = data.get("verified_name")
                    display_num = data.get("display_phone_number")
                    quality = data.get("quality_rating", "UNKNOWN")

                    if conf:
                        conf.verified_name = verified_name
                        conf.quality_rating = quality
                        conf.status = "ACTIVE"
                        conf.last_error = None
                        session.commit()

                    return WhatsAppTestConnectionOut(
                        connected=True,
                        operating_mode=mode,
                        phone_number_id=phone_id,
                        display_phone_number=display_num,
                        verified_name=verified_name,
                        quality_rating=quality,
                        message="Meta WhatsApp Business API connection verified successfully.",
                    )
                else:
                    err_msg = resp.text
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message", resp.text)
                    except Exception:
                        pass

                    if conf:
                        conf.last_error = err_msg
                        conf.status = "ERROR"
                        session.commit()

                    return WhatsAppTestConnectionOut(
                        connected=False,
                        operating_mode=mode,
                        phone_number_id=phone_id,
                        message=f"Meta Graph API error ({resp.status_code}): {err_msg}",
                    )
        except Exception as exc:
            logger.error("Exception during WhatsApp connection test: %s", exc)
            return WhatsAppTestConnectionOut(
                connected=False,
                operating_mode=mode,
                phone_number_id=phone_id,
                message=f"Network error connecting to Meta Graph API: {str(exc)}",
            )

    @classmethod
    def is_opted_out(cls, org_id: UUID, phone_number: str, session: Session) -> bool:
        """Checks whether a phone number has opted out of automated WhatsApp messages."""
        norm_phone = cls.adapter.normalize_phone_number(phone_number)
        if not norm_phone:
            return False
        return bool(
            session.scalar(
                select(WhatsAppOptOut).where(
                    WhatsAppOptOut.org_id == org_id,
                    WhatsAppOptOut.phone_number == norm_phone,
                )
            )
        )

    @classmethod
    def record_opt_out(
        cls,
        org_id: UUID,
        phone_number: str,
        reason: str,
        session: Session,
    ) -> WhatsAppOptOut:
        """Registers a phone number in the opt-out registry."""
        norm_phone = cls.adapter.normalize_phone_number(phone_number)
        existing = session.scalar(
            select(WhatsAppOptOut).where(
                WhatsAppOptOut.org_id == org_id,
                WhatsAppOptOut.phone_number == norm_phone,
            )
        )
        if existing:
            return existing

        opt_out = WhatsAppOptOut(
            org_id=org_id,
            phone_number=norm_phone,
            reason=reason,
            opted_out_at=datetime.now(timezone.utc),
        )
        session.add(opt_out)
        session.commit()
        session.refresh(opt_out)
        return opt_out

    @classmethod
    def send_message(
        cls,
        org_id: UUID,
        recipient_phone: str,
        message_type: str = "TEMPLATE",
        template_name: Optional[str] = None,
        template_components: Optional[List[Dict[str, Any]]] = None,
        text_body: Optional[str] = None,
        order_id: Optional[UUID] = None,
        ndr_case_id: Optional[UUID] = None,
        session: Optional[Session] = None,
        actor_user_id: Optional[UUID] = None,
    ) -> WhatsAppMessage:
        """Sends an outbound WhatsApp message via Meta Cloud API or mock simulator.
        
        Strictly enforces:
        - E.164 phone number formatting.
        - Opt-out registry check before dispatch.
        - Status lifecycle (QUEUED -> SENT -> DELIVERED -> READ / FAILED).
        - Deduction of intervention communication cost for economic tracking.
        """
        if session is None:
            raise ValueError("Database session is required.")

        norm_phone = cls.adapter.normalize_phone_number(recipient_phone)
        if not norm_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid recipient phone number format: '{recipient_phone}'",
            )

        # Check opt-out policy
        if cls.is_opted_out(org_id, norm_phone, session):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot send message: Recipient '{norm_phone}' has opted out (STOP) of automated WhatsApp messages.",
            )

        conf = cls.get_config(org_id, session)
        mode = conf.operating_mode if conf else getattr(settings, "WHATSAPP_OPERATING_MODE", "MOCK")
        phone_id = (conf.phone_number_id if conf else None) or getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)

        preview = text_body or f"Template: {template_name or 'generic_notification'}"

        msg = WhatsAppMessage(
            org_id=org_id,
            whatsapp_config_id=conf.id if conf else None,
            order_id=order_id,
            ndr_case_id=ndr_case_id,
            direction="OUTBOUND",
            recipient_phone=norm_phone,
            sender_phone=phone_id or "ProfitGuard AI",
            message_type=message_type,
            template_name=template_name,
            body_preview=preview,
            status="QUEUED",
            intervention_cost=STANDARD_WHATSAPP_INTERVENTION_COST,
        )
        session.add(msg)
        session.flush()

        # Handle MOCK Mode
        if mode == "MOCK":
            msg.wamid = f"wamid.mock_{uuid4().hex[:20]}"
            msg.status = "SENT"
            msg.sent_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(msg)
            return msg

        # Handle META_TEST or LIVE Mode
        access_token = None
        if conf and conf.access_token_encrypted:
            try:
                access_token = crypto_service.decrypt(conf.access_token_encrypted)
            except Exception as e:
                logger.error("Failed to decrypt WhatsApp access token: %s", e)
        if not access_token:
            access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)

        if not phone_id or not access_token:
            msg.status = "FAILED"
            msg.error_code = "CREDENTIALS_MISSING"
            msg.error_message = "Meta Phone Number ID or Access Token is missing."
            session.commit()
            session.refresh(msg)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=msg.error_message,
            )

        api_version = (conf.api_version if conf else None) or getattr(settings, "WHATSAPP_API_VERSION", "v20.0")
        url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"

        # Construct Meta Graph API payload
        target_to = norm_phone.replace("+", "")
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target_to,
        }

        if message_type == "TEMPLATE":
            payload["type"] = "template"
            payload["template"] = {
                "name": template_name or "order_confirmation_cod",
                "language": {"code": "en_US"},
            }
            if template_components:
                payload["template"]["components"] = template_components
        else:
            payload["type"] = "text"
            payload["text"] = {"preview_url": False, "body": text_body or ""}

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=getattr(settings, "WHATSAPP_REQUEST_TIMEOUT_SECONDS", 10.0)) as client:
                resp = client.post(url, json=payload, headers=headers)
                msg.raw_payload = cls.adapter.redact_payload(resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"body": resp.text})

                if resp.is_success:
                    res_json = resp.json()
                    messages = res_json.get("messages", [])
                    if messages:
                        msg.wamid = messages[0].get("id")
                    msg.status = "SENT"
                    msg.sent_at = datetime.now(timezone.utc)
                else:
                    msg.status = "FAILED"
                    try:
                        err_info = resp.json().get("error", {})
                        msg.error_code = str(err_info.get("code", resp.status_code))
                        msg.error_message = err_info.get("message", resp.text)
                    except Exception:
                        msg.error_code = str(resp.status_code)
                        msg.error_message = resp.text
        except Exception as exc:
            logger.error("Network error sending WhatsApp message: %s", exc)
            msg.status = "FAILED"
            msg.error_code = "NETWORK_ERROR"
            msg.error_message = str(exc)

        session.commit()
        session.refresh(msg)

        if msg.status == "FAILED":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Meta WhatsApp dispatch failed: {msg.error_message}",
            )

        return msg

    @classmethod
    def send_cod_verification(
        cls,
        order_id: UUID,
        org_id: UUID,
        session: Session,
        recipient_phone: Optional[str] = None,
        actor_user_id: Optional[UUID] = None,
    ) -> WhatsAppMessage:
        """Sends an interactive COD confirmation message to customer phone number."""
        order = session.scalar(
            select(Order).where(Order.id == order_id, Order.org_id == org_id)
        )
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

        if order.payment_method != "COD":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WhatsApp COD verification can only be dispatched for Cash on Delivery orders.",
            )

        target_phone = recipient_phone or order.customer_phone
        if not target_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer phone number is missing from this order.",
            )

        order_identifier = order.external_order_id or (order.order_number if hasattr(order, "order_number") else str(order.id)[:8])
        order_val_str = f"₹{order.order_value:,.2f}"

        template_name = "order_confirmation_cod"
        template_components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": order.customer_name or "Valued Customer"},
                    {"type": "text", "text": order_identifier},
                    {"type": "text", "text": order_val_str},
                ],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [{"type": "payload", "payload": "CONFIRM_ORDER"}],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "1",
                "parameters": [{"type": "payload", "payload": "CANCEL_ORDER"}],
            },
        ]

        text_preview = (
            f"Hello {order.customer_name or 'Customer'}, please confirm your Cash on Delivery order "
            f"#{order_identifier} of {order_val_str}. Reply 'CONFIRM' to verify or 'CANCEL' to cancel."
        )

        message = cls.send_message(
            org_id=org_id,
            recipient_phone=target_phone,
            message_type="TEMPLATE",
            template_name=template_name,
            template_components=template_components,
            text_body=text_preview,
            order_id=order.id,
            session=session,
            actor_user_id=actor_user_id,
        )

        # Update evaluation intervention notes
        evaluation = session.scalar(
            select(OrderEvaluation)
            .where(OrderEvaluation.order_id == order.id, OrderEvaluation.org_id == org_id)
            .order_by(OrderEvaluation.created_at.desc())
        )
        if evaluation:
            evaluation.intervention_status = "PENDING"
            evaluation.intervention_notes = f"WhatsApp verification dispatched ({message.status}) to {target_phone}."

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="WHATSAPP_COD_OTP_SENT",
            resource_type="Order",
            resource_id=str(order.id),
            payload={
                "message_id": str(message.id),
                "wamid": message.wamid,
                "phone": message.recipient_phone,
                "order_value": str(order.order_value),
            },
        )

        session.commit()
        return message

    @classmethod
    def send_ndr_recovery(
        cls,
        ndr_case_id: UUID,
        org_id: UUID,
        session: Session,
        recipient_phone: Optional[str] = None,
        notes: Optional[str] = None,
        actor_user_id: Optional[UUID] = None,
    ) -> WhatsAppMessage:
        """Sends an NDR customer recovery message for address verification and reattempt."""
        case = session.scalar(
            select(NDRCase).where(NDRCase.id == ndr_case_id, NDRCase.org_id == org_id)
        )
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NDR case not found.")

        order = case.order
        target_phone = recipient_phone or case.updated_phone or order.customer_phone
        if not target_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer phone number is missing from NDR case and order.",
            )

        template_name = "ndr_delivery_recovery"
        template_components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": order.customer_name or "Valued Customer"},
                    {"type": "text", "text": order.external_order_id or case.case_number},
                    {"type": "text", "text": case.reason_code.replace("_", " ").title()},
                ],
            }
        ]

        text_preview = (
            f"Hello {order.customer_name or 'Customer'}, your delivery for order #{order.external_order_id or case.case_number} "
            f"could not be completed ({case.reason_code}). Please reply with your updated address or delivery instructions to reschedule."
        )

        message = cls.send_message(
            org_id=org_id,
            recipient_phone=target_phone,
            message_type="TEMPLATE",
            template_name=template_name,
            template_components=template_components,
            text_body=text_preview,
            order_id=order.id,
            ndr_case_id=case.id,
            session=session,
            actor_user_id=actor_user_id,
        )

        # Record NDR Action Log
        action_log = NDRActionLog(
            org_id=org_id,
            ndr_case_id=case.id,
            order_id=order.id,
            actor_user_id=actor_user_id,
            action_type="CONTACT_CUSTOMER",
            action_details={
                "contact_method": "WHATSAPP",
                "message_id": str(message.id),
                "wamid": message.wamid,
                "notes": notes or "Automated WhatsApp recovery dispatched",
            },
            intervention_cost=STANDARD_WHATSAPP_INTERVENTION_COST,
            notes=notes or "Automated WhatsApp recovery dispatched",
        )
        session.add(action_log)

        case.customer_contacted = True
        case.contact_method = "WHATSAPP"
        case.status = "IN_PROGRESS"

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="WHATSAPP_NDR_RECOVERY_SENT",
            resource_type="NDRCase",
            resource_id=str(case.id),
            payload={
                "message_id": str(message.id),
                "wamid": message.wamid,
                "phone": message.recipient_phone,
                "reason_code": case.reason_code,
            },
        )

        session.commit()
        return message

    @classmethod
    def verify_webhook_challenge(
        cls,
        hub_mode: Optional[str],
        hub_verify_token: Optional[str],
        hub_challenge: Optional[str],
        session: Session,
    ) -> str:
        """Verifies Meta GET webhook verification challenge handshake.
        
        Meta calls:
        GET /webhook?hub.mode=subscribe&hub.challenge=1158201444&hub.verify_token=your_token
        """
        if not hub_mode or hub_mode != "subscribe" or not hub_verify_token or not hub_challenge:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook verification request parameters.",
            )

        # Check if verify token matches system setting
        system_token = getattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", None)
        if system_token and hub_verify_token == system_token:
            return hub_challenge

        # Check against any tenant's configured verify token
        matched_config = session.scalar(
            select(WhatsAppConfig).where(WhatsAppConfig.webhook_verify_token == hub_verify_token)
        )
        if matched_config:
            return hub_challenge

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification token mismatch.",
        )

    @classmethod
    def handle_webhook(
        cls,
        raw_body: bytes,
        headers: Dict[str, str],
        session: Session,
    ) -> Tuple[int, Dict[str, Any]]:
        """Handles incoming POST webhooks from Meta WhatsApp Cloud API.
        
        Verifies X-Hub-Signature-256 against configured app secrets,
        deduplicates events idempotently, and processes delivery status updates and customer replies.
        """
        lower_headers = {k.lower(): v for k, v in headers.items()}
        signature = lower_headers.get("x-hub-signature-256", "")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return 400, {"status": "error", "message": "Invalid JSON body"}

        # Determine app secret for signature verification
        # 1. Check if payload contains business account id or phone number id to find tenant
        app_secret = getattr(settings, "WHATSAPP_APP_SECRET", None)
        target_config = None

        entries = payload.get("entry", [])
        if entries and isinstance(entries, list):
            entry = entries[0]
            account_id = str(entry.get("id", ""))
            changes = entry.get("changes", [])
            phone_num_id = None
            if changes and isinstance(changes, list):
                val = changes[0].get("value", {})
                phone_num_id = val.get("metadata", {}).get("phone_number_id")

            if phone_num_id:
                target_config = session.scalar(
                    select(WhatsAppConfig).where(WhatsAppConfig.phone_number_id == str(phone_num_id))
                )
            if not target_config and account_id:
                target_config = session.scalar(
                    select(WhatsAppConfig).where(WhatsAppConfig.business_account_id == account_id)
                )

        if target_config and target_config.app_secret_encrypted:
            try:
                app_secret = crypto_service.decrypt(target_config.app_secret_encrypted)
            except Exception as e:
                logger.error("Failed to decrypt tenant WhatsApp app secret: %s", e)

        # Verify signature if secret configured
        if app_secret:
            if not cls.adapter.verify_signature(raw_body, signature, app_secret):
                logger.warning("WhatsApp webhook signature verification failed.")
                return 401, {"status": "error", "message": "Invalid signature"}

        processed_count = 0
        now_utc = datetime.now(timezone.utc)

        for entry in entries:
            for change in entry.get("changes", []):
                val = change.get("value", {})
                phone_num_id = val.get("metadata", {}).get("phone_number_id")
                org_id = target_config.org_id if target_config else None

                # 1. Process Delivery Status Updates
                statuses = val.get("statuses", [])
                for st in statuses:
                    wamid = st.get("id")
                    status_name = st.get("status", "").upper()
                    ts_raw = st.get("timestamp")
                    status_time = now_utc
                    if ts_raw:
                        try:
                            status_time = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
                        except Exception:
                            pass

                    event_key = f"{wamid}:{status_name}:{ts_raw}"
                    # Check Idempotency
                    existing_ev = session.scalar(
                        select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.event_id == event_key)
                    )
                    if existing_ev:
                        continue

                    # Record event
                    event_log = WhatsAppWebhookEvent(
                        org_id=org_id,
                        event_id=event_key,
                        event_type="STATUS_UPDATE",
                        status="PROCESSED",
                        raw_payload=cls.adapter.redact_payload(st),
                    )
                    session.add(event_log)

                    # Update message record
                    msg = session.scalar(
                        select(WhatsAppMessage).where(WhatsAppMessage.wamid == wamid)
                    )
                    if msg:
                        if status_name == "SENT":
                            msg.status = "SENT"
                            msg.sent_at = status_time
                        elif status_name == "DELIVERED":
                            msg.status = "DELIVERED"
                            msg.delivered_at = status_time
                        elif status_name == "READ":
                            msg.status = "READ"
                            msg.read_at = status_time
                        elif status_name == "FAILED":
                            msg.status = "FAILED"
                            errors = st.get("errors", [])
                            if errors:
                                msg.error_code = str(errors[0].get("code", ""))
                                msg.error_message = errors[0].get("message", "Delivery failed")

                    processed_count += 1

                # 2. Process Inbound Messages & Customer Replies
                messages = val.get("messages", [])
                for incoming in messages:
                    msg_id = incoming.get("id")
                    if not msg_id:
                        continue

                    # Check Idempotency
                    existing_ev = session.scalar(
                        select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.event_id == msg_id)
                    )
                    if existing_ev:
                        continue

                    event_log = WhatsAppWebhookEvent(
                        org_id=org_id,
                        event_id=msg_id,
                        event_type="MESSAGE_RECEIVED",
                        status="PROCESSED",
                        raw_payload=cls.adapter.redact_payload(incoming),
                    )
                    session.add(event_log)

                    from_phone = cls.adapter.normalize_phone_number(incoming.get("from", ""))
                    msg_type = incoming.get("type", "text")
                    text_body = ""

                    if msg_type == "text":
                        text_body = incoming.get("text", {}).get("body", "")
                    elif msg_type == "button":
                        btn = incoming.get("button", {})
                        text_body = btn.get("payload") or btn.get("text") or ""
                    elif msg_type == "interactive":
                        inter = incoming.get("interactive", {})
                        btn_rep = inter.get("button_reply", {})
                        text_body = btn_rep.get("id") or btn_rep.get("title") or ""

                    # Record incoming WhatsApp message in database
                    inbound_msg = WhatsAppMessage(
                        org_id=org_id or (target_config.org_id if target_config else uuid.uuid4()),
                        whatsapp_config_id=target_config.id if target_config else None,
                        direction="INBOUND",
                        recipient_phone=phone_num_id or "BUSINESS",
                        sender_phone=from_phone,
                        message_type=msg_type.upper(),
                        body_preview=text_body,
                        status="DELIVERED",
                        wamid=msg_id,
                        delivered_at=now_utc,
                        raw_payload=cls.adapter.redact_payload(incoming),
                    )
                    session.add(inbound_msg)

                    # Intent Processing
                    if org_id:
                        # 1. Opt-out Check
                        if cls.adapter.detect_opt_out(text_body):
                            cls.record_opt_out(org_id, from_phone, "STOP_KEYWORD", session)
                            logger.info("Customer %s opted out of WhatsApp.", from_phone)

                        # 2. Intent Detection
                        intent = cls.adapter.detect_intent(text_body)

                        # Match latest order for this phone
                        target_order = session.scalar(
                            select(Order)
                            .where(
                                Order.org_id == org_id,
                                Order.customer_phone == from_phone,
                                Order.status.in_(["HOLD", "PENDING", "CONFIRMED"]),
                            )
                            .order_by(Order.created_at.desc())
                        )

                        if intent == "CONFIRM" and target_order:
                            inbound_msg.order_id = target_order.id
                            # If order was on HOLD or pending OTP verification, confirm it!
                            eval_record = session.scalar(
                                select(OrderEvaluation)
                                .where(
                                    OrderEvaluation.order_id == target_order.id,
                                    OrderEvaluation.org_id == org_id,
                                )
                                .order_by(OrderEvaluation.created_at.desc())
                            )
                            if eval_record and eval_record.intervention_status == "PENDING":
                                eval_record.intervention_status = "OTP_VERIFIED"
                                eval_record.intervention_notes = f"Verified via customer WhatsApp reply: '{text_body}'"
                                eval_record.intervention_resolved_at = now_utc

                            # Record Delivery Confirmation Event
                            DeliveryService.record_delivery_event(
                                org_id=org_id,
                                order_id=target_order.id,
                                event_in=DeliveryEventCreate(
                                    order_id=target_order.id,
                                    event_type="CONFIRMED",
                                    event_source="WHATSAPP_CUSTOMER",
                                    reason_description=f"Customer confirmed order via WhatsApp: '{text_body}'",
                                ),
                                session=session,
                            )
                        elif intent == "CANCEL" and target_order:
                            inbound_msg.order_id = target_order.id
                            # SAFETY INVARIANT: Never cancel automatically; hold for operator review!
                            target_order.status = "HOLD"
                            eval_record = session.scalar(
                                select(OrderEvaluation)
                                .where(
                                    OrderEvaluation.order_id == target_order.id,
                                    OrderEvaluation.org_id == org_id,
                                )
                                .order_by(OrderEvaluation.created_at.desc())
                            )
                            if eval_record:
                                eval_record.intervention_notes = (
                                    f"Customer requested cancellation via WhatsApp: '{text_body}'. "
                                    f"Order placed on HOLD for merchant review."
                                )

                            AuditService.record_event(
                                session=session,
                                org_id=org_id,
                                action="WHATSAPP_CANCEL_REQUESTED",
                                resource_type="Order",
                                resource_id=str(target_order.id),
                                payload={"response": text_body, "phone": from_phone},
                            )
                        elif intent == "ADDRESS_UPDATE":
                            # Check active NDR case
                            ndr_case = session.scalar(
                                select(NDRCase)
                                .where(
                                    NDRCase.org_id == org_id,
                                    NDRCase.status.in_(["OPEN", "IN_PROGRESS", "REATTEMPT_SCHEDULED"]),
                                )
                                .order_by(NDRCase.created_at.desc())
                            )
                            if ndr_case:
                                inbound_msg.ndr_case_id = ndr_case.id
                                ndr_case.customer_response = text_body
                                ndr_case.updated_address1 = text_body
                                action_log = NDRActionLog(
                                    org_id=org_id,
                                    ndr_case_id=ndr_case.id,
                                    order_id=ndr_case.order_id,
                                    action_type="VERIFY_ADDRESS",
                                    action_details={"source": "WHATSAPP", "reply": text_body},
                                    intervention_cost=Decimal("0.00"),
                                    notes=f"Address update received from WhatsApp reply: '{text_body}'",
                                )
                                session.add(action_log)

                    processed_count += 1

        if target_config:
            target_config.last_webhook_received_at = now_utc

        session.commit()
        return 200, {"status": "success", "processed_events": processed_count}

    @classmethod
    def list_messages(
        cls,
        org_id: UUID,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        order_id: Optional[UUID] = None,
        ndr_case_id: Optional[UUID] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[WhatsAppMessage], int]:
        """Lists message records with pagination and optional filters."""
        query = select(WhatsAppMessage).where(WhatsAppMessage.org_id == org_id)
        if order_id:
            query = query.where(WhatsAppMessage.order_id == order_id)
        if ndr_case_id:
            query = query.where(WhatsAppMessage.ndr_case_id == ndr_case_id)
        if status:
            query = query.where(WhatsAppMessage.status == status.upper())

        total = session.scalar(
            select(WhatsAppMessage)
            .where(*query._where_criteria)
            .with_only_columns(WhatsAppMessage.id)
        )
        # Count items
        items_all = list(session.scalars(query.order_by(WhatsAppMessage.created_at.desc())).all())
        total_count = len(items_all)

        offset = (page - 1) * page_size
        items = items_all[offset : offset + page_size]
        return items, total_count

    @classmethod
    def list_opt_outs(
        cls,
        org_id: UUID,
        session: Session,
    ) -> List[WhatsAppOptOut]:
        """Lists all opted-out phone numbers for this tenant."""
        return list(
            session.scalars(
                select(WhatsAppOptOut)
                .where(WhatsAppOptOut.org_id == org_id)
                .order_by(WhatsAppOptOut.opted_out_at.desc())
            ).all()
        )
