"""Order SQLAlchemy Model.

Enforces:
- Organization/tenant scoping with index and foreign key.
- Immutable original order value (never mutated on RTO, refund, or discount).
- Tenant-scoped uniqueness on (org_id, external_order_id).
- Indian address, phone, pincode, and payment method fields.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
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
from app.models.base import GUID, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Merchant's external identifier (e.g., Shopify order ID #1001)
    external_order_id = Column(String(255), nullable=False, index=True)

    # Order placement timestamp from merchant system
    order_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    currency = Column(String(3), nullable=False, default="INR")

    # IMMUTABLE Original Order Value (GMV in ₹) agreed at checkout
    # Financial adjustments, refunds, and RTO losses are tracked in separate ledger models
    order_value = Column(Numeric(12, 2), nullable=False)

    # Payment Method: 'COD' or 'PREPAID'
    payment_method = Column(String(50), nullable=False)

    # Order Lifecycle Statuses
    # Status: PENDING | CONFIRMED | HOLD | CANCELLED | DELIVERED | RTO
    status = Column(String(50), nullable=False, default="PENDING")

    # Fulfillment Status: UNFULFILLED | FULFILLED | PARTIAL | HOLD
    fulfillment_status = Column(String(50), nullable=False, default="UNFULFILLED")

    # Customer Information
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True, index=True)
    customer_email = Column(String(255), nullable=True, index=True)

    # Delivery Address
    shipping_address1 = Column(Text, nullable=True)
    shipping_address2 = Column(Text, nullable=True)
    shipping_city = Column(String(100), nullable=True)
    shipping_state = Column(String(100), nullable=True)
    shipping_pincode = Column(String(20), nullable=True, index=True)
    shipping_country = Column(String(10), nullable=False, default="IN")

    # Logistics & Channel Details
    courier_name = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    source_channel = Column(String(100), nullable=False, default="MANUAL")

    # Optional reference to CSV Import Job
    import_job_id = Column(GUID(), ForeignKey("import_jobs.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    evaluations = relationship("OrderEvaluation", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    delivery_events = relationship("DeliveryEvent", back_populates="order", cascade="all, delete-orphan", lazy="selectin", order_by="DeliveryEvent.occurred_at.asc()")
    ndr_cases = relationship("NDRCase", back_populates="order", cascade="all, delete-orphan", lazy="selectin", order_by="NDRCase.created_at.desc()")
    reconciliation = relationship("OrderFinancialReconciliation", back_populates="order", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    outcome = relationship("OrderOutcome", back_populates="order", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    organization = relationship("Organization")
    import_job = relationship("ImportJob", back_populates="orders")

    __table_args__ = (
        UniqueConstraint("org_id", "external_order_id", name="uq_order_org_external_id"),
        Index("idx_orders_org_created", "org_id", "created_at"),
        Index("idx_orders_org_status", "org_id", "status"),
        Index("idx_orders_org_phone", "org_id", "customer_phone"),
    )
