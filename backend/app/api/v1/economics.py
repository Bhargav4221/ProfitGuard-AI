"""Merchant Unit Economics API."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_tenant_context, require_role
from app.core.tenant import OrganizationRole, TenantContext
from app.models.merchant_economics import MerchantEconomics
from app.schemas.economics import MerchantEconomicsOut, MerchantEconomicsUpdate
from app.services.audit_service import AuditService

router = APIRouter(prefix="/economics", tags=["Merchant Economics"])


@router.get("", response_model=MerchantEconomicsOut)
def get_economics(
    tenant: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Fetches merchant unit economics configuration for the active tenant."""
    economics = session.scalar(
        select(MerchantEconomics).where(MerchantEconomics.org_id == tenant.org_id)
    )
    if not economics:
        # Lazy initialization if missing
        economics = MerchantEconomics(org_id=tenant.org_id)
        session.add(economics)
        session.commit()
    return economics


@router.put("", response_model=MerchantEconomicsOut)
def update_economics(
    payload: MerchantEconomicsUpdate,
    tenant: TenantContext = Depends(require_role({OrganizationRole.OWNER, OrganizationRole.ADMIN})),
    session: Session = Depends(get_db),
):
    """Updates unit economics configuration. Requires OWNER or ADMIN role."""
    economics = session.scalar(
        select(MerchantEconomics).where(MerchantEconomics.org_id == tenant.org_id)
    )
    if not economics:
        economics = MerchantEconomics(org_id=tenant.org_id)
        session.add(economics)

    for field, value in payload.model_dump().items():
        setattr(economics, field, value)

    AuditService.record_event(
        session=session,
        org_id=tenant.org_id,
        actor_user_id=tenant.user_id,
        action="ECONOMICS_CONFIG_UPDATED",
        resource_type="MerchantEconomics",
        resource_id=str(economics.id),
        payload={"updated_fields": list(payload.model_dump().keys())},
    )

    session.commit()
    session.refresh(economics)
    return economics
