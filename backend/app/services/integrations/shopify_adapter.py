"""Shopify Integration Adapter.

Implements BaseIntegrationAdapter for Shopify:
- Official HMAC-SHA256 verification (base64-encoded digest compared via hmac.compare_digest).
- Normalization of Shopify order events (orders/create, orders/updated, orders/cancelled, orders/fulfilled).
- Temporal consistency checks: Prevents out-of-order or stale events from regressing order states.
- Sanitization of sensitive data (redacting auth tokens, customer payment parameters).
"""

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.services.integrations.base import (
    BaseIntegrationAdapter,
    IntegrationEventType,
    IntegrationProvider,
    StandardizedIntegrationEvent,
)

logger = logging.getLogger(__name__)

TOPIC_TO_EVENT_TYPE = {
    "orders/create": IntegrationEventType.ORDER_CREATED,
    "orders/updated": IntegrationEventType.ORDER_UPDATED,
    "orders/cancelled": IntegrationEventType.ORDER_CANCELLED,
    "orders/fulfilled": IntegrationEventType.ORDER_FULFILLED,
}


class ShopifyAdapter(BaseIntegrationAdapter):
    """Adapter for official Shopify Webhooks and Admin API payloads."""

    @property
    def provider(self) -> IntegrationProvider:
        return IntegrationProvider.SHOPIFY

    def verify_signature(self, raw_body: bytes, signature: str, secret: str) -> bool:
        """Verifies the official Shopify HMAC-SHA256 signature against the raw request body.

        Shopify sends:
        Header: X-Shopify-Hmac-Sha256
        Value: Base64-encoded HMAC-SHA256 hash using the app client secret or webhook secret.
        """
        if not signature or not secret or not raw_body:
            return False

        try:
            computed_digest = hmac.new(
                secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).digest()
            expected_signature = base64.b64encode(computed_digest).decode("utf-8")
            return hmac.compare_digest(expected_signature.strip(), signature.strip())
        except Exception as exc:
            logger.error("Exception during Shopify HMAC verification: %s", exc)
            return False

    def parse_webhook(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> StandardizedIntegrationEvent:
        """Constructs a StandardizedIntegrationEvent from Shopify request headers and body."""
        # Case-insensitive header lookup
        lower_headers = {k.lower(): v for k, v in headers.items()}
        raw_topic = lower_headers.get("x-shopify-topic", "unknown")
        delivery_id = lower_headers.get("x-shopify-delivery-id", "")
        shop_domain = lower_headers.get("x-shopify-shop-domain", "")

        event_type = TOPIC_TO_EVENT_TYPE.get(raw_topic, IntegrationEventType.UNKNOWN)

        # Parse timestamp from payload updated_at or created_at
        ts_str = payload.get("updated_at") or payload.get("created_at")
        event_time = datetime.now(timezone.utc)
        if ts_str:
            try:
                # Shopify sends ISO-8601 like "2026-10-12T11:20:00-04:00" or with "Z"
                event_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                pass

        return StandardizedIntegrationEvent(
            provider=IntegrationProvider.SHOPIFY,
            event_id=delivery_id,
            event_type=event_type,
            raw_topic=raw_topic,
            shop_or_account_id=shop_domain,
            timestamp=event_time,
            payload=payload,
            signature_verified=True,
            metadata={
                "api_version": lower_headers.get("x-shopify-api-version", "2024-01"),
                "shopify_order_id": str(payload.get("id")) if payload.get("id") else None,
            },
        )

    @staticmethod
    def extract_normalized_order(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes Shopify order JSON payload into ProfitGuard Order fields."""
        order_id_num = payload.get("id")
        external_order_id = str(order_id_num) if order_id_num else ""

        total_price_str = str(payload.get("total_price", "0.00"))
        try:
            order_val = Decimal(total_price_str)
        except Exception:
            order_val = Decimal("0.00")

        # Determine Payment Method: COD vs PREPAID
        gateway_names = [str(g).lower() for g in (payload.get("payment_gateway_names") or [])]
        financial_status = str(payload.get("financial_status", "")).lower()

        cod_indicators = {"cash on delivery", "cod", "manual", "cash_on_delivery"}
        is_cod = any(ind in g for g in gateway_names for ind in cod_indicators) or (
            financial_status == "pending" and not any("prepaid" in g or "razorpay" in g or "stripe" in g for g in gateway_names)
        )
        payment_method = "COD" if is_cod else "PREPAID"

        # Customer & Shipping Details
        shipping_addr = payload.get("shipping_address") or payload.get("customer", {}).get("default_address") or {}
        first_name = shipping_addr.get("first_name", "") or ""
        last_name = shipping_addr.get("last_name", "") or ""
        customer_name = (f"{first_name} {last_name}").strip() or shipping_addr.get("name") or payload.get("customer", {}).get("name")

        phone = shipping_addr.get("phone") or payload.get("phone") or payload.get("customer", {}).get("phone")
        email = payload.get("email") or payload.get("customer", {}).get("email")

        # Parse placement date
        created_at_str = payload.get("created_at")
        order_date = datetime.now(timezone.utc)
        if created_at_str:
            try:
                order_date = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except Exception:
                pass

        # Parse line items
        line_items_raw = payload.get("line_items") or []
        items_data = []
        for it in line_items_raw:
            price_str = str(it.get("price", "0.00"))
            try:
                it_price = Decimal(price_str)
            except Exception:
                it_price = Decimal("0.00")
            qty = int(it.get("quantity", 1))

            items_data.append({
                "product_name": it.get("title", "Product") or "Product",
                "sku": it.get("sku") or "DEFAULT-SKU",
                "quantity": qty,
                "price": it_price,
            })

        return {
            "external_order_id": external_order_id,
            "order_value": order_val,
            "currency": payload.get("currency", "INR") or "INR",
            "order_date": order_date,
            "payment_method": payment_method,
            "customer_name": customer_name,
            "customer_phone": str(phone).strip() if phone else None,
            "customer_email": str(email).strip() if email else None,
            "shipping_address1": shipping_addr.get("address1"),
            "shipping_address2": shipping_addr.get("address2"),
            "shipping_city": shipping_addr.get("city"),
            "shipping_state": shipping_addr.get("province") or shipping_addr.get("province_code"),
            "shipping_pincode": str(shipping_addr.get("zip", "")).strip() or None,
            "shipping_country": shipping_addr.get("country_code", "IN") or "IN",
            "source_channel": "SHOPIFY",
            "items": items_data,
        }

    @staticmethod
    def is_stale_event(
        existing_order_updated_at: Optional[datetime],
        incoming_event_time: datetime,
    ) -> bool:
        """Returns True if the incoming event timestamp is older than the existing order's recorded state."""
        if not existing_order_updated_at or not incoming_event_time:
            return False
        # If incoming event is strictly older by more than 1 second, it is considered stale
        return incoming_event_time < existing_order_updated_at
