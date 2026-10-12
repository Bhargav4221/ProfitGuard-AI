"""Audit Logging Service with Concurrency-Safe Deterministic Hash Chaining."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.audit_log import (
    AuditLog,
    canonicalize_payload,
    compute_audit_hash,
    format_audit_timestamp,
)


class AuditService:
    @staticmethod
    def record_event(
        session: Session,
        org_id: UUID,
        action: str,
        resource_type: str,
        actor_user_id: Optional[UUID] = None,
        resource_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """Records an audit event with concurrency-safe deterministic hash chaining."""
        bind = session.get_bind()
        is_postgres = bind.dialect.name == "postgresql"

        # 1. Acquire transaction-level advisory lock per tenant
        if is_postgres:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('audit_lock_' || :org_id))"),
                {"org_id": str(org_id)}
            )

        # 2. Fetch the latest audit record for this tenant
        query = (
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.sequence_number.desc())
            .limit(1)
        )
        if is_postgres:
            query = query.with_for_update()

        last_record = session.scalar(query)

        # 3. Calculate sequence number and previous hash
        if last_record:
            sequence_number = last_record.sequence_number + 1
            previous_hash = last_record.current_hash
        else:
            sequence_number = 1
            previous_hash = "0" * 64  # Genesis block hash for tenant

        # 4. Canonicalize payload and compute hash
        now = datetime.now(timezone.utc).replace(microsecond=0)
        timestamp_str = format_audit_timestamp(now)
        canonical_str = canonicalize_payload(payload or {})

        current_hash = compute_audit_hash(
            previous_hash=previous_hash,
            org_id=str(org_id),
            sequence_number=sequence_number,
            actor_user_id=str(actor_user_id) if actor_user_id else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            canonical_payload=canonical_str,
            timestamp_str=timestamp_str,
        )

        # 5. Create and persist audit record
        audit_entry = AuditLog(
            org_id=org_id,
            sequence_number=sequence_number,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload or {},
            previous_hash=previous_hash,
            current_hash=current_hash,
            created_at=now,
        )
        session.add(audit_entry)
        session.flush()
        return audit_entry

    @staticmethod
    def verify_chain(session: Session, org_id: UUID) -> Tuple[bool, Optional[int], str]:
        """Validates the complete cryptographic hash chain for an organization."""
        records = session.scalars(
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.sequence_number.asc())
        ).all()

        if not records:
            return True, None, "No audit records found for organization."

        expected_prev_hash = "0" * 64
        for idx, rec in enumerate(records, start=1):
            if rec.sequence_number != idx:
                return False, rec.sequence_number, f"Sequence gap detected: expected {idx}, found {rec.sequence_number}."

            if rec.previous_hash != expected_prev_hash:
                return False, rec.sequence_number, f"Broken link: row {rec.sequence_number} previous_hash does not match preceding current_hash."

            canonical_str = canonicalize_payload(rec.payload)
            timestamp_str = format_audit_timestamp(rec.created_at)

            expected_current_hash = compute_audit_hash(
                previous_hash=rec.previous_hash,
                org_id=str(rec.org_id),
                sequence_number=rec.sequence_number,
                actor_user_id=str(rec.actor_user_id) if rec.actor_user_id else None,
                action=rec.action,
                resource_type=rec.resource_type,
                resource_id=rec.resource_id,
                canonical_payload=canonical_str,
                timestamp_str=timestamp_str,
            )

            if rec.current_hash != expected_current_hash:
                return False, rec.sequence_number, f"Tampered entry: hash mismatch on sequence {rec.sequence_number}."

            expected_prev_hash = rec.current_hash

        return True, None, f"Hash chain verified successfully ({len(records)} records intact)."
