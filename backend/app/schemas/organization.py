"""Organization and Membership Schemas."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.core.tenant import OrganizationRole


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    status: str
    created_at: datetime


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    user_id: UUID
    role: OrganizationRole
    created_at: datetime
    organization: OrganizationOut


class MemberInvite(BaseModel):
    email: str
    role: OrganizationRole = OrganizationRole.OPERATOR


class MemberRoleUpdate(BaseModel):
    role: OrganizationRole
