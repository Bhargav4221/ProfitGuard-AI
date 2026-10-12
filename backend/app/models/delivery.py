"""Delivery Lifecycle, Tracking Events, and NDR Recovery Models.

Enforces:
- Organization/tenant isolation with foreign keys and indices.
- Delivery lifecycle tracking with auditability and event idempotency.
- Permitted recovery actions (CONTACT_CUSTOMER, VERIFY_ADDRESS, SCHEDULE_REATTEMPT, ESCALATE, CLOSE).
- Explicit labeling of simulated vs live courier events (is_simulated flag).
- Decimal financial fields for intervention and recovery economics.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.audit_log import JSONType
from app.models.base import GUID, TimestampMixin


class DeliveryEvent(Base, TimestampMixin):
    """Immutable log of delivery lifecycle events from couriers, webhooks, or manual entry.
    
    Guarantees event idempotency via unique constraint on (org_id, event_id).
    """
    __tablename__ = "delivery_events"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    # Idempotency identifier provided by courier or generated (e.g. tracking# + status + timestamp)
    event_id = Column(String(255), nullable=False)

    # Event Type / Status:
    # ORDER_CONFIRMED, READY_TO_SHIP, SHIPPED, OUT_FOR_DELIVERY,
    # DELIVERY_ATTEMPT_FAILED (NDR), DELIVERED, RTO_INITIATED, RTO_DELIVERED, CANCELLED
    event_type = Column(String(50), nullable=False)
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)

    # Source: COURIER_WEBHOOK | COURIER_WEBHOOK_SIMULATED | MANUAL_OPERATOR | SYSTEM
    event_source = Column(String(50), nullable=False, default="SYSTEM")
    is_simulated = Column(Boolean, nullable=False, default=False)

    # Logistics specifics
    carrier_name = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    carrier_status_code = Column(String(50), nullable=True)
    reason_code = Column(String(100), nullable=True)
    reason_description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)

    occurred_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    raw_payload = Column(JSONType, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="delivery_events")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("org_id", "event_id", name="uq_delivery_events_org_event_id"),
        Index("idx_delivery_events_org_order", "org_id", "order_id"),
        Index("idx_delivery_events_org_occurred", "org_id", "occurred_at"),
    )


class NDRCase(Base, TimestampMixin):
    """Non-Delivery Report (NDR) Recovery Case for failed delivery attempts.
    
    Created when an order encounters a delivery failure.
    Tracks recovery actions, address amendments, reattempts, and resolution.
    """
    __tablename__ = "ndr_cases"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    case_number = Column(String(50), nullable=False)

    # Status: OPEN | IN_PROGRESS | REATTEMPT_SCHEDULED | RESOLVED_DELIVERED | RESOLVED_RTO | RESOLVED_CANCELLED | CLOSED
    status = Column(String(50), nullable=False, default="OPEN")

    # Priority: HIGH | MEDIUM | LOW
    priority = Column(String(20), nullable=False, default="MEDIUM")

    attempt_count = Column(Integer, nullable=False, default=1)
    last_attempt_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Reason: CUSTOMER_UNAVAILABLE | INCORRECT_ADDRESS | CUSTOMER_UNREACHABLE | DELIVERY_RESCHEDULE_REQUESTED | COD_AMOUNT_NOT_READY | CUSTOMER_REFUSED | OTHER
    reason_code = Column(String(100), nullable=False)
    carrier_reason_raw = Column(Text, nullable=True)

    # Operator Assignment
    assigned_operator_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_operator_name = Column(String(255), nullable=True)

    # Customer Outreach & Address Verification
    customer_contacted = Column(Boolean, nullable=False, default=False)
    contact_method = Column(String(50), nullable=True)  # WHATSAPP | SMS | CALL | EMAIL
    customer_response = Column(Text, nullable=True)

    updated_address1 = Column(Text, nullable=True)
    updated_address2 = Column(Text, nullable=True)
    updated_city = Column(String(100), nullable=True)
    updated_state = Column(String(100), nullable=True)
    updated_pincode = Column(String(20), nullable=True)
    updated_phone = Column(String(50), nullable=True)

    # Reattempt Tracking
    reattempt_date = Column(DateTime(timezone=True), nullable=True)
    next_action = Column(String(100), nullable=True)
    next_action_due = Column(DateTime(timezone=True), nullable=True)

    # Simulation Disclosures
    is_simulated = Column(Boolean, nullable=False, default=False)

    # Decision Support & Economic Estimates
    expected_recovery_lift = Column(Numeric(12, 2), nullable=True)
    estimated_recovery_ec = Column(Numeric(12, 2), nullable=True)
    recommended_recovery_action = Column(String(50), nullable=True)
    recommendation_rationale = Column(Text, nullable=True)

    # Closure
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closure_reason = Column(Text, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="ndr_cases")
    actions = relationship("NDRActionLog", back_populates="ndr_case", cascade="all, delete-orphan", lazy="selectin", order_by="NDRActionLog.created_at.desc()")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("org_id", "case_number", name="uq_ndr_cases_org_case_num"),
        Index("idx_ndr_cases_org_status", "org_id", "status"),
        Index("idx_ndr_cases_org_order", "org_id", "order_id"),
        Index("idx_ndr_cases_org_priority", "org_id", "priority"),
    )


class NDRActionLog(Base, TimestampMixin):
    """Audit log of individual recovery interventions on an NDR case."""
    __tablename__ = "ndr_action_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    ndr_case_id = Column(GUID(), ForeignKey("ndr_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    actor_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Action Type: CONTACT_CUSTOMER | VERIFY_ADDRESS | SCHEDULE_REATTEMPT | ESCALATE_TO_MANUAL_REVIEW | REQUEST_RTO | CLOSE_CASE
    action_type = Column(String(50), nullable=False)
    action_details = Column(JSONType, nullable=False, default=dict)
    intervention_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    notes = Column(Text, nullable=True)

    # Relationships
    ndr_case = relationship("NDRCase", back_populates="actions")
    order = relationship("Order")

    __table_args__ = (
        Index("idx_ndr_actions_org_case", "org_id", "ndr_case_id"),
        Index("idx_ndr_actions_org_created", "org_id", "created_at"),
    )
