"""OrderItem SQLAlchemy Model.

Enforces:
- Organization/tenant scoping.
- Associated order linkage with cascade deletion.
- Positive quantity and non-negative unit price / cost.
- Validated line item total calculation in Decimal.
"""

import uuid
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import GUID, TimestampMixin


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    external_product_id = Column(String(255), nullable=True)
    sku = Column(String(100), nullable=True, index=True)
    product_name = Column(String(255), nullable=False)

    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=True)
    total_price = Column(Numeric(12, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    organization = relationship("Organization")

    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_order_item_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_item_unit_price_non_negative"),
        CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="ck_order_item_unit_cost_non_negative"),
        CheckConstraint("total_price >= 0", name="ck_order_item_total_price_non_negative"),
        Index("idx_order_items_org_order", "org_id", "order_id"),
    )
