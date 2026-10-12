"""Common Integration Event Abstractions and Provider Adapters.

Operational & Security Guidelines:
1. Standardizes webhook ingest across external platforms (Shopify, future WhatsApp Business, courier providers).
2. Enforces cryptographic signature verification before payload processing.
3. Masks all credential tokens, private customer keys, and sensitive financial data in audit summaries.
4. Purely non-authoritative adapter interface: does not invent fake provider credentials or mock connections.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import re
import copy


class IntegrationProvider(str, Enum):
    SHOPIFY = "SHOPIFY"
    WHATSAPP = "WHATSAPP"
    COURIER_BLUEDART = "COURIER_BLUEDART"
    COURIER_DELHIVERY = "COURIER_DELHIVERY"
    COURIER_SHIPROCKET = "COURIER_SHIPROCKET"
    GENERIC = "GENERIC"


class IntegrationEventType(str, Enum):
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_UPDATED = "ORDER_UPDATED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_FULFILLED = "ORDER_FULFILLED"
    TRACKING_UPDATE = "TRACKING_UPDATE"
    NDR_EVENT = "NDR_EVENT"
    CUSTOMER_COMMUNICATION = "CUSTOMER_COMMUNICATION"
    UNKNOWN = "UNKNOWN"


@dataclass
class StandardizedIntegrationEvent:
    """Normalized carrier/platform event representation."""
    provider: IntegrationProvider
    event_id: str
    event_type: IntegrationEventType
    raw_topic: str
    shop_or_account_id: str
    timestamp: datetime
    payload: Dict[str, Any]
    signature_verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# Keys whose values must be redacted in event audit logs and summaries
SENSITIVE_KEY_PATTERNS: Set[str] = {
    "token", "secret", "password", "key", "authorization",
    "access_token", "client_secret", "signature", "hmac",
    "credit_card", "cvv", "card_number", "pin"
}


def sanitize_dict_for_logging(data: Any) -> Any:
    """Recursively redacts sensitive keys and values from dictionaries before logging."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            key_lower = str(k).lower()
            if any(p in key_lower for p in SENSITIVE_KEY_PATTERNS):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                cleaned[k] = sanitize_dict_for_logging(v)
            else:
                cleaned[k] = v
        return cleaned
    elif isinstance(data, list):
        return [sanitize_dict_for_logging(item) for item in data]
    return data


class BaseIntegrationAdapter(ABC):
    """Abstract base class for all external service webhooks and event adapters."""

    @property
    @abstractmethod
    def provider(self) -> IntegrationProvider:
        """Returns the provider type."""
        pass

    @abstractmethod
    def verify_signature(self, raw_body: bytes, signature: str, secret: str) -> bool:
        """Verifies cryptographic signature against raw request body."""
        pass

    @abstractmethod
    def parse_webhook(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> StandardizedIntegrationEvent:
        """Parses and maps the raw payload and headers into a StandardizedIntegrationEvent."""
        pass

    def redact_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Returns a sanitized copy of the payload with secrets redacted."""
        return sanitize_dict_for_logging(payload)
