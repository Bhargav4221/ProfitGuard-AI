"""Merchant Economics Schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MerchantEconomicsBase(BaseModel):
    default_cogs_percent: Decimal = Field(default=Decimal("30.00"), ge=0, le=100)
    forward_shipping_cost: Decimal = Field(default=Decimal("70.00"), ge=0)
    reverse_shipping_cost: Decimal = Field(default=Decimal("65.00"), ge=0)
    packaging_cost: Decimal = Field(default=Decimal("20.00"), ge=0)
    cod_carrier_fee: Decimal = Field(default=Decimal("35.00"), ge=0)
    cod_fee_incurred_on: str = Field(default="UPON_DELIVERY_ONLY")

    payment_gateway_percent: Decimal = Field(default=Decimal("2.00"), ge=0, le=100)
    payment_gateway_flat: Decimal = Field(default=Decimal("3.00"), ge=0)
    inventory_damage_rate: Decimal = Field(default=Decimal("0.0500"), ge=0, le=1)

    otp_verification_cost: Decimal = Field(default=Decimal("0.50"), ge=0)
    manual_review_cost: Decimal = Field(default=Decimal("18.00"), ge=0)
    prepaid_incentive_discount: Decimal = Field(default=Decimal("50.00"), ge=0)
    prepaid_comms_cost: Decimal = Field(default=Decimal("0.50"), ge=0)

    tax_accounting_mode: str = Field(default="TAX_EXCLUSIVE_NET")
    allow_auto_cancel: bool = False
    enable_holdout_experiment: bool = False
    holdout_percentage: Decimal = Field(default=Decimal("5.00"), ge=0, le=20)
    safety_value_cap: Decimal = Field(default=Decimal("3500.00"), ge=0)

    @field_validator("cod_fee_incurred_on")
    @classmethod
    def validate_cod_fee_policy(cls, v: str) -> str:
        clean = (v or "").strip().upper()
        # Explicit migration of known legacy aliases
        legacy_map = {
            "DELIVERY_ATTEMPT_1": "UPON_MANIFEST",
            "UPON_DISPATCH": "UPON_MANIFEST",
            "DELIVERED_ONLY": "UPON_DELIVERY_ONLY",
        }
        if clean in legacy_map:
            return legacy_map[clean]
        allowed = {"UPON_DELIVERY_ONLY", "UPON_MANIFEST"}
        if clean not in allowed:
            raise ValueError(
                f"Invalid cod_fee_incurred_on '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return clean


class MerchantEconomicsUpdate(MerchantEconomicsBase):
    pass


class MerchantEconomicsOut(MerchantEconomicsBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    created_at: datetime
    updated_at: datetime
