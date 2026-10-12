"""Organization Membership and RBAC Model."""

import uuid
from sqlalchemy import Column, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.tenant import OrganizationRole
from app.models.base import GUID, TimestampMixin


class OrgMembership(Base, TimestampMixin):
    __tablename__ = "org_memberships"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(OrganizationRole, name="org_role_enum"), nullable=False, default=OrganizationRole.OPERATOR)

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_membership_user"),
    )
