"""Audit Trail and Cryptographic Verification API."""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_tenant_context
from app.core.tenant import TenantContext
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditChainVerificationOut, AuditLogOut
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("", response_model=List[AuditLogOut])
def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Fetches paginated audit trail records for the authenticated organization."""
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.org_id == tenant.org_id)
        .order_by(AuditLog.sequence_number.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return logs


@router.get("/verify", response_model=AuditChainVerificationOut)
def verify_audit_trail(
    tenant: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Verifies the complete SHA-256 cryptographic hash chain for this tenant.
    
    Detects any retroactively modified, deleted, or out-of-order records.
    """
    total_records = session.query(AuditLog).filter(AuditLog.org_id == tenant.org_id).count()
    is_valid, broken_seq, detail = AuditService.verify_chain(session, tenant.org_id)

    return AuditChainVerificationOut(
        org_id=tenant.org_id,
        total_records=total_records,
        is_valid=is_valid,
        broken_sequence_number=broken_seq,
        detail=detail,
    )
