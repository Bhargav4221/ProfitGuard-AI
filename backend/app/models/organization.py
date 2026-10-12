"""Organization Database Model."""

import uuid
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import GUID, TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(50), default="active", nullable=False)

    memberships = relationship("OrgMembership", back_populates="organization", cascade="all, delete-orphan")
    economics = relationship("MerchantEconomics", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")
    shopify_store = relationship("ShopifyStore", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    whatsapp_config = relationship("WhatsAppConfig", back_populates="organization", uselist=False, cascade="all, delete-orphan")

