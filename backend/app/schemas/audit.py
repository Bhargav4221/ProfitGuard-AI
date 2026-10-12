"""Audit Log Schemas."""

from datetime import datetime
from typing import Any, Dict
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    sequence_number: int
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    payload: Dict[str, Any]
    previous_hash: str
    current_hash: str
    created_at: datetime


class AuditChainVerificationOut(BaseModel):
    org_id: UUID
    total_records: int
    is_valid: bool
    broken_sequence_number: int | None = None
    detail: str
