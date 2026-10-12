"""Authoritative Order Financial Reconciliation and Realized Contribution Model.

Tracks the exact ex-post financial ledger for finalized orders:
- Immutable Order Value (GMV) separated from Collected Revenue.
- Actual COGS, forward shipping, and avoided/incurred reverse shipping.
- Payment gateway / COD carrier fees based on verified events.
- Actual inventory impairment vs full recovery.
- Pre-dispatch and NDR intervention costs deducted exactly once.
- Realized Contribution (RC) compared against ex-ante Expected Contribution (EC).
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


class OrderFinancialReconciliation(Base, TimestampMixin):
    __tablename__ = "financial_reconciliations"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    external_order_id = Column(String(255), nullable=False)
    terminal_status = Column(String(50), nullable=False)  # DELIVERED | RTO | CANCELLED

    # 1. Gross Order Value (Checkout GMV - Immutable)
    order_value = Column(Numeric(12, 2), nullable=False)

    # 2. Collected Revenue (Actual Cash Inflow: 0 for RTO/Cancelled, Gross for COD Delivered)
    collected_revenue = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # 3. Direct Operational Expenses
    cogs = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    forward_shipping_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    reverse_shipping_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    payment_fee = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    packaging_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    inventory_damage_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    # 4. Intervention Expenses (Deducted exactly once)
    pre_dispatch_intervention_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    ndr_recovery_intervention_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    # 5. Authoritative Realized Contribution (RC in ₹)
    # RC = Collected Revenue - COGS - S_f - S_r - PaymentFee - Packaging - Damage - PreDispatchCost - NDRCost
    realized_contribution = Column(Numeric(12, 2), nullable=False)

    # 6. Ex-Ante Comparison
    expected_contribution = Column(Numeric(12, 2), nullable=True)
    variance_ec_vs_rc = Column(Numeric(12, 2), nullable=True)  # RC - EC

    reconciliation_status = Column(String(50), nullable=False, default="SETTLED")  # SETTLED | PROVISIONAL
    accounting_notes = Column(Text, nullable=True)
    reconciled_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    order = relationship("Order", back_populates="reconciliation")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("org_id", "order_id", name="uq_reconciliation_org_order"),
        Index("idx_reconciliation_org_status", "org_id", "terminal_status"),
        Index("idx_reconciliation_org_created", "org_id", "created_at"),
    )
