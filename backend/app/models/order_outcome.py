"""Real-Order Outcome Tracking and Realized Financial Performance Model.

Tracks the full closed-loop outcome comparing order-time predictions/recommendations
with actual terminal delivery outcomes and realized financial results:
- Order and Tenant Scoping with UniqueConstraint on (org_id, order_id).
- Prediction-time audit: Model version, timestamp, feature reference snapshot, predicted P(RTO), risk tier.
- Policy audit: Deterministic recommendation, merchant approved action, pre-dispatch intervention status.
- Terminal delivery outcome: DELIVERED | RTO | CANCELLED, carrier, tracking number, delivered/RTO timestamps.
- Authoritative financial results: Realized revenue, COGS, logistics, damage, intervention costs, realized contribution (RC).
- Ex-ante vs ex-post variance: RC vs EC.
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
from app.models.audit_log import JSONType
from app.models.base import GUID, TimestampMixin


class OrderOutcome(Base, TimestampMixin):
    __tablename__ = "order_outcomes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    external_order_id = Column(String(255), nullable=False, index=True)

    # Optional references to evaluation and financial reconciliation
    evaluation_id = Column(GUID(), ForeignKey("order_evaluations.id", ondelete="SET NULL"), nullable=True, index=True)
    reconciliation_id = Column(GUID(), ForeignKey("financial_reconciliations.id", ondelete="SET NULL"), nullable=True, index=True)

    # 1. Prediction-Time Model State & Auditing
    model_version = Column(String(100), nullable=True, index=True)
    feature_contract_version = Column(String(50), nullable=True)
    prediction_timestamp = Column(DateTime(timezone=True), nullable=True)
    prediction_feature_ref = Column(String(255), nullable=True)
    prediction_features_snapshot = Column(JSONType, nullable=True)
    predicted_p_rto = Column(Numeric(5, 4), nullable=True)
    predicted_risk_tier = Column(String(20), nullable=True)  # LOW | MEDIUM | HIGH | CRITICAL

    # 2. Policy & Decision Tracking
    deterministic_recommendation = Column(String(50), nullable=False)  # SHIP_AS_IS | VERIFY_OTP | INCENTIVIZE_PREPAID | MANUAL_REVIEW | HOLD_CANCEL
    ml_assisted_recommendation = Column(String(50), nullable=True)     # Action recommended under ML-assisted policy
    final_recommendation = Column(String(50), nullable=True)           # Action actually presented to merchant
    ml_operating_mode = Column(String(50), nullable=True)              # SHADOW | LIVE_ASSISTED | DISABLED
    decision_policy_version = Column(String(50), nullable=True)        # Policy rule version applied
    merchant_approved_action = Column(String(50), nullable=True)       # Action selected/approved by merchant operator
    intervention_status = Column(String(50), nullable=False, default="NONE")  # NONE | PENDING | OTP_VERIFIED | OTP_FAILED | PREPAID_CONVERTED | PREPAID_DECLINED | MANUAL_APPROVED | MANUAL_REJECTED
    intervention_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    # 3. Terminal Delivery Outcome
    final_delivery_outcome = Column(String(50), nullable=False, index=True)  # DELIVERED | RTO | CANCELLED
    carrier_name = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    rto_reason_code = Column(String(100), nullable=True)
    rto_reason_description = Column(Text, nullable=True)

    # 4. Authoritative Realized Financial Metrics
    realized_order_value = Column(Numeric(12, 2), nullable=False)  # Gross Order GMV
    realized_collected_revenue = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    realized_cogs = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    realized_shipping_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))  # Forward + Reverse Shipping
    realized_damage_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    realized_rto_loss = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))        # S_f + S_r + Packaging + Damage if RTO
    realized_contribution = Column(Numeric(12, 2), nullable=False)                             # Realized Contribution (RC)
    expected_contribution = Column(Numeric(12, 2), nullable=True)                              # Ex-Ante Expected Contribution (EC)
    variance_ec_vs_rc = Column(Numeric(12, 2), nullable=True)                                  # RC - EC

    # 5. Outcome Recording Metadata
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    recorded_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="outcome", lazy="selectin")
    evaluation = relationship("OrderEvaluation", lazy="selectin")
    reconciliation = relationship("OrderFinancialReconciliation", lazy="selectin")
    organization = relationship("Organization")
    recorded_by = relationship("User", foreign_keys=[recorded_by_user_id])

    __table_args__ = (
        UniqueConstraint("org_id", "order_id", name="uq_order_outcomes_org_order"),
        Index("idx_order_outcomes_org_terminal", "org_id", "final_delivery_outcome"),
        Index("idx_order_outcomes_org_recorded", "org_id", "recorded_at"),
        Index("idx_order_outcomes_org_model", "org_id", "model_version"),
    )
