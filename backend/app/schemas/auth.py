"""Authentication Pydantic Schemas."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class UserRegister(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="Valid email address.")
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters long.")
    full_name: str | None = None
    organization_name: str = Field(..., min_length=2, max_length=100, description="Initial organization name.")


class UserLogin(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefresh(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime
