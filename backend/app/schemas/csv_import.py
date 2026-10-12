"""Pydantic Schemas for Two-Stage CSV Import Pipeline."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CSVRowError(BaseModel):
    row_index: int
    external_order_id: Optional[str] = None
    column_name: Optional[str] = None
    error_message: str


class CSVPreviewResponse(BaseModel):
    preview_id: UUID
    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    sample_valid_rows: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[CSVRowError] = Field(default_factory=list)


class CSVCommitRequest(BaseModel):
    preview_id: UUID


class CSVCommitResponse(BaseModel):
    import_id: UUID
    filename: str
    status: str
    inserted_count: int
    skipped_count: int
    total_rows: int


class ImportJobErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    row_index: int
    external_order_id: Optional[str]
    column_name: Optional[str]
    error_message: str
    created_at: datetime


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    filename: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    created_at: datetime
    committed_at: Optional[datetime]
    errors: List[ImportJobErrorOut] = Field(default_factory=list)


class ImportJobListOut(BaseModel):
    jobs: List[ImportJobOut]
    total: int
    limit: int
    offset: int
