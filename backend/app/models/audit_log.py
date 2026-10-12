"""Append-Only Tamper-Evident Audit Log Model with SHA-256 Hash Chaining."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, TEXT
from app.core.database import Base
from app.models.base import GUID


class JSONType(TypeDecorator):
    """Platform-independent JSON type (JSONB on PostgreSQL, TEXT on SQLite)."""
    impl = TEXT
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB)
        return dialect.type_descriptor(TEXT)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.dumps(
            value,
            sort_keys=True,
            default=lambda o: str(o) if isinstance(o, (Decimal, UUID, datetime)) else str(o),
        )

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, dict) or isinstance(value, list):
            return value
        return json.loads(value)


def canonicalize_payload(payload: Dict[str, Any] | None) -> str:
    """Canonicalizes JSON payloads with deterministic key ordering and compact formatting."""
    if not payload:
        return "{}"
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=lambda o: str(o) if isinstance(o, (Decimal, UUID, datetime)) else str(o),
    )


def format_audit_timestamp(dt: datetime | str) -> str:
    """Standardizes datetime to second-precision UTC ISO-8601 string across database drivers."""
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_audit_hash(
    previous_hash: str,
    org_id: str,
    sequence_number: int,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    canonical_payload: str,
    timestamp_str: str
) -> str:
    """Computes a deterministic SHA-256 digest over the audit entry fields."""
    hasher = hashlib.sha256()
    hasher.update(previous_hash.encode("utf-8"))
    hasher.update(b"|")
    hasher.update(org_id.encode("utf-8"))
    hasher.update(b"|")
    hasher.update(str(sequence_number).encode("utf-8"))
    hasher.update(b"|")
    hasher.update((actor_user_id or "system").encode("utf-8"))
    hasher.update(b"|")
    hasher.update(action.encode("utf-8"))
    hasher.update(b"|")
    hasher.update(resource_type.encode("utf-8"))
    hasher.update(b"|")
    hasher.update((resource_id or "").encode("utf-8"))
    hasher.update(b"|")
    hasher.update(canonical_payload.encode("utf-8"))
    hasher.update(b"|")
    hasher.update(timestamp_str.encode("utf-8"))
    return hasher.hexdigest()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_number = Column(BigInteger, nullable=False)
    actor_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255), nullable=True)
    payload = Column(JSONType, nullable=False, default=dict)

    # Hash Chaining
    previous_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc).replace(microsecond=0),
        nullable=False
    )

    organization = relationship("Organization", back_populates="audit_logs")
    actor = relationship("User")

    __table_args__ = (
        Index("idx_audit_org_seq", "org_id", "sequence_number", unique=True),
        Index("idx_audit_org_created", "org_id", "created_at"),
    )
