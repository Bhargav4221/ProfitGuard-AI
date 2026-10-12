"""Merchant Economics Database Model."""

import uuid
from sqlalchemy import Column, Numeric, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import GUID, TimestampMixin


class MerchantEconomics(Base, TimestampMixin):
    __tablename__ = "merchant_economics"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    # Unit Cost Structure (₹)
    default_cogs_percent = Column(Numeric(5, 2), default=30.00, nullable=False)
    forward_shipping_cost = Column(Numeric(10, 2), default=70.00, nullable=False)
    reverse_shipping_cost = Column(Numeric(10, 2), default=65.00, nullable=False)
    packaging_cost = Column(Numeric(10, 2), default=20.00, nullable=False)
    cod_carrier_fee = Column(Numeric(10, 2), default=35.00, nullable=False)

    # Carrier Contract Policies
    # Options: UPON_DELIVERY_ONLY (default) | UPON_MANIFEST
    cod_fee_incurred_on = Column(String(50), default="UPON_DELIVERY_ONLY", nullable=False)

    # Payment Gateway Fees (for prepaid)
    payment_gateway_percent = Column(Numeric(5, 2), default=2.00, nullable=False)
    payment_gateway_flat = Column(Numeric(10, 2), default=3.00, nullable=False)

    # Inventory Damage Rate on RTO (0.05 = 5%)
    inventory_damage_rate = Column(Numeric(5, 4), default=0.0500, nullable=False)

    # Pre-Dispatch Intervention Costs
    otp_verification_cost = Column(Numeric(10, 2), default=0.50, nullable=False)
    manual_review_cost = Column(Numeric(10, 2), default=18.00, nullable=False)
    prepaid_incentive_discount = Column(Numeric(10, 2), default=50.00, nullable=False)
    prepaid_comms_cost = Column(Numeric(10, 2), default=0.50, nullable=False)

    # Tax & Accounting Modes
    # Options: TAX_EXCLUSIVE_NET (default) | TAX_INCLUSIVE_CASH_FLOW
    tax_accounting_mode = Column(String(50), default="TAX_EXCLUSIVE_NET", nullable=False)

    # Operational Policy Flags
    allow_auto_cancel = Column(Boolean, default=False, nullable=False)
    enable_holdout_experiment = Column(Boolean, default=False, nullable=False)
    holdout_percentage = Column(Numeric(5, 2), default=5.00, nullable=False)
    safety_value_cap = Column(Numeric(10, 2), default=3500.00, nullable=False)

    organization = relationship("Organization", back_populates="economics")
