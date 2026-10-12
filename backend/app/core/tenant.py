"""Tenant Context Abstraction and ContextVars Propagation.

Every multi-tenant request or task operates within an active TenantContext.
If a tenant context is missing or invalid, access is denied by default.
"""

from contextvars import ContextVar
from enum import Enum
from typing import Optional, Set
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from fastapi import HTTPException, status


class OrganizationRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    AUDITOR = "AUDITOR"


# Context variable for context-local tenant propagation (used in async tasks & worker sessions)
_current_tenant_var: ContextVar[Optional["TenantContext"]] = ContextVar("current_tenant", default=None)


class TenantContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    org_id: UUID
    user_id: UUID
    role: OrganizationRole

    def require_role(self, allowed_roles: Set[OrganizationRole]) -> None:
        """Enforces that the tenant context has one of the allowed roles.
        
        Raises HTTP 403 Forbidden if the user's role is not permitted.
        """
        if self.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: role '{self.role.value}' lacks required authorization.",
            )

    @property
    def is_owner(self) -> bool:
        return self.role == OrganizationRole.OWNER

    @property
    def is_admin(self) -> bool:
        return self.role in {OrganizationRole.OWNER, OrganizationRole.ADMIN}

    @property
    def can_operate(self) -> bool:
        return self.role in {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.OPERATOR}

    @property
    def is_auditor(self) -> bool:
        return self.role == OrganizationRole.AUDITOR


def set_current_tenant(tenant: Optional[TenantContext]):
    return _current_tenant_var.set(tenant)


def get_current_tenant() -> Optional[TenantContext]:
    return _current_tenant_var.get()
