"""Organization & Membership Management API."""

import re
from typing import List
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.tenant import OrganizationRole
from app.models.membership import OrgMembership
from app.models.merchant_economics import MerchantEconomics
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import (
    MemberInvite,
    MemberRoleUpdate,
    MembershipOut,
    OrganizationCreate,
    OrganizationOut,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/orgs", tags=["Organizations"])


@router.get("", response_model=List[MembershipOut])
def list_user_organizations(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lists all organizations and active roles for the authenticated user."""
    memberships = session.scalars(
        select(OrgMembership).where(OrgMembership.user_id == current_user.id)
    ).all()
    return memberships


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Creates a new organization and assigns the creator as OWNER."""
    base_slug = re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")
    slug = f"{base_slug}-{str(uuid4())[:8]}"

    org = Organization(name=payload.name, slug=slug, status="active")
    session.add(org)
    session.flush()

    membership = OrgMembership(
        org_id=org.id,
        user_id=current_user.id,
        role=OrganizationRole.OWNER,
    )
    session.add(membership)

    economics = MerchantEconomics(org_id=org.id)
    session.add(economics)
    session.flush()

    AuditService.record_event(
        session=session,
        org_id=org.id,
        actor_user_id=current_user.id,
        action="ORGANIZATION_CREATED",
        resource_type="Organization",
        resource_id=str(org.id),
        payload={"name": org.name, "created_by": current_user.email},
    )

    session.commit()
    return org


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(
    org_id: UUID,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetches details for an organization, verifying the user is a member."""
    membership = session.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == current_user.id
        )
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you are not a member of this organization.",
        )

    org = session.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    return org


@router.post("/{org_id}/members/invite", status_code=status.HTTP_201_CREATED)
def invite_member(
    org_id: UUID,
    payload: MemberInvite,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invites a user to the organization. Requires OWNER or ADMIN role."""
    inviter_membership = session.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == current_user.id
        )
    )
    if not inviter_membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden.")

    if inviter_membership.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: only OWNER or ADMIN can invite members.",
        )

    # Find the target user
    target_user = session.scalar(select(User).where(User.email == payload.email.lower()))
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this email is not registered yet.",
        )

    existing_membership = session.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == target_user.id
        )
    )
    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this organization.",
        )

    new_membership = OrgMembership(
        org_id=org_id,
        user_id=target_user.id,
        role=payload.role,
    )
    session.add(new_membership)

    AuditService.record_event(
        session=session,
        org_id=org_id,
        actor_user_id=current_user.id,
        action="MEMBER_ADDED",
        resource_type="OrgMembership",
        resource_id=str(new_membership.id),
        payload={"invited_email": target_user.email, "assigned_role": payload.role.value},
    )

    session.commit()
    return {"message": f"Successfully added {target_user.email} as {payload.role.value}."}


@router.patch("/{org_id}/members/{user_id}/role", status_code=status.HTTP_200_OK)
def update_member_role(
    org_id: UUID,
    user_id: UUID,
    payload: MemberRoleUpdate,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Updates a member's role. Requires OWNER role."""
    updater_membership = session.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == current_user.id
        )
    )
    if not updater_membership or updater_membership.role != OrganizationRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization OWNER can modify member roles.",
        )

    target_membership = session.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id
        )
    )
    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user is not a member of this organization.",
        )

    old_role = target_membership.role.value
    target_membership.role = payload.role

    AuditService.record_event(
        session=session,
        org_id=org_id,
        actor_user_id=current_user.id,
        action="MEMBER_ROLE_UPDATED",
        resource_type="OrgMembership",
        resource_id=str(target_membership.id),
        payload={"target_user_id": str(user_id), "old_role": old_role, "new_role": payload.role.value},
    )

    session.commit()
    return {"message": f"Role updated from {old_role} to {payload.role.value}."}
