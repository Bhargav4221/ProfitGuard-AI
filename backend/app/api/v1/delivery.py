"""Delivery Lifecycle, Tracking Events, and NDR Recovery API Endpoints.

Provides:
- POST /delivery/events              (Record courier or manual delivery event; OPERATOR, ADMIN, OWNER)
- POST /delivery/simulate            (Simulate courier tracking event with is_simulated=True; OPERATOR, ADMIN, OWNER)
- POST /delivery/webhook             (Courier webhook receiver with HMAC signature check)
- GET  /delivery/events/{order_id}   (List delivery events for an order; all tenant roles)
- GET  /delivery/ndr                 (List NDR cases with filtering & pagination; all tenant roles)
- GET  /delivery/ndr/{case_id}       (Get NDR case details, order details & actions; all tenant roles)
- POST /delivery/ndr/{case_id}/actions (Record recovery action: CONTACT, ADDRESS, REATTEMPT, etc.; OPERATOR, ADMIN, OWNER)
- GET  /delivery/ndr/{case_id}/recommendation (Get decision support lift calculation; all tenant roles)
"""

from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_tenant_context, require_role
from app.core.tenant import OrganizationRole, TenantContext
from app.models.delivery import DeliveryEvent, NDRCase
from app.models.merchant_economics import MerchantEconomics
from app.models.order import Order
from app.schemas.delivery import (
    CourierWebhookPayload,
    DeliveryEventCreate,
    DeliveryEventOut,
    NDRActionCreate,
    NDRCaseOut,
    NDRListOut,
    NDRRecommendationOut,
    SimulateDeliveryRequest,
)
from app.services.delivery_service import DeliveryService
from app.services.order_service import OrderService

router = APIRouter(prefix="/delivery", tags=["Delivery & NDR Recovery"])

OPERATOR_ROLES = {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.OPERATOR}


def _enrich_ndr_case(case: NDRCase) -> NDRCaseOut:
    """Enriches NDRCase with order summary fields for frontend presentation."""
    order = case.order
    return NDRCaseOut(
        id=case.id,
        org_id=case.org_id,
        order_id=case.order_id,
        case_number=case.case_number,
        status=case.status,
        priority=case.priority,
        attempt_count=case.attempt_count,
        last_attempt_date=case.last_attempt_date,
        reason_code=case.reason_code,
        carrier_reason_raw=case.carrier_reason_raw,
        assigned_operator_id=case.assigned_operator_id,
        assigned_operator_name=case.assigned_operator_name,
        customer_contacted=case.customer_contacted,
        contact_method=case.contact_method,
        customer_response=case.customer_response,
        updated_address1=case.updated_address1,
        updated_address2=case.updated_address2,
        updated_city=case.updated_city,
        updated_state=case.updated_state,
        updated_pincode=case.updated_pincode,
        updated_phone=case.updated_phone,
        reattempt_date=case.reattempt_date,
        next_action=case.next_action,
        next_action_due=case.next_action_due,
        is_simulated=case.is_simulated,
        expected_recovery_lift=case.expected_recovery_lift,
        estimated_recovery_ec=case.estimated_recovery_ec,
        recommended_recovery_action=case.recommended_recovery_action,
        recommendation_rationale=case.recommendation_rationale,
        closed_at=case.closed_at,
        closure_reason=case.closure_reason,
        created_at=case.created_at,
        updated_at=case.updated_at,
        order_external_id=order.external_order_id if order else None,
        order_value=order.order_value if order else None,
        customer_name=order.customer_name if order else None,
        customer_phone=order.customer_phone if order else None,
        shipping_city=order.shipping_city if order else None,
        shipping_pincode=order.shipping_pincode if order else None,
        payment_method=order.payment_method if order else None,
        actions=case.actions if hasattr(case, "actions") else [],
    )


@router.post("/events", response_model=DeliveryEventOut, status_code=status.HTTP_201_CREATED)
def record_delivery_event(
    event_in: DeliveryEventCreate,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Ingests a delivery tracking event, validates lifecycle state machine, and triggers NDR if failed."""
    event, _ = DeliveryService.record_delivery_event(
        org_id=tenant.org_id,
        order_id=event_in.order_id,
        event_in=event_in,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return event


@router.post("/simulate", response_model=DeliveryEventOut, status_code=status.HTTP_201_CREATED)
def simulate_delivery_event(
    req: SimulateDeliveryRequest,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Simulates a courier delivery tracking event for testing and workflows.
    
    Strictly marked with is_simulated=True and event_source='COURIER_WEBHOOK_SIMULATED'.
    """
    event_in = DeliveryEventCreate(
        order_id=req.order_id,
        event_id=req.event_id,
        event_type=req.event_type,
        event_source="COURIER_WEBHOOK_SIMULATED",
        is_simulated=True,
        carrier_name=req.carrier_name or "Delhivery (Simulated)",
        reason_code=req.reason_code,
        reason_description=req.notes or f"Simulated delivery event: {req.event_type}",
        location=req.location or "Regional Delivery Hub",
    )
    event, _ = DeliveryService.record_delivery_event(
        org_id=tenant.org_id,
        order_id=req.order_id,
        event_in=event_in,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return event


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def courier_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    x_courier_signature: Optional[str] = Header(default=None, alias="X-Courier-Signature"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    """Receives courier webhooks with HMAC-SHA256 signature verification.
    
    Validates webhook signature against webhook secret to prevent spoofing.
    """
    raw_body = await request.body()

    # Secret from settings or environment
    webhook_secret = getattr(settings, "COURIER_WEBHOOK_SECRET", "pg_webhook_secret_default")
    if webhook_secret:
        if not DeliveryService.verify_webhook_signature(raw_body, x_courier_signature, webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid courier webhook HMAC signature.",
            )

    try:
        payload_data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body.")

    # Org ID from header or payload
    org_id_str = x_org_id or payload_data.get("org_id")
    if not org_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required organization context in webhook.",
        )
    try:
        org_id = UUID(org_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed org_id.")

    # Match order by tracking number or external_order_id
    tracking_num = payload_data.get("tracking_number")
    external_order_id = payload_data.get("external_order_id")
    order = None

    if tracking_num:
        order = session.scalar(
            select(Order).where(Order.org_id == org_id, Order.tracking_number == tracking_num)
        )
    if not order and external_order_id:
        order = session.scalar(
            select(Order).where(Order.org_id == org_id, Order.external_order_id == external_order_id)
        )

    if not order:
        return {"status": "ignored", "message": "Order not found for tracking details."}

    event_in = DeliveryEventCreate(
        order_id=order.id,
        event_id=payload_data.get("event_id"),
        event_type=payload_data.get("status", "IN_TRANSIT"),
        event_source="COURIER_WEBHOOK",
        is_simulated=False,
        carrier_name=payload_data.get("carrier", "Carrier"),
        tracking_number=tracking_num,
        carrier_status_code=payload_data.get("sub_status"),
        reason_code=payload_data.get("reason_code"),
        reason_description=payload_data.get("reason_description"),
        location=payload_data.get("location"),
        raw_payload=payload_data,
    )

    event, updated_order = DeliveryService.record_delivery_event(
        org_id=org_id,
        order_id=order.id,
        event_in=event_in,
        session=session,
    )
    return {"status": "success", "event_id": str(event.id), "new_order_status": updated_order.status}


@router.get("/events/{order_id}", response_model=List[DeliveryEventOut])
def get_order_delivery_events(
    order_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Returns chronological delivery tracking events for an order."""
    # Ensure order belongs to this tenant
    _ = OrderService.get_order(org_id=tenant.org_id, order_id=order_id, session=session)

    events = list(
        session.scalars(
            select(DeliveryEvent)
            .where(DeliveryEvent.org_id == tenant.org_id, DeliveryEvent.order_id == order_id)
            .order_by(DeliveryEvent.occurred_at.asc(), DeliveryEvent.created_at.asc())
        ).all()
    )
    return events


@router.get("/ndr", response_model=NDRListOut)
def list_ndr_cases(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
    status: Optional[str] = Query(default=None, description="Filter by status: OPEN, IN_PROGRESS, REATTEMPT_SCHEDULED, RESOLVED, CLOSED"),
    reason: Optional[str] = Query(default=None, description="Filter by failure reason code"),
    priority: Optional[str] = Query(default=None, description="Filter by priority: HIGH, MEDIUM, LOW"),
    search: Optional[str] = Query(default=None, description="Search case number, customer, phone, or order ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lists NDR recovery cases with multi-criteria filtering, search, and pagination."""
    cases, total = DeliveryService.list_ndr_cases(
        org_id=tenant.org_id,
        session=session,
        status_filter=status,
        reason_filter=reason,
        priority_filter=priority,
        search=search,
        limit=limit,
        offset=offset,
    )
    enriched = [_enrich_ndr_case(c) for c in cases]
    return NDRListOut(cases=enriched, total=total, limit=limit, offset=offset)


@router.get("/ndr/{case_id}", response_model=NDRCaseOut)
def get_ndr_case(
    case_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves single NDR recovery case details, order details, and recovery action logs."""
    case = DeliveryService.get_ndr_case(org_id=tenant.org_id, case_id=case_id, session=session)
    return _enrich_ndr_case(case)


@router.post("/ndr/{case_id}/actions", response_model=NDRCaseOut)
def record_ndr_action(
    case_id: UUID,
    action_in: NDRActionCreate,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Executes a permitted recovery action on an active NDR case."""
    updated_case = DeliveryService.record_ndr_action(
        org_id=tenant.org_id,
        case_id=case_id,
        action_in=action_in,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return _enrich_ndr_case(updated_case)


@router.get("/ndr/{case_id}/recommendation", response_model=NDRRecommendationOut)
def get_ndr_recommendation(
    case_id: UUID,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Calculates real-time recovery decision recommendation and lift for an NDR case."""
    case = DeliveryService.get_ndr_case(org_id=tenant.org_id, case_id=case_id, session=session)
    order = case.order
    economics = session.scalar(
        select(MerchantEconomics).where(MerchantEconomics.org_id == tenant.org_id)
    )
    if not economics:
        economics = MerchantEconomics(org_id=tenant.org_id)
        session.add(economics)
        session.flush()

    rec = DeliveryService.compute_recovery_recommendation(
        order=order,
        economics=economics,
        reason_code=case.reason_code,
    )
    rec.ndr_case_id = case.id
    return rec
