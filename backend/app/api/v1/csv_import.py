"""CSV Import API Endpoints.

Provides:
- GET  /csv-import/template          (Download sample CSV template)
- POST /csv-import/preview           (Stage A: Upload & Validate CSV, stages valid rows)
- POST /csv-import/commit            (Stage B: Transactionally insert staged orders)
- GET  /csv-import/history           (List import jobs with pagination)
- GET  /csv-import/history/{id}      (Get import job details & errors)
"""

from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_tenant_context, require_role
from app.core.tenant import OrganizationRole, TenantContext
from app.models.import_job import ImportJob
from app.schemas.csv_import import (
    CSVCommitRequest,
    CSVCommitResponse,
    CSVPreviewResponse,
    ImportJobListOut,
    ImportJobOut,
)
from app.services.csv_service import CSVService

router = APIRouter(prefix="/csv-import", tags=["CSV Import"])

OPERATOR_ROLES = {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.OPERATOR}


@router.get("/template")
def download_template():
    """Downloads standard RFC 4180 CSV template for merchant order ingestion."""
    csv_content = CSVService.get_template()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="profitguard_order_import_template.csv"'
        },
    )


@router.post("/preview", response_model=CSVPreviewResponse)
async def preview_csv(
    file: UploadFile = File(...),
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))] = None,
    session: Annotated[Session, Depends(get_db)] = None,
):
    """Stage A — Ingests and validates CSV. Stages valid rows without committing to orders."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a .csv extension.",
        )

    file_bytes = await file.read()
    return CSVService.preview_csv(
        file_bytes=file_bytes,
        filename=file.filename,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        session=session,
    )


@router.post("/commit", response_model=CSVCommitResponse)
def commit_csv(
    commit_req: CSVCommitRequest,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Stage B — Commits staged orders transactionally and idempotently into database."""
    inserted, skipped = CSVService.commit_import(
        preview_id=commit_req.preview_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        session=session,
    )

    import_job = session.get(ImportJob, commit_req.preview_id)
    return CSVCommitResponse(
        import_id=import_job.id,
        filename=import_job.filename,
        status=import_job.status,
        inserted_count=inserted,
        skipped_count=skipped,
        total_rows=import_job.total_rows,
    )


@router.get("/history", response_model=ImportJobListOut)
def list_import_history(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Retrieves import job history for current tenant."""
    query = select(ImportJob).where(ImportJob.org_id == tenant.org_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0

    query = query.order_by(ImportJob.created_at.desc()).limit(limit).offset(offset)
    jobs = list(session.scalars(query).all())

    return ImportJobListOut(jobs=jobs, total=total, limit=limit, offset=offset)


@router.get("/history/{import_id}", response_model=ImportJobOut)
def get_import_job(
    import_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves detailed status and errors for a specific import job."""
    job = session.scalar(
        select(ImportJob).where(
            ImportJob.id == import_id,
            ImportJob.org_id == tenant.org_id,
        )
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found or unauthorized.",
        )
    return job
