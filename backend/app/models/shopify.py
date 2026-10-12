"""Shopify Integration Database Models.

Enforces:
- Organization/tenant scoping for connected Shopify stores.
- Secure storage of encrypted API access tokens and webhook verification secrets.
- Idempotent tracking of Shopify webhook delivery attempts (X-Shopify-Delivery-Id).
- Audit trail for webhook lifecycle: RECEIVED, PROCESSED, DUPLICATE, FAILED, IGNORED.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.audit_log import JSONType
from app.models.base import GUID, TimestampMixin


class ShopifyStore(Base, TimestampMixin):
    """Represents a merchant's connected Shopify store."""
    __tablename__ = "shopify_stores"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # e.g., "merchant-store.myshopify.com"
    shop_domain = Column(String(255), unique=True, index=True, nullable=False)

    # AES-256-GCM encrypted access credentials
    access_token_encrypted = Column(Text, nullable=True)
    webhook_secret_encrypted = Column(Text, nullable=True)

    # Connection Status: not_configured | installed | active | suspended | uninstalled
    status = Column(String(50), nullable=False, default="not_configured")

    installed_at = Column(DateTime(timezone=True), nullable=True)
    uninstalled_at = Column(DateTime(timezone=True), nullable=True)

    # OAuth scopes granted by merchant
    scopes = Column(String(500), nullable=True, default="read_orders,write_orders")
    api_version = Column(String(20), nullable=False, default="2024-01")

    # Relationships
    organization = relationship("Organization", back_populates="shopify_store")
    deliveries = relationship("ShopifyWebhookDelivery", back_populates="store", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_shopify_stores_org_status", "org_id", "status"),
    )


class ShopifyWebhookDelivery(Base, TimestampMixin):
    """Tracks incoming webhook deliveries from Shopify for deduplication and audit."""
    __tablename__ = "shopify_webhook_deliveries"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    shopify_store_id = Column(GUID(), ForeignKey("shopify_stores.id", ondelete="SET NULL"), nullable=True, index=True)

    # Unique Delivery UUID sent in X-Shopify-Delivery-Id header
    shopify_delivery_id = Column(String(100), unique=True, index=True, nullable=False)

    # Webhook topic: orders/create, orders/updated, orders/cancelled, orders/fulfilled
    topic = Column(String(100), nullable=False, index=True)
    shop_domain = Column(String(255), nullable=False, index=True)

    # External Shopify Order ID if present in payload
    shopify_order_id = Column(String(100), nullable=True, index=True)

    # Normalized internal order reference once created/matched
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)

    # Delivery Processing Status: RECEIVED | PROCESSED | DUPLICATE | FAILED | IGNORED
    status = Column(String(50), nullable=False, default="RECEIVED")

    error_message = Column(Text, nullable=True)
    payload_summary = Column(JSONType, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    store = relationship("ShopifyStore", back_populates="deliveries")
    order = relationship("Order")
    organization = relationship("Organization")

    __table_args__ = (
        Index("idx_shopify_deliveries_org_topic", "org_id", "topic"),
        Index("idx_shopify_deliveries_org_status", "org_id", "status"),
    )
