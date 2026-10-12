"""Revoked JWT Tokens Model for Session Invalidation."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String
from app.core.database import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti = Column(String(36), primary_key=True, index=True)
    revoked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
