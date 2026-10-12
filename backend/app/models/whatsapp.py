"""Meta WhatsApp Business Cloud API Database Models.

Enforces:
- Tenant isolation for WhatsApp credentials and message history.
- Encrypted storage for Meta access tokens and webhook app secrets using AES-256-GCM.
- Idempotent tracking of incoming delivery status and message webhooks.
- Explicit lifecycle tracking: QUEUED -> SENT -> DELIVERED -> READ / FAILED.
- Strict customer opt-out management (STOP / UNSUBSCRIBE).
- Audit trail for COD pre-dispatch verification and NDR recovery messaging.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.audit_log import JSONType
from app.models.base import GUID, TimestampMixin


class WhatsAppConfig(Base, TimestampMixin):
    """Represents an organization's Meta WhatsApp Business Cloud API configuration."""
    __tablename__ = "whatsapp_configs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Meta Graph API identifiers
    phone_number_id = Column(String(100), nullable=True, index=True)
    business_account_id = Column(String(100), nullable=True, index=True)

    # AES-256-GCM Encrypted credentials
    access_token_encrypted = Column(Text, nullable=True)
    app_secret_encrypted = Column(Text, nullable=True)

    # Webhook handshake verification token
    webhook_verify_token = Column(String(255), nullable=True, default="profitguard_whatsapp_verify_token_default")

    # Operating Mode: MOCK | META_TEST | LIVE
    operating_mode = Column(String(50), nullable=False, default="MOCK")

    # Status: NOT_CONFIGURED | ACTIVE | DISCONNECTED | ERROR
    status = Column(String(50), nullable=False, default="NOT_CONFIGURED")

    # Profile & Health metadata
    verified_name = Column(String(255), nullable=True)
    quality_rating = Column(String(50), nullable=True)  # GREEN, YELLOW, RED, UNKNOWN
    api_version = Column(String(20), nullable=False, default="v20.0")

    # Public callback URL generated or configured
    webhook_url = Column(String(500), nullable=True)
    last_webhook_received_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="whatsapp_config")
    messages = relationship("WhatsAppMessage", back_populates="config", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_whatsapp_configs_org_mode", "org_id", "operating_mode"),
        Index("idx_whatsapp_configs_phone_num_id", "phone_number_id"),
    )


class WhatsAppMessage(Base, TimestampMixin):
    """Tracks every outbound and inbound WhatsApp message, its delivery status receipts, and costs."""
    __tablename__ = "whatsapp_messages"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    whatsapp_config_id = Column(GUID(), ForeignKey("whatsapp_configs.id", ondelete="SET NULL"), nullable=True, index=True)

    # Workflow linkages
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    ndr_case_id = Column(GUID(), ForeignKey("ndr_cases.id", ondelete="SET NULL"), nullable=True, index=True)

    # Meta message ID: e.g. "wamid.HBgL..."
    wamid = Column(String(150), unique=True, index=True, nullable=True)

    # Direction: OUTBOUND | INBOUND
    direction = Column(String(20), nullable=False, default="OUTBOUND")

    # Phone numbers in E.164 format (+919876543210)
    recipient_phone = Column(String(30), nullable=False, index=True)
    sender_phone = Column(String(30), nullable=True)

    # Message Type: TEMPLATE | TEXT | INTERACTIVE | OTP
    message_type = Column(String(50), nullable=False, default="TEMPLATE")
    template_name = Column(String(100), nullable=True)

    # Preview or sanitized text body
    body_preview = Column(Text, nullable=True)

    # Status: QUEUED | SENT | DELIVERED | READ | FAILED
    status = Column(String(30), nullable=False, default="QUEUED", index=True)

    # Provider error information
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # Economic intervention cost in INR (deducted for financial reconciliation)
    intervention_cost = Column(Numeric(10, 2), nullable=False, default=0.00)

    # Delivery lifecycle timestamps from provider status callbacks
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Full raw payload (sanitized)
    raw_payload = Column(JSONType, nullable=True)

    # Relationships
    config = relationship("WhatsAppConfig", back_populates="messages")
    order = relationship("Order")
    ndr_case = relationship("NDRCase")
    organization = relationship("Organization")

    __table_args__ = (
        Index("idx_whatsapp_messages_org_status", "org_id", "status"),
        Index("idx_whatsapp_messages_org_order", "org_id", "order_id"),
        Index("idx_whatsapp_messages_org_phone", "org_id", "recipient_phone"),
    )


class WhatsAppOptOut(Base, TimestampMixin):
    """Maintains phone numbers that have opted out of WhatsApp automated messaging."""
    __tablename__ = "whatsapp_opt_outs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # E.164 formatted phone number
    phone_number = Column(String(30), nullable=False, index=True)
    opted_out_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    reason = Column(String(100), nullable=False, default="CUSTOMER_REQUEST")

    __table_args__ = (
        UniqueConstraint("org_id", "phone_number", name="uq_whatsapp_opt_outs_org_phone"),
        Index("idx_whatsapp_opt_outs_org_phone", "org_id", "phone_number"),
    )


class WhatsAppWebhookEvent(Base, TimestampMixin):
    """Tracks received webhook events to guarantee idempotent processing and avoid duplicates."""
    __tablename__ = "whatsapp_webhook_events"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)

    # Unique event key: wamid for messages, or wamid:status:timestamp for status receipts
    event_id = Column(String(150), unique=True, index=True, nullable=False)
    event_type = Column(String(50), nullable=False)  # STATUS_UPDATE | MESSAGE_RECEIVED

    status = Column(String(50), nullable=False, default="PROCESSED")  # PROCESSED | DUPLICATE | FAILED
    error_message = Column(Text, nullable=True)
    raw_payload = Column(JSONType, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_whatsapp_webhook_events_event_id", "event_id"),
    )
