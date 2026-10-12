"""Shopify Service.

Handles:
- Tenant-scoped Shopify store configuration and credential lifecycle.
- Inbound webhook processing with official HMAC-SHA256 signature verification.
- Idempotency protection against retried/duplicate X-Shopify-Delivery-Id values.
- Automatic creation and evaluation of orders (triggering Decision Engine and shadow ML inference).
- Order lifecycle synchronization (cancellations and fulfillments).
- Strict out-of-order and stale event protection.
- Audit logging and sensitive token redaction.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import AESGCMCryptoService
from app.models.delivery import DeliveryEvent
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.shopify import ShopifyStore, ShopifyWebhookDelivery
from app.schemas.delivery import DeliveryEventCreate
from app.schemas.shopify import ShopifyStoreConfigIn
from app.services.audit_service import AuditService
from app.services.decision_engine import DecisionEngineService
from app.services.delivery_service import DeliveryService
from app.services.integrations.shopify_adapter import ShopifyAdapter

logger = logging.getLogger(__name__)


class ShopifyService:
    @staticmethod
    def normalize_domain(domain: str) -> str:
        """Cleans and normalizes store domain string."""
        clean = (domain or "").strip().lower()
        clean = clean.replace("https://", "").replace("http://", "")
        if "/" in clean:
            clean = clean.split("/")[0]
        return clean

    @classmethod
    def get_store(cls, org_id: UUID, session: Session) -> Optional[ShopifyStore]:
        """Returns the connected ShopifyStore record for an organization."""
        return session.scalar(
            select(ShopifyStore).where(ShopifyStore.org_id == org_id)
        )

    @classmethod
    def get_store_by_domain(cls, shop_domain: str, session: Session) -> Optional[ShopifyStore]:
        """Looks up a ShopifyStore by its shop domain."""
        norm_domain = cls.normalize_domain(shop_domain)
        return session.scalar(
            select(ShopifyStore).where(ShopifyStore.shop_domain == norm_domain)
        )

    @classmethod
    def configure_store(
        cls,
        org_id: UUID,
        config: ShopifyStoreConfigIn,
        session: Session,
        actor_user_id: Optional[UUID] = None,
    ) -> ShopifyStore:
        """Configures or updates a merchant's Shopify store credentials."""
        domain = cls.normalize_domain(config.shop_domain)
        if not domain or ".myshopify.com" not in domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Shopify domain. Must be in the format 'store-name.myshopify.com'.",
            )

        # Check if domain is registered under another organization
        existing_other = session.scalar(
            select(ShopifyStore).where(
                ShopifyStore.shop_domain == domain,
                ShopifyStore.org_id != org_id,
            )
        )
        if existing_other:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Shopify domain '{domain}' is already associated with another merchant organization.",
            )

        crypto = AESGCMCryptoService()
        store = cls.get_store(org_id, session)

        enc_token = None
        if config.access_token:
            enc_token = crypto.encrypt(config.access_token)

        enc_secret = None
        if config.webhook_secret:
            enc_secret = crypto.encrypt(config.webhook_secret)

        now = datetime.now(timezone.utc)
        if not store:
            store_status = "active" if (enc_token or enc_secret) else "not_configured"
            store = ShopifyStore(
                id=uuid4(),
                org_id=org_id,
                shop_domain=domain,
                access_token_encrypted=enc_token,
                webhook_secret_encrypted=enc_secret,
                status=store_status,
                scopes=config.scopes or "read_orders,write_orders",
                api_version=settings.SHOPIFY_API_VERSION,
                installed_at=now if store_status == "active" else None,
            )
            session.add(store)
        else:
            store.shop_domain = domain
            if enc_token:
                store.access_token_encrypted = enc_token
            if enc_secret:
                store.webhook_secret_encrypted = enc_secret
            if config.scopes:
                store.scopes = config.scopes
            store.status = "active" if (store.access_token_encrypted or store.webhook_secret_encrypted) else store.status
            if store.status == "active" and not store.installed_at:
                store.installed_at = now

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="SHOPIFY_STORE_CONFIGURED",
            resource_type="ShopifyStore",
            resource_id=str(store.id),
            payload={
                "shop_domain": domain,
                "status": store.status,
                "has_token": bool(store.access_token_encrypted),
                "has_secret": bool(store.webhook_secret_encrypted),
            },
        )

        session.commit()
        session.refresh(store)
        return store

    @classmethod
    def disconnect_store(
        cls,
        org_id: UUID,
        session: Session,
        actor_user_id: Optional[UUID] = None,
    ) -> Optional[ShopifyStore]:
        """Disconnects a Shopify store, revoking stored tokens and setting status to not_configured."""
        store = cls.get_store(org_id, session)
        if not store:
            return None

        store.access_token_encrypted = None
        store.webhook_secret_encrypted = None
        store.status = "not_configured"
        store.uninstalled_at = datetime.now(timezone.utc)

        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="SHOPIFY_STORE_DISCONNECTED",
            resource_type="ShopifyStore",
            resource_id=str(store.id),
            payload={"shop_domain": store.shop_domain},
        )

        session.commit()
        session.refresh(store)
        return store

    @classmethod
    def list_deliveries(
        cls,
        org_id: UUID,
        session: Session,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ShopifyWebhookDelivery], int]:
        """Returns paginated webhook deliveries for an organization."""
        query = select(ShopifyWebhookDelivery).where(ShopifyWebhookDelivery.org_id == org_id)
        from sqlalchemy import func
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        deliveries = session.scalars(
            query.order_by(ShopifyWebhookDelivery.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(deliveries), total

    @classmethod
    def handle_webhook(
        cls,
        raw_body: bytes,
        headers: Dict[str, str],
        session: Session,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Orchestrates safe processing of an inbound Shopify webhook:
        1. Validates presence of delivery ID and shop domain headers.
        2. Validates store registration and active connection status.
        3. Validates HMAC signature against store-specific or fallback secret.
        4. Detects and gracefully ignores duplicate X-Shopify-Delivery-Id attempts.
        5. Parses and executes order operations.
        6. Preserves audit logs with secret redaction.
        """
        adapter = ShopifyAdapter()
        lower_headers = {k.lower(): v for k, v in headers.items()}
        delivery_id = lower_headers.get("x-shopify-delivery-id")
        shop_domain = lower_headers.get("x-shopify-shop-domain")
        topic = lower_headers.get("x-shopify-topic", "unknown")
        hmac_header = lower_headers.get("x-shopify-hmac-sha256")

        if not delivery_id:
            logger.warning("Rejected webhook: Missing X-Shopify-Delivery-Id header.")
            return status.HTTP_400_BAD_REQUEST, {"detail": "Missing X-Shopify-Delivery-Id header."}

        if not shop_domain:
            logger.warning("Rejected webhook %s: Missing X-Shopify-Shop-Domain header.", delivery_id)
            return status.HTTP_400_BAD_REQUEST, {"detail": "Missing X-Shopify-Shop-Domain header."}

        # 1. Lookup Store Association
        store = cls.get_store_by_domain(shop_domain, session)
        if not store:
            logger.warning("Rejected webhook %s: Unknown or unregistered shop domain '%s'.", delivery_id, shop_domain)
            # Log ignored delivery record if desired, or return 404
            return status.HTTP_404_NOT_FOUND, {
                "detail": f"Unknown or unregistered Shopify store domain: '{shop_domain}'.",
            }

        if store.status not in ("active", "installed"):
            logger.warning("Rejected webhook %s: Store '%s' is not active (status=%s).", delivery_id, shop_domain, store.status)
            return status.HTTP_403_FORBIDDEN, {
                "detail": f"Store '{shop_domain}' is currently {store.status}. Configure store before sending webhooks.",
            }

        # 2. Retrieve Signing Secret
        crypto = AESGCMCryptoService()
        webhook_secret = None
        if store.webhook_secret_encrypted:
            try:
                webhook_secret = crypto.decrypt(store.webhook_secret_encrypted)
            except Exception as exc:
                logger.error("Failed to decrypt webhook secret for store %s: %s", store.shop_domain, exc)

        if not webhook_secret and settings.SHOPIFY_WEBHOOK_SECRET:
            webhook_secret = settings.SHOPIFY_WEBHOOK_SECRET

        if not webhook_secret:
            logger.error("Store %s has no webhook secret configured and no global fallback secret is set.", store.shop_domain)
            return status.HTTP_401_UNAUTHORIZED, {
                "detail": "Shopify webhook signing secret is not configured for this store.",
            }

        # 3. Cryptographic HMAC Signature Verification
        if not adapter.verify_signature(raw_body, hmac_header or "", webhook_secret):
            logger.warning("Rejected webhook %s: Invalid Shopify HMAC signature.", delivery_id)
            return status.HTTP_401_UNAUTHORIZED, {"detail": "Invalid Shopify HMAC signature."}

        # 4. Check Idempotency (Delivery Deduplication)
        existing_delivery = session.scalar(
            select(ShopifyWebhookDelivery).where(ShopifyWebhookDelivery.shopify_delivery_id == delivery_id)
        )
        if existing_delivery:
            logger.info("Duplicate delivery %s for topic %s already recorded with status %s.",
                        delivery_id, topic, existing_delivery.status)
            return status.HTTP_200_OK, {
                "status": "DUPLICATE",
                "detail": f"Delivery '{delivery_id}' has already been processed with status '{existing_delivery.status}'.",
            }

        # 5. Parse JSON Payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            logger.error("Malformed JSON payload in webhook %s: %s", delivery_id, exc)
            delivery_record = ShopifyWebhookDelivery(
                id=uuid4(),
                org_id=store.org_id,
                shopify_store_id=store.id,
                shopify_delivery_id=delivery_id,
                topic=topic,
                shop_domain=store.shop_domain,
                status="FAILED",
                error_message=f"Malformed JSON: {str(exc)}",
            )
            session.add(delivery_record)
            session.commit()
            return status.HTTP_400_BAD_REQUEST, {"detail": "Invalid JSON payload."}

        # 6. Initialize Delivery Record
        sanitized_summary = adapter.redact_payload({
            "topic": topic,
            "order_id": payload.get("id"),
            "order_number": payload.get("name") or payload.get("order_number"),
            "total_price": payload.get("total_price"),
            "currency": payload.get("currency"),
            "created_at": payload.get("created_at"),
            "financial_status": payload.get("financial_status"),
        })

        delivery_record = ShopifyWebhookDelivery(
            id=uuid4(),
            org_id=store.org_id,
            shopify_store_id=store.id,
            shopify_delivery_id=delivery_id,
            topic=topic,
            shop_domain=store.shop_domain,
            shopify_order_id=str(payload.get("id")) if payload.get("id") else None,
            status="RECEIVED",
            payload_summary=sanitized_summary,
        )
        session.add(delivery_record)
        session.flush()

        # 7. Normalize and Process Event Topics
        try:
            matched_order = None
            if topic == "orders/create":
                matched_order = cls._process_order_create(store, payload, session)
            elif topic == "orders/updated":
                matched_order = cls._process_order_updated(store, payload, session)
            elif topic == "orders/cancelled":
                matched_order = cls._process_order_cancelled(store, payload, session)
            elif topic in ("orders/fulfilled", "fulfillments/create"):
                matched_order = cls._process_order_fulfilled(store, payload, session)
            else:
                logger.info("Ignored unsupported Shopify webhook topic: %s", topic)
                delivery_record.status = "IGNORED"

            if matched_order:
                delivery_record.order_id = matched_order.id
                if delivery_record.status != "IGNORED":
                    delivery_record.status = "PROCESSED"
            elif delivery_record.status == "RECEIVED":
                delivery_record.status = "PROCESSED"

            delivery_record.processed_at = datetime.now(timezone.utc)
            session.commit()
            return status.HTTP_200_OK, {
                "status": delivery_record.status,
                "topic": topic,
                "delivery_id": delivery_id,
                "order_id": str(matched_order.id) if matched_order else None,
            }

        except Exception as exc:
            logger.error("Error processing Shopify event %s (%s): %s", delivery_id, topic, exc, exc_info=True)
            session.rollback()
            # Mark delivery as FAILED in fresh transaction
            with session.no_autoflush:
                fail_delivery = session.scalar(
                    select(ShopifyWebhookDelivery).where(ShopifyWebhookDelivery.shopify_delivery_id == delivery_id)
                )
                if not fail_delivery:
                    fail_delivery = ShopifyWebhookDelivery(
                        id=uuid4(),
                        org_id=store.org_id,
                        shopify_store_id=store.id,
                        shopify_delivery_id=delivery_id,
                        topic=topic,
                        shop_domain=store.shop_domain,
                        shopify_order_id=str(payload.get("id")) if payload.get("id") else None,
                        status="FAILED",
                        error_message=str(exc),
                    )
                    session.add(fail_delivery)
                else:
                    fail_delivery.status = "FAILED"
                    fail_delivery.error_message = str(exc)
                session.commit()

            return status.HTTP_500_INTERNAL_SERVER_ERROR, {
                "detail": f"Failed to process Shopify webhook: {str(exc)}",
            }

    @classmethod
    def _process_order_create(
        cls,
        store: ShopifyStore,
        payload: Dict[str, Any],
        session: Session,
    ) -> Order:
        """Processes orders/create webhook, persisting Order and triggering Decision Engine."""
        norm = ShopifyAdapter.extract_normalized_order(payload)
        ext_id = norm["external_order_id"]
        if not ext_id:
            raise ValueError("Shopify payload is missing order id.")

        # Check if order already exists in this tenant
        existing = session.scalar(
            select(Order).where(
                Order.org_id == store.org_id,
                Order.external_order_id == ext_id,
            )
        )
        if existing:
            logger.info("Order %s already exists for org %s; skipping creation.", ext_id, store.org_id)
            return existing

        # Create Order
        order = Order(
            id=uuid4(),
            org_id=store.org_id,
            external_order_id=ext_id,
            order_date=norm["order_date"],
            currency=norm["currency"],
            order_value=norm["order_value"],
            payment_method=norm["payment_method"],
            status="PENDING",
            fulfillment_status="UNFULFILLED",
            customer_name=norm["customer_name"],
            customer_phone=norm["customer_phone"],
            customer_email=norm["customer_email"],
            shipping_address1=norm["shipping_address1"],
            shipping_address2=norm["shipping_address2"],
            shipping_city=norm["shipping_city"],
            shipping_state=norm["shipping_state"],
            shipping_pincode=norm["shipping_pincode"],
            shipping_country=norm["shipping_country"],
            source_channel="SHOPIFY",
        )
        session.add(order)
        session.flush()

        # Add line items
        for it_data in norm["items"]:
            it = OrderItem(
                id=uuid4(),
                org_id=store.org_id,
                order_id=order.id,
                sku=it_data["sku"],
                product_name=it_data["product_name"],
                quantity=it_data["quantity"],
                unit_price=it_data["price"],
                total_price=it_data["price"] * it_data["quantity"],
            )
            session.add(it)
        session.flush()

        # Ensure Merchant Economics exists
        econ = session.scalar(
            select(MerchantEconomics).where(MerchantEconomics.org_id == store.org_id)
        )
        if not econ:
            econ = MerchantEconomics(org_id=store.org_id)
            session.add(econ)
            session.flush()

        # Evaluate order using DecisionEngineService (runs deterministic rules + shadow ML)
        DecisionEngineService.evaluate_order(
            order=order,
            economics=econ,
            session=session,
            evaluated_by_user_id=None,
        )

        logger.info("Created and evaluated Shopify order %s (ID: %s) for org %s.", ext_id, order.id, store.org_id)
        return order

    @classmethod
    def _process_order_updated(
        cls,
        store: ShopifyStore,
        payload: Dict[str, Any],
        session: Session,
    ) -> Optional[Order]:
        """Processes orders/updated, protecting against stale events and terminal state mutation."""
        ext_id = str(payload.get("id", ""))
        order = session.scalar(
            select(Order).where(Order.org_id == store.org_id, Order.external_order_id == ext_id)
        )
        if not order:
            logger.info("Order %s not found on orders/updated; ignoring.", ext_id)
            return None

        # Guard: Terminal state cannot be regressed by update event
        if order.status in ("DELIVERED", "RTO", "CANCELLED"):
            logger.info("Order %s is in terminal state '%s'; ignoring orders/updated mutation.", ext_id, order.status)
            return order

        # Guard: Stale timestamp check
        updated_at_str = payload.get("updated_at")
        if updated_at_str:
            try:
                event_time = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if ShopifyAdapter.is_stale_event(order.updated_at, event_time):
                    logger.info("Incoming orders/updated for order %s is older than current record; skipping.", ext_id)
                    return order
            except Exception:
                pass

        # Update contact and shipping details if order is still PENDING or CONFIRMED
        norm = ShopifyAdapter.extract_normalized_order(payload)
        if norm["customer_name"]:
            order.customer_name = norm["customer_name"]
        if norm["customer_phone"]:
            order.customer_phone = norm["customer_phone"]
        if norm["customer_email"]:
            order.customer_email = norm["customer_email"]
        if norm["shipping_address1"]:
            order.shipping_address1 = norm["shipping_address1"]
        if norm["shipping_city"]:
            order.shipping_city = norm["shipping_city"]
        if norm["shipping_pincode"]:
            order.shipping_pincode = norm["shipping_pincode"]

        session.flush()
        return order

    @classmethod
    def _process_order_cancelled(
        cls,
        store: ShopifyStore,
        payload: Dict[str, Any],
        session: Session,
    ) -> Optional[Order]:
        """Processes orders/cancelled, moving order to CANCELLED and triggering outcome recording."""
        ext_id = str(payload.get("id", ""))
        order = session.scalar(
            select(Order).where(Order.org_id == store.org_id, Order.external_order_id == ext_id)
        )
        if not order:
            return None

        # Guard: Terminal states DELIVERED or RTO cannot be cancelled retroactively
        if order.status in ("DELIVERED", "RTO"):
            logger.warning("Order %s has already reached delivery terminal state '%s'; cannot cancel.", ext_id, order.status)
            return order

        if order.status == "CANCELLED":
            return order

        # Transition order to CANCELLED
        DeliveryService.record_delivery_event(
            org_id=store.org_id,
            order_id=order.id,
            event_in=DeliveryEventCreate(
                order_id=order.id,
                event_type="CANCELLED",
                event_source="COURIER_WEBHOOK",
                reason_description=payload.get("cancel_reason", "Cancelled by merchant via Shopify"),
            ),
            session=session,
            actor_user_id=None,
        )
        return order

    @classmethod
    def _process_order_fulfilled(
        cls,
        store: ShopifyStore,
        payload: Dict[str, Any],
        session: Session,
    ) -> Optional[Order]:
        """Processes fulfillments, updating carrier and tracking information and transitioning to SHIPPED."""
        ext_id = str(payload.get("id", ""))
        order = session.scalar(
            select(Order).where(Order.org_id == store.org_id, Order.external_order_id == ext_id)
        )
        if not order:
            return None

        fulfillments = payload.get("fulfillments") or []
        carrier = None
        tracking_num = None
        if fulfillments:
            first_f = fulfillments[0]
            carrier = first_f.get("tracking_company")
            tracking_num = first_f.get("tracking_number") or (first_f.get("tracking_numbers") or [None])[0]

        # Valid lifecycle progression: PENDING -> CONFIRMED -> READY_TO_SHIP -> SHIPPED
        steps = []
        if order.status == "PENDING":
            steps = ["CONFIRMED", "READY_TO_SHIP", "SHIPPED"]
        elif order.status == "CONFIRMED":
            steps = ["READY_TO_SHIP", "SHIPPED"]
        elif order.status == "READY_TO_SHIP":
            steps = ["SHIPPED"]

        for ev_type in steps:
            DeliveryService.record_delivery_event(
                org_id=store.org_id,
                order_id=order.id,
                event_in=DeliveryEventCreate(
                    order_id=order.id,
                    event_type=ev_type,
                    carrier_name=carrier,
                    tracking_number=tracking_num,
                    event_source="COURIER_WEBHOOK",
                ),
                session=session,
                actor_user_id=None,
            )

        order.fulfillment_status = "FULFILLED"
        session.flush()
        return order
