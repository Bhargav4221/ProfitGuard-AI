"""Order Evaluation and Decision SQLAlchemy Model.

Tracks:
- Pre-dispatch order risk assessment and uncertainty indicators.
- 5-Action candidate comparisons (SHIP_AS_IS, VERIFY_OTP, INCENTIVIZE_PREPAID, MANUAL_REVIEW, HOLD_CANCEL).
- Expected contribution (EC) in ₹ and lift vs SHIP_AS_IS.
- Transparent explanations, triggered rules, and policy guards.
- Merchant decision lifecycle (RECOMMENDED, ACCEPTED, OVERRIDDEN, EXECUTED).
- Pre-dispatch intervention outcomes (OTP verified/expired, prepaid conversion, manual review).
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
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.audit_log import JSONType
from app.models.base import GUID, TimestampMixin


class OrderEvaluation(Base, TimestampMixin):
    __tablename__ = "order_evaluations"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    evaluated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    evaluated_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Core Action Recommendation
    # Actions: SHIP_AS_IS | VERIFY_OTP | INCENTIVIZE_PREPAID | MANUAL_REVIEW | HOLD_CANCEL
    recommended_action = Column(String(50), nullable=False)
    recommended_action_deterministic = Column(String(50), nullable=True)
    recommended_action_ml_assisted = Column(String(50), nullable=True)
    decision_policy_version = Column(String(50), nullable=True)
    ml_operating_mode = Column(String(50), nullable=True)  # SHADOW | LIVE_ASSISTED | DISABLED
    ml_decision_rationale = Column(Text, nullable=True)
    recommended_lift = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    ship_as_is_ec = Column(Numeric(12, 2), nullable=False)
    best_ec = Column(Numeric(12, 2), nullable=False)
    profit_at_risk = Column(Numeric(12, 2), nullable=False)

    # Statistical Risk & Uncertainty Metrics
    baseline_p_rto = Column(Numeric(5, 4), nullable=False)
    uncertainty_score = Column(Numeric(5, 4), nullable=False)
    risk_tier = Column(String(20), nullable=False)  # LOW | MEDIUM | HIGH | CRITICAL

    # Detailed Comparison and Explanation Data
    comparison_data = Column(JSONType, nullable=False, default=list)
    explanation_data = Column(JSONType, nullable=False, default=dict)

    # Merchant Decision Lifecycle
    # Status: EVALUATED | ACCEPTED | OVERRIDDEN | EXECUTED | CANCELLED
    decision_status = Column(String(50), nullable=False, default="EVALUATED")
    selected_action = Column(String(50), nullable=True)
    override_reason = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Pre-Dispatch Intervention Outcome
    # Status: NONE | PENDING | OTP_VERIFIED | OTP_FAILED | PREPAID_CONVERTED | PREPAID_DECLINED | MANUAL_APPROVED | MANUAL_REJECTED
    intervention_status = Column(String(50), nullable=False, default="NONE")
    intervention_notes = Column(Text, nullable=True)
    intervention_resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    order = relationship("Order", back_populates="evaluations")
    organization = relationship("Organization")
    evaluated_by = relationship("User", foreign_keys=[evaluated_by_user_id])
    decided_by = relationship("User", foreign_keys=[decided_by_user_id])

    __table_args__ = (
        Index("idx_order_eval_org_created", "org_id", "created_at"),
        Index("idx_order_eval_org_order", "org_id", "order_id"),
        Index("idx_order_eval_org_status", "org_id", "decision_status"),
    )
