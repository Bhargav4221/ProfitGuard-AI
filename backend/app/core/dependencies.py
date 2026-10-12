"""FastAPI Security Dependencies: Authentication, Tenant Isolation, and RBAC Guards.

Enforces:
1. Valid JWT bearer token with revocation check against `revoked_tokens`.
2. Mandatory `X-Org-Id` header with verified user membership in that organization.
3. Transaction-local database RLS configuration via `set_transaction_tenant_context`.
4. Role-Based Access Control (RBAC) authorization guards.
"""

from typing import Annotated, Callable, Optional, Set
from uuid import UUID
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, set_transaction_tenant_context
from app.core.security import decode_token
from app.core.tenant import OrganizationRole, TenantContext, set_current_tenant
from app.models.membership import OrgMembership
from app.models.revoked_token import RevokedToken
from app.models.user import User

security_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_bearer)],
    session: Annotated[Session, Depends(get_db)]
) -> User:
    """Authenticates JWT access token, checks revocation, and returns current user."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: access token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    if jti:
        is_revoked = session.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
        if is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user ID in token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_tenant_context(
    x_org_id: Annotated[Optional[str], Header(alias="X-Org-Id")] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_db)] = None
) -> TenantContext:
    """Extracts X-Org-Id header, verifies user membership, sets transaction-local RLS, and returns TenantContext.
    
    Denies access by default if X-Org-Id header is absent or user lacks membership in that organization.
    """
    if not x_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'X-Org-Id' header for organization-scoped resource.",
        )

    try:
        org_id = UUID(x_org_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format for 'X-Org-Id'. Expected UUID.",
        )

    # Verify that the user has an active membership in the requested organization
    membership = session.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == current_user.id
        )
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you are not a member of the requested organization.",
        )

    tenant = TenantContext(
        org_id=org_id,
        user_id=current_user.id,
        role=membership.role
    )

    # Bind transaction-local RLS configuration
    set_transaction_tenant_context(session, org_id)

    # Propagate to ContextVar for downstream logging and worker calls
    set_current_tenant(tenant)

    return tenant


def require_role(allowed_roles: Set[OrganizationRole]) -> Callable:
    """Dependency factory returning a validator ensuring the tenant has sufficient permissions."""
    def role_checker(
        tenant: Annotated[TenantContext, Depends(get_tenant_context)]
    ) -> TenantContext:
        tenant.require_role(allowed_roles)
        return tenant

    return role_checker
