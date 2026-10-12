"""Demo Dataset & Complete Journey API Endpoints."""

from typing import Annotated, Any, Dict
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.tenant import OrganizationRole, TenantContext
from app.services.demo_service import DemoService

router = APIRouter(prefix="/demo", tags=["Demo & Journey Validation"])

OPERATOR_ROLES = {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.OPERATOR}


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_demo_data(
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
) -> Dict[str, Any]:
    """Populates repeatable, simulated demonstration orders and NDR cases."""
    return DemoService.seed_demo_data(
        org_id=tenant.org_id,
        session=session,
        user_id=tenant.user_id,
    )


@router.post("/reset", status_code=status.HTTP_200_OK)
def reset_demo_data(
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
) -> Dict[str, Any]:
    """Safely purges ONLY demo records (DEMO-*) without deleting actual merchant orders."""
    deleted_count = DemoService.reset_demo_data(
        org_id=tenant.org_id,
        session=session,
        user_id=tenant.user_id,
    )
    return {
        "status": "success",
        "message": f"Successfully purged {deleted_count} demo records.",
        "deleted_count": deleted_count,
    }


@router.post("/run-journey", status_code=status.HTTP_200_OK)
def run_demo_journey(
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
) -> Dict[str, Any]:
    """Executes the complete 8-step order-to-recovery journey and returns execution transcript."""
    return DemoService.run_complete_journey(
        org_id=tenant.org_id,
        session=session,
        user_id=tenant.user_id,
    )
