"""ImportJob and ImportJobError SQLAlchemy Models.

Enforces:
- Organization/tenant scoping for staging and persistent audit.
- Two-stage lifecycle: PREVIEW -> COMMITTED.
- Row-level validation tracking with exact row indices and field identifiers.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.audit_log import JSONType
from app.models.base import GUID, TimestampMixin


class ImportJob(Base, TimestampMixin):
    __tablename__ = "import_jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    filename = Column(String(255), nullable=False)
    # Status: PREVIEW | COMMITTED | CANCELLED
    status = Column(String(50), nullable=False, default="PREVIEW")

    total_rows = Column(Integer, nullable=False, default=0)
    valid_rows = Column(Integer, nullable=False, default=0)
    invalid_rows = Column(Integer, nullable=False, default=0)
    duplicate_rows = Column(Integer, nullable=False, default=0)

    # Staged valid row records stored during Stage A preview for Stage B commit
    staged_data = Column(JSONType, nullable=False, default=list)

    committed_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization")
    created_by = relationship("User")
    orders = relationship("Order", back_populates="import_job")
    errors = relationship("ImportJobError", back_populates="import_job", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("idx_import_jobs_org_created", "org_id", "created_at"),
    )


class ImportJobError(Base):
    __tablename__ = "import_job_errors"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    import_job_id = Column(GUID(), ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    row_index = Column(Integer, nullable=False)
    external_order_id = Column(String(255), nullable=True)
    column_name = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    import_job = relationship("ImportJob", back_populates="errors")
    organization = relationship("Organization")

    __table_args__ = (
        Index("idx_import_errors_org_job", "org_id", "import_job_id"),
    )
