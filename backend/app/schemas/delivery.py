"""Pydantic v2 Schemas for Delivery Lifecycle, Tracking Events, and NDR Recovery."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class DeliveryEventCreate(BaseModel):
    order_id: UUID
    event_id: Optional[str] = Field(default=None, description="Idempotency key from courier")
    event_type: str = Field(description="CONFIRMED, READY_TO_SHIP, SHIPPED, OUT_FOR_DELIVERY, DELIVERY_ATTEMPT_FAILED, DELIVERED, RTO_INITIATED, RTO_DELIVERED, CANCELLED")
    event_source: Optional[str] = Field(default="MANUAL_OPERATOR")
    is_simulated: Optional[bool] = Field(default=False)
    carrier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier_status_code: Optional[str] = None
    reason_code: Optional[str] = None
    reason_description: Optional[str] = None
    location: Optional[str] = None
    occurred_at: Optional[datetime] = None
    raw_payload: Optional[Dict[str, Any]] = None


class DeliveryEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    order_id: UUID
    event_id: str
    event_type: str
    previous_status: Optional[str] = None
    new_status: str
    event_source: str
    is_simulated: bool
    carrier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier_status_code: Optional[str] = None
    reason_code: Optional[str] = None
    reason_description: Optional[str] = None
    location: Optional[str] = None
    occurred_at: datetime
    created_at: datetime


class SimulateDeliveryRequest(BaseModel):
    order_id: UUID
    event_id: Optional[str] = Field(default=None, description="Optional custom event idempotency key")
    event_type: str = Field(description="OUT_FOR_DELIVERY, DELIVERY_ATTEMPT_FAILED, DELIVERED, RTO_INITIATED, RTO_DELIVERED, CANCELLED")
    reason_code: Optional[str] = Field(default="CUSTOMER_UNAVAILABLE", description="CUSTOMER_UNAVAILABLE, INCORRECT_ADDRESS, etc.")
    carrier_name: Optional[str] = Field(default="Delhivery (Simulated)")
    location: Optional[str] = Field(default="Bengaluru Delivery Hub")
    notes: Optional[str] = None


class NDRActionCreate(BaseModel):
    action_type: str = Field(description="CONTACT_CUSTOMER, VERIFY_ADDRESS, SCHEDULE_REATTEMPT, ESCALATE_TO_MANUAL_REVIEW, REQUEST_RTO, CLOSE_CASE")
    contact_method: Optional[str] = Field(default=None, description="WHATSAPP, SMS, CALL, EMAIL")
    customer_response: Optional[str] = None
    updated_address1: Optional[str] = None
    updated_address2: Optional[str] = None
    updated_city: Optional[str] = None
    updated_state: Optional[str] = None
    updated_pincode: Optional[str] = None
    updated_phone: Optional[str] = None
    reattempt_date: Optional[datetime] = None
    closure_reason: Optional[str] = None
    notes: Optional[str] = None


class NDRActionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ndr_case_id: UUID
    order_id: UUID
    actor_user_id: Optional[UUID] = None
    action_type: str
    action_details: Dict[str, Any]
    intervention_cost: Decimal
    notes: Optional[str] = None
    created_at: datetime


class NDRCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    order_id: UUID
    case_number: str
    status: str
    priority: str
    attempt_count: int
    last_attempt_date: datetime
    reason_code: str
    carrier_reason_raw: Optional[str] = None
    assigned_operator_id: Optional[UUID] = None
    assigned_operator_name: Optional[str] = None
    customer_contacted: bool
    contact_method: Optional[str] = None
    customer_response: Optional[str] = None
    updated_address1: Optional[str] = None
    updated_address2: Optional[str] = None
    updated_city: Optional[str] = None
    updated_state: Optional[str] = None
    updated_pincode: Optional[str] = None
    updated_phone: Optional[str] = None
    reattempt_date: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due: Optional[datetime] = None
    is_simulated: bool
    expected_recovery_lift: Optional[Decimal] = None
    estimated_recovery_ec: Optional[Decimal] = None
    recommended_recovery_action: Optional[str] = None
    recommendation_rationale: Optional[str] = None
    closed_at: Optional[datetime] = None
    closure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Enriched order fields
    order_external_id: Optional[str] = None
    order_value: Optional[Decimal] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_pincode: Optional[str] = None
    payment_method: Optional[str] = None
    actions: List[NDRActionLogOut] = []


class NDRListOut(BaseModel):
    cases: List[NDRCaseOut]
    total: int
    limit: int
    offset: int


class NDRRecommendationOut(BaseModel):
    ndr_case_id: UUID
    order_id: UUID
    recommended_action: str
    expected_recovery_lift: Decimal
    estimated_recovery_ec: Decimal
    baseline_rto_loss: Decimal
    profit_at_risk: Decimal
    estimated_rescue_prob: Decimal
    intervention_cost: Decimal
    rationale: str
    data_sufficiency: str
    accounting_notes: str


class CourierWebhookPayload(BaseModel):
    carrier: str
    tracking_number: str
    external_order_id: Optional[str] = None
    status: str
    sub_status: Optional[str] = None
    reason_code: Optional[str] = None
    reason_description: Optional[str] = None
    location: Optional[str] = None
    timestamp: Optional[datetime] = None
    event_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
