"""Monitoring and Closed-Loop Outcome Analytics API Endpoints.

Provides:
- GET /monitoring/outcomes  (Lists outcome tracking records with filters & pagination)
- GET /monitoring/metrics   (Computes closed-loop monitoring metrics separating observed facts from modeled estimates)
"""

from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_tenant_context
from app.core.tenant import TenantContext
from app.schemas.outcome import (
    OrderOutcomeListOut,
    OrderOutcomeOut,
    OutcomeMonitoringMetricsOut,
)
from app.services.outcome_tracking_service import OutcomeTrackingService

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Outcomes"])


@router.get("/outcomes", response_model=OrderOutcomeListOut)
def list_outcomes(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
    final_delivery_outcome: Optional[str] = Query(default=None, description="Filter by terminal delivery outcome: DELIVERED | RTO | CANCELLED"),
    model_version: Optional[str] = Query(default=None, description="Filter by ML model version"),
    date_from: Optional[datetime] = Query(default=None, description="Filter outcomes on or after date"),
    date_to: Optional[datetime] = Query(default=None, description="Filter outcomes on or before date"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lists completed order outcome tracking records with tenant isolation and multi-criteria filters."""
    items, total = OutcomeTrackingService.list_order_outcomes(
        org_id=tenant.org_id,
        session=session,
        final_delivery_outcome=final_delivery_outcome,
        model_version=model_version,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return OrderOutcomeListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/metrics", response_model=OutcomeMonitoringMetricsOut)
def get_monitoring_metrics(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
    date_from: Optional[datetime] = Query(default=None, description="Start date for completed outcome cohort"),
    date_to: Optional[datetime] = Query(default=None, description="End date for completed outcome cohort"),
    operating_threshold: float = Query(default=0.18, ge=0.01, le=0.99, description="Operating risk threshold for empirical precision/recall evaluation"),
):
    """Computes closed-loop outcome metrics: coverage, RTO rate, precision/recall, realized costs, and net contribution.
    
    Clearly separates verified cash facts from modeled counterfactual estimates.
    """
    return OutcomeTrackingService.get_monitoring_metrics(
        org_id=tenant.org_id,
        session=session,
        date_from=date_from,
        date_to=date_to,
        operating_threshold=operating_threshold,
    )


@router.get("/ml-status")
def get_ml_status(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
):
    """Returns the current ML operating mode, model readiness gates, and serving metadata."""
    from app.core.config import settings
    from app.services.ml_inference_service import ml_inference_service

    metadata = ml_inference_service.get_metadata()
    return {
        "operating_mode": ml_inference_service.get_operating_mode(),
        "is_approved_for_consequential_actions": ml_inference_service.is_approved_for_consequential_actions(),
        "decision_policy_version": getattr(settings, "ML_DECISION_POLICY_VERSION", "v1.1-ml-assisted"),
        "model_loaded": ml_inference_service.is_ready(),
        "model_metadata": metadata,
        "governance_notice": (
            "Synthetic development weights: strictly restricted from autonomous order cancellation. "
            "Operates in advisory/assisted mode only."
        ),
    }

