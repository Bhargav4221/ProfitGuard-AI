"""Pydantic Schemas for Orders and Line Items.

Validation Rules:
- Monetary amounts must be Decimal (never float).
- quantity >= 1, unit_price >= 0, order_value > 0.
- Indian mobile validation (10 digits starting with 6-9) when supplied.
- Indian pincode validation (6 digits starting with 1-9) when supplied.
- Immutable fields (order_value, org_id, external_order_id) cannot be modified via update.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_indian_phone(phone: Optional[str]) -> Optional[str]:
    """Normalizes and validates 10-digit Indian mobile numbers."""
    if not phone:
        return None
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", str(phone).strip())
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]

    if not re.match(r"^[6-9]\d{9}$", cleaned):
        raise ValueError(f"Invalid Indian mobile number '{phone}'. Expected 10 digits starting with 6-9.")
    return cleaned


def normalize_indian_pincode(pincode: Optional[str]) -> Optional[str]:
    """Validates 6-digit Indian postal codes."""
    if not pincode:
        return None
    cleaned = re.sub(r"\s+", "", str(pincode).strip())
    if not re.match(r"^[1-9][0-9]{5}$", cleaned):
        raise ValueError(f"Invalid Indian postal pincode '{pincode}'. Expected 6 digits starting with 1-9.")
    return cleaned


class OrderItemCreate(BaseModel):
    sku: Optional[str] = None
    external_product_id: Optional[str] = None
    product_name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(..., ge=0)
    unit_cost: Optional[Decimal] = Field(default=None, ge=0)

    @field_validator("unit_price", "unit_cost", mode="before")
    @classmethod
    def parse_decimal(cls, v):
        if v is None:
            return None
        return Decimal(str(v).strip())


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    sku: Optional[str]
    external_product_id: Optional[str]
    product_name: str
    quantity: int
    unit_price: Decimal
    unit_cost: Optional[Decimal]
    total_price: Decimal
    created_at: datetime


class OrderCreate(BaseModel):
    external_order_id: str = Field(..., min_length=1, max_length=255)
    order_date: Optional[datetime] = None
    currency: str = Field(default="INR", max_length=3)
    order_value: Decimal = Field(..., gt=0)
    payment_method: str = Field(..., description="'COD' or 'PREPAID'")

    status: str = Field(default="PENDING", max_length=50)
    fulfillment_status: str = Field(default="UNFULFILLED", max_length=50)

    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None

    shipping_address1: Optional[str] = None
    shipping_address2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_pincode: Optional[str] = None
    shipping_country: str = "IN"

    courier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    source_channel: str = Field(default="MANUAL", max_length=100)

    items: List[OrderItemCreate] = Field(default_factory=list)

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in {"COD", "PREPAID"}:
            raise ValueError(f"Invalid payment_method '{v}'. Allowed values are 'COD' or 'PREPAID'.")
        return clean

    @field_validator("customer_phone")
    @classmethod
    def validate_phone(cls, v):
        return normalize_indian_phone(v)

    @field_validator("shipping_pincode")
    @classmethod
    def validate_pincode(cls, v):
        return normalize_indian_pincode(v)

    @field_validator("order_value", mode="before")
    @classmethod
    def parse_order_value(cls, v):
        try:
            val = Decimal(str(v).strip())
            if not val.is_finite() or val <= 0:
                raise ValueError("order_value must be a finite positive number.")
            return val
        except Exception as e:
            raise ValueError(f"Invalid order_value: {e}")


class OrderUpdate(BaseModel):
    """Permitted fields for order updates.
    
    IMMUTABLE: order_value, id, org_id, external_order_id are excluded by design.
    """
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None

    shipping_address1: Optional[str] = None
    shipping_address2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_pincode: Optional[str] = None

    courier_name: Optional[str] = None
    tracking_number: Optional[str] = None

    status: Optional[str] = None
    fulfillment_status: Optional[str] = None

    @field_validator("customer_phone")
    @classmethod
    def validate_phone(cls, v):
        return normalize_indian_phone(v)

    @field_validator("shipping_pincode")
    @classmethod
    def validate_pincode(cls, v):
        return normalize_indian_pincode(v)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    external_order_id: str
    order_date: datetime
    currency: str
    order_value: Decimal
    payment_method: str
    status: str
    fulfillment_status: str

    customer_name: Optional[str]
    customer_phone: Optional[str]
    customer_email: Optional[str]

    shipping_address1: Optional[str]
    shipping_address2: Optional[str]
    shipping_city: Optional[str]
    shipping_state: Optional[str]
    shipping_pincode: Optional[str]
    shipping_country: str

    courier_name: Optional[str]
    tracking_number: Optional[str]
    source_channel: str
    import_job_id: Optional[UUID]

    created_at: datetime
    updated_at: datetime

    items: List[OrderItemOut] = Field(default_factory=list)


class OrderListOut(BaseModel):
    orders: List[OrderOut]
    total: int
    limit: int
    offset: int


class DashboardSummaryOut(BaseModel):
    total_orders: int
    total_gmv: Decimal
    expected_contribution: Decimal
    realized_contribution: Decimal
    high_risk_count: int
    active_ndr_count: int
    status_breakdown: dict
    payment_method_breakdown: dict

