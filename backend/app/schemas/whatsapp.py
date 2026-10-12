"""Pydantic Schemas for Meta WhatsApp Business Cloud API Integration."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WhatsAppConfigIn(BaseModel):
    """Payload to configure or update WhatsApp Business Cloud API credentials."""
    phone_number_id: str = Field(..., description="Meta Phone Number ID from App Dashboard")
    business_account_id: Optional[str] = Field(default=None, description="WhatsApp Business Account (WABA) ID")
    access_token: Optional[str] = Field(default=None, description="Permanent System User Access Token")
    app_secret: Optional[str] = Field(default=None, description="Meta App Secret for HMAC-SHA256 signature verification")
    webhook_verify_token: Optional[str] = Field(default="profitguard_whatsapp_verify_token_default", description="Custom token for GET webhook verification")
    operating_mode: str = Field(default="MOCK", description="MOCK | META_TEST | LIVE")
    api_version: str = Field(default="v20.0", description="Meta Graph API version")

    @field_validator("operating_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in {"MOCK", "META_TEST", "LIVE"}:
            raise ValueError(f"Invalid operating mode '{v}'. Must be MOCK, META_TEST, or LIVE.")
        return clean


class WhatsAppConfigOut(BaseModel):
    """Sanitized public view of WhatsApp configuration without exposing raw tokens."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    phone_number_id: Optional[str] = None
    business_account_id: Optional[str] = None
    has_access_token: bool
    has_app_secret: bool
    webhook_verify_token: Optional[str] = None
    operating_mode: str
    status: str
    verified_name: Optional[str] = None
    quality_rating: Optional[str] = None
    api_version: str
    webhook_url: Optional[str] = None
    last_webhook_received_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WhatsAppTestConnectionOut(BaseModel):
    """Result of active connection diagnostic test."""
    connected: bool
    operating_mode: str
    phone_number_id: Optional[str] = None
    display_phone_number: Optional[str] = None
    verified_name: Optional[str] = None
    quality_rating: Optional[str] = None
    message: str


class WhatsAppSendTestIn(BaseModel):
    """Payload to send a test message to an authorized recipient."""
    recipient_phone: str = Field(..., description="Recipient phone in E.164 format (+919876543210)")
    message_text: Optional[str] = Field(default="ProfitGuard AI WhatsApp integration test message.", description="Text to send")


class WhatsAppSendOtpIn(BaseModel):
    """Payload to trigger pre-dispatch COD OTP / Confirmation message."""
    order_id: UUID
    recipient_phone: Optional[str] = Field(default=None, description="Optional override phone; defaults to order customer phone")


class WhatsAppSendNdrIn(BaseModel):
    """Payload to trigger delivery recovery / address confirmation message."""
    ndr_case_id: UUID
    recipient_phone: Optional[str] = Field(default=None, description="Optional override phone; defaults to NDR case phone")
    notes: Optional[str] = Field(default=None, description="Optional agent notes")


class WhatsAppMessageOut(BaseModel):
    """Single WhatsApp message log entry."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    order_id: Optional[UUID] = None
    ndr_case_id: Optional[UUID] = None
    wamid: Optional[str] = None
    direction: str
    recipient_phone: str
    sender_phone: Optional[str] = None
    message_type: str
    template_name: Optional[str] = None
    body_preview: Optional[str] = None
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    intervention_cost: Decimal
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class WhatsAppMessageListOut(BaseModel):
    """Paginated list of WhatsApp messages."""
    items: List[WhatsAppMessageOut]
    total: int
    page: int
    page_size: int


class WhatsAppOptOutOut(BaseModel):
    """Record of customer opt-out."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    phone_number: str
    opted_out_at: datetime
    reason: str
