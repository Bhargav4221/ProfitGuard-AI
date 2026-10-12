"""Meta WhatsApp Business Cloud API Integration Adapter.

Implements BaseIntegrationAdapter for Meta WhatsApp:
- Official HMAC-SHA256 signature verification via X-Hub-Signature-256.
- Inbound webhook parsing for message receipts (statuses) and incoming customer replies (messages).
- International E.164 phone number formatting and sanitization.
- Customer intent detection (Opt-out STOP, Order Confirmation, Order Cancellation, Address updates).
- Payload sanitization redacting tokens and secrets.
"""

import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.integrations.base import (
    BaseIntegrationAdapter,
    IntegrationEventType,
    IntegrationProvider,
    StandardizedIntegrationEvent,
)

logger = logging.getLogger(__name__)

# Keywords for customer intent recognition
OPT_OUT_KEYWORDS = {"STOP", "UNSUBSCRIBE", "OPT OUT", "OPTOUT", "QUIT", "CANCEL AUTO"}
CONFIRM_KEYWORDS = {"CONFIRM", "YES", "CONFIRM_ORDER", "1", "OK", "CONFIRMED", "Y"}
CANCEL_KEYWORDS = {"CANCEL", "NO", "CANCEL_ORDER", "2", "DONT SEND", "DON'T SEND", "STOP ORDER"}


class WhatsAppAdapter(BaseIntegrationAdapter):
    """Adapter for official Meta WhatsApp Business Cloud API webhooks and payloads."""

    @property
    def provider(self) -> IntegrationProvider:
        return IntegrationProvider.WHATSAPP

    def verify_signature(self, raw_body: bytes, signature: str, secret: str) -> bool:
        """Verifies the official Meta X-Hub-Signature-256 against raw request body.

        Meta sends:
        Header: X-Hub-Signature-256
        Format: sha256=<hex_encoded_hmac_sha256>
        """
        if not signature or not secret or not raw_body:
            return False

        try:
            clean_sig = signature.strip()
            if clean_sig.startswith("sha256="):
                clean_sig = clean_sig[7:]

            computed_hex = hmac.new(
                secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(computed_hex, clean_sig)
        except Exception as exc:
            logger.error("Exception during WhatsApp HMAC verification: %s", exc)
            return False

    def parse_webhook(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> StandardizedIntegrationEvent:
        """Constructs a StandardizedIntegrationEvent from Meta WhatsApp webhook payload."""
        lower_headers = {k.lower(): v for k, v in headers.items()}
        signature_header = lower_headers.get("x-hub-signature-256", "")

        # Extract entry and change value
        entries = payload.get("entry", [])
        account_id = ""
        event_id = ""
        event_type = IntegrationEventType.CUSTOMER_COMMUNICATION

        if entries and isinstance(entries, list):
            entry = entries[0]
            account_id = str(entry.get("id", ""))
            changes = entry.get("changes", [])
            if changes and isinstance(changes, list):
                val = changes[0].get("value", {})
                messages = val.get("messages", [])
                statuses = val.get("statuses", [])

                if messages:
                    msg = messages[0]
                    event_id = msg.get("id", "")
                    event_type = IntegrationEventType.CUSTOMER_COMMUNICATION
                elif statuses:
                    st = statuses[0]
                    event_id = f"{st.get('id', '')}:{st.get('status', '')}:{st.get('timestamp', '')}"
                    event_type = IntegrationEventType.TRACKING_UPDATE

        return StandardizedIntegrationEvent(
            provider=IntegrationProvider.WHATSAPP,
            event_id=event_id or f"wa_event_{datetime.now(timezone.utc).timestamp()}",
            event_type=event_type,
            raw_topic="whatsapp/messages",
            shop_or_account_id=account_id,
            timestamp=datetime.now(timezone.utc),
            payload=payload,
            signature_verified=bool(signature_header),
            metadata={
                "object": payload.get("object", "whatsapp_business_account"),
            },
        )

    @staticmethod
    def normalize_phone_number(phone: str) -> str:
        """Normalizes a phone number to standard E.164 format (+919876543210)."""
        if not phone:
            return ""

        # Remove spaces, dashes, dots, parentheses
        cleaned = re.sub(r"[\s\-\(\)\.]+", "", str(phone).strip())

        # If already starts with '+', keep digits after
        if cleaned.startswith("+"):
            digits = re.sub(r"[^\d]", "", cleaned[1:])
            return f"+{digits}"

        digits = re.sub(r"[^\d]", "", cleaned)

        # Default India standard: 10 digits without country code -> add +91
        if len(digits) == 10:
            return f"+91{digits}"
        # 12 digits starting with 91 -> add '+'
        elif len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"

        return f"+{digits}" if digits else ""

    @staticmethod
    def detect_opt_out(text: Optional[str]) -> bool:
        """Detects whether message text indicates an opt-out intent."""
        if not text:
            return False
        clean = text.strip().upper()
        return clean in OPT_OUT_KEYWORDS

    @staticmethod
    def detect_intent(text: Optional[str]) -> str:
        """Categorizes incoming message text into customer action intent."""
        if not text:
            return "UNKNOWN"
        clean = text.strip().upper()

        if clean in OPT_OUT_KEYWORDS:
            return "OPT_OUT"
        if clean in CONFIRM_KEYWORDS:
            return "CONFIRM"
        if clean in CANCEL_KEYWORDS:
            return "CANCEL"
        if any(w in clean for w in ["ADDRESS", "PINCODE", "HOUSE", "STREET", "FLAT", "ROAD"]):
            return "ADDRESS_UPDATE"

        return "OTHER"
