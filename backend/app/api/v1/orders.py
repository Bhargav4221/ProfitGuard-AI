"""Orders API Endpoints.

Provides:
- POST   /orders          (Create manual order; OWNER, ADMIN, OPERATOR)
- GET    /orders          (List orders with filters & pagination; all roles)
- GET    /orders/{id}     (Get order details; all roles)
- PATCH  /orders/{id}     (Update order fields; OWNER, ADMIN, OPERATOR)
- GET    /orders/{id}/items (Get line items; all roles)
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_tenant_context, require_role
from app.core.tenant import OrganizationRole, TenantContext
from app.models.merchant_economics import MerchantEconomics
from app.schemas.decision import (
    InterventionOutcomeRequest,
    OrderDecisionRecordRequest,
    OrderEvaluationOut,
)
from app.schemas.order import DashboardSummaryOut, OrderCreate, OrderListOut, OrderItemOut, OrderOut, OrderUpdate
from app.schemas.outcome import OrderOutcomeOut, OutcomeRecordRequest
from app.schemas.reconciliation import FinancialReconciliationOut
from app.services.decision_engine import DecisionEngineService
from app.services.order_service import OrderService
from app.services.outcome_tracking_service import OutcomeTrackingService
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/orders", tags=["Orders"])

OPERATOR_ROLES = {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.OPERATOR}


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    order_in: OrderCreate,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Creates a new order manually within the tenant's workspace."""
    return OrderService.create_order(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        order_in=order_in,
        session=session,
    )


@router.get("", response_model=OrderListOut)
def list_orders(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
    status: Optional[str] = Query(default=None, description="Filter by order status"),
    payment_method: Optional[str] = Query(default=None, description="Filter by COD or PREPAID"),
    search: Optional[str] = Query(default=None, description="Search external ID, customer name, phone, or email"),
    date_from: Optional[datetime] = Query(default=None, description="Filter orders on or after date"),
    date_to: Optional[datetime] = Query(default=None, description="Filter orders on or before date"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lists orders for the tenant with multi-criteria filtering and pagination."""
    orders, total = OrderService.list_orders(
        org_id=tenant.org_id,
        session=session,
        status_filter=status,
        payment_method_filter=payment_method,
        search=search,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return OrderListOut(orders=orders, total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves authoritative database-backed business metrics for the tenant's workspace."""
    return OrderService.get_dashboard_summary(org_id=tenant.org_id, session=session)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves order details by internal UUID."""
    return OrderService.get_order(
        org_id=tenant.org_id,
        order_id=order_id,
        session=session,
    )


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(
    order_id: UUID,
    order_update: OrderUpdate,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Updates mutable fields of an order. Original order value remains immutable."""
    return OrderService.update_order(
        org_id=tenant.org_id,
        order_id=order_id,
        user_id=tenant.user_id,
        order_update=order_update,
        session=session,
    )


@router.post("/{order_id}/confirm", response_model=OrderOut)
def confirm_order(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Transitions a PENDING or HOLD order to CONFIRMED status via delivery lifecycle state machine."""
    order = OrderService.get_order(org_id=tenant.org_id, order_id=order_id, session=session)
    if order.status == "CONFIRMED":
        return order

    from app.schemas.delivery import DeliveryEventCreate
    from app.services.delivery_service import DeliveryService

    event_in = DeliveryEventCreate(
        order_id=order_id,
        event_type="CONFIRMED",
        event_source="MANUAL_OPERATOR",
        is_simulated=False,
        reason_description="Order manually confirmed by operator",
    )
    _, updated_order = DeliveryService.record_delivery_event(
        org_id=tenant.org_id,
        order_id=order_id,
        event_in=event_in,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return updated_order


@router.post("/{order_id}/resume", response_model=OrderOut)
def resume_order(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Lifts HOLD on an order and resumes it back to CONFIRMED."""
    order = OrderService.get_order(org_id=tenant.org_id, order_id=order_id, session=session)
    if order.status != "HOLD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is in '{order.status}', not in 'HOLD'. Only orders on hold can be resumed.",
        )

    from app.schemas.delivery import DeliveryEventCreate
    from app.services.delivery_service import DeliveryService

    event_in = DeliveryEventCreate(
        order_id=order_id,
        event_type="CONFIRMED",
        event_source="MANUAL_OPERATOR",
        is_simulated=False,
        reason_description="Hold released by operator; resumed to confirmed",
    )
    _, updated_order = DeliveryService.record_delivery_event(
        org_id=tenant.org_id,
        order_id=order_id,
        event_in=event_in,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return updated_order


@router.get("/{order_id}/items", response_model=List[OrderItemOut])
def list_order_items(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Lists individual line items for an order."""
    return OrderService.list_order_items(
        org_id=tenant.org_id,
        order_id=order_id,
        session=session,
    )


# -----------------------------------------------------------------------------
# Decision Engine & 5-Action Evaluation Endpoints
# -----------------------------------------------------------------------------


@router.post("/{order_id}/evaluate", response_model=OrderEvaluationOut)
def evaluate_order(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Evaluates order across all 5 candidate actions, calculating risk and expected contribution."""
    order = OrderService.get_order(org_id=tenant.org_id, order_id=order_id, session=session)
    economics = session.scalar(select(MerchantEconomics).where(MerchantEconomics.org_id == tenant.org_id))
    if not economics:
        economics = MerchantEconomics(org_id=tenant.org_id)
        session.add(economics)
        session.flush()

    return DecisionEngineService.evaluate_order(
        order=order,
        economics=economics,
        session=session,
        evaluated_by_user_id=tenant.user_id,
    )


@router.get("/{order_id}/decision", response_model=OrderEvaluationOut)
def get_order_decision(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves latest decision evaluation and candidate action comparison."""
    # Ensure order exists in this tenant
    _ = OrderService.get_order(org_id=tenant.org_id, order_id=order_id, session=session)
    return DecisionEngineService.get_latest_evaluation(
        order_id=order_id,
        org_id=tenant.org_id,
        session=session,
    )


@router.post("/{order_id}/decision", response_model=OrderEvaluationOut)
def record_order_decision(
    order_id: UUID,
    req: OrderDecisionRecordRequest,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Records an authorized decision (acceptance or override with reason) and updates order status."""
    return DecisionEngineService.record_decision(
        order_id=order_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action=req.action,
        override_reason=req.override_reason,
        session=session,
    )


@router.post("/{order_id}/intervention-outcome", response_model=OrderEvaluationOut)
def record_intervention_outcome(
    order_id: UUID,
    req: InterventionOutcomeRequest,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Records outcome of an executed pre-dispatch intervention (e.g. OTP verified/failed)."""
    return DecisionEngineService.record_intervention_outcome(
        order_id=order_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        outcome=req.outcome,
        notes=req.notes,
        session=session,
    )


# -----------------------------------------------------------------------------
# Financial Reconciliation & Realized Contribution Endpoints
# -----------------------------------------------------------------------------


@router.get("/{order_id}/reconciliation", response_model=FinancialReconciliationOut)
def get_order_reconciliation(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves authoritative ex-post financial reconciliation ledger for an order."""
    # Ensure order exists in this tenant
    _ = OrderService.get_order(org_id=tenant.org_id, order_id=order_id, session=session)
    return ReconciliationService.get_order_reconciliation(
        org_id=tenant.org_id,
        order_id=order_id,
        session=session,
    )


@router.post("/{order_id}/reconcile", response_model=FinancialReconciliationOut)
def reconcile_order(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Calculates and persists the authoritative realized contribution ledger."""
    return ReconciliationService.reconcile_order(
        org_id=tenant.org_id,
        order_id=order_id,
        session=session,
        actor_user_id=tenant.user_id,
    )


# -----------------------------------------------------------------------------
# Real-Order Outcome Tracking Endpoints
# -----------------------------------------------------------------------------


@router.get("/{order_id}/outcome", response_model=OrderOutcomeOut)
def get_order_outcome(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves authoritative real-order outcome record linking prediction, policy, and realized financials."""
    return OutcomeTrackingService.get_order_outcome(
        org_id=tenant.org_id,
        order_id=order_id,
        session=session,
    )


@router.post("/{order_id}/outcome", response_model=OrderOutcomeOut)
def record_order_outcome(
    order_id: UUID,
    req: OutcomeRecordRequest,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Idempotently records or updates closed-loop outcome for an order that reached terminal delivery status."""
    return OutcomeTrackingService.record_order_outcome(
        org_id=tenant.org_id,
        order_id=order_id,
        session=session,
        actor_user_id=tenant.user_id,
        notes=req.notes,
    )



