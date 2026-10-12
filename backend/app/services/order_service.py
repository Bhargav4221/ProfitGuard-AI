"""Order Management Service.

Provides:
- Organization-scoped Order CRUD operations.
- Enforces immutability of original order value and external identifiers.
- Line items association and Decimal arithmetic validation.
- Filtering, search, and pagination.
- Complete hash-chained audit logging for creation and modifications.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.delivery import NDRCase
from app.models.financial_reconciliation import OrderFinancialReconciliation
from app.models.order import Order
from app.models.order_decision import OrderEvaluation
from app.models.order_item import OrderItem
from app.schemas.order import OrderCreate, OrderUpdate
from app.services.audit_service import AuditService


class OrderService:
    @staticmethod
    def create_order(
        org_id: UUID,
        user_id: UUID,
        order_in: OrderCreate,
        session: Session,
    ) -> Order:
        """Creates a single manual order with items, scoped strictly to org_id."""
        # Check tenant-scoped external_order_id uniqueness
        existing = session.scalar(
            select(Order).where(
                Order.org_id == org_id,
                Order.external_order_id == order_in.external_order_id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Order with external ID '{order_in.external_order_id}' already exists in your organization.",
            )

        order_date = order_in.order_date or datetime.now(timezone.utc)

        order = Order(
            org_id=org_id,
            external_order_id=order_in.external_order_id,
            order_date=order_date,
            currency=order_in.currency or "INR",
            order_value=order_in.order_value,
            payment_method=order_in.payment_method,
            status=order_in.status or "PENDING",
            fulfillment_status=order_in.fulfillment_status or "UNFULFILLED",
            customer_name=order_in.customer_name,
            customer_phone=order_in.customer_phone,
            customer_email=order_in.customer_email,
            shipping_address1=order_in.shipping_address1,
            shipping_address2=order_in.shipping_address2,
            shipping_city=order_in.shipping_city,
            shipping_state=order_in.shipping_state,
            shipping_pincode=order_in.shipping_pincode,
            shipping_country=order_in.shipping_country or "IN",
            courier_name=order_in.courier_name,
            tracking_number=order_in.tracking_number,
            source_channel=order_in.source_channel or "MANUAL",
        )
        session.add(order)
        session.flush()

        # Add line items if specified
        for item_in in order_in.items:
            total_price = item_in.quantity * item_in.unit_price
            item = OrderItem(
                org_id=org_id,
                order_id=order.id,
                sku=item_in.sku,
                external_product_id=item_in.external_product_id,
                product_name=item_in.product_name,
                quantity=item_in.quantity,
                unit_price=item_in.unit_price,
                unit_cost=item_in.unit_cost,
                total_price=total_price,
            )
            session.add(item)

        # Audit log entry
        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=user_id,
            action="ORDER_CREATED",
            resource_type="Order",
            resource_id=str(order.id),
            payload={
                "external_order_id": order.external_order_id,
                "order_value": str(order.order_value),
                "payment_method": order.payment_method,
                "item_count": len(order_in.items),
                "source_channel": order.source_channel,
            },
        )

        session.commit()
        session.refresh(order)
        return order

    @staticmethod
    def get_order(
        org_id: UUID,
        order_id: UUID,
        session: Session,
    ) -> Order:
        """Retrieves a single order by ID, enforcing tenant isolation."""
        order = session.scalar(
            select(Order).where(
                Order.id == order_id,
                Order.org_id == org_id,
            )
        )
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found or unauthorized.",
            )
        return order

    @staticmethod
    def list_orders(
        org_id: UUID,
        session: Session,
        status_filter: Optional[str] = None,
        payment_method_filter: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Order], int]:
        """Lists orders for tenant with filtering, search, and pagination."""
        query = select(Order).where(Order.org_id == org_id)

        if status_filter:
            query = query.where(Order.status == status_filter)

        if payment_method_filter:
            query = query.where(Order.payment_method == payment_method_filter)

        if date_from:
            query = query.where(Order.order_date >= date_from)

        if date_to:
            query = query.where(Order.order_date <= date_to)

        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Order.external_order_id.ilike(search_pattern),
                    Order.customer_name.ilike(search_pattern),
                    Order.customer_phone.ilike(search_pattern),
                    Order.customer_email.ilike(search_pattern),
                )
            )

        # Count total matches before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = session.scalar(count_query) or 0

        # Apply ordering and pagination
        query = query.order_by(Order.order_date.desc(), Order.created_at.desc())
        query = query.limit(min(limit, 200)).offset(max(offset, 0))

        orders = list(session.scalars(query).all())
        return orders, total

    @staticmethod
    def update_order(
        org_id: UUID,
        order_id: UUID,
        user_id: UUID,
        order_update: OrderUpdate,
        session: Session,
    ) -> Order:
        """Updates mutable fields on an existing order.
        
        Strictly guarantees:
        - Immutable fields ('order_value', 'org_id', 'id', 'external_order_id') CANNOT be changed.
        - Changes are logged in the append-only audit trail.
        """
        order = OrderService.get_order(org_id=org_id, order_id=order_id, session=session)

        # Collect changed fields
        update_data = order_update.model_dump(exclude_unset=True)
        changes = {}

        for field, new_val in update_data.items():
            # Immutable safety guard
            if field in {"id", "org_id", "external_order_id", "order_value", "currency"}:
                continue
            old_val = getattr(order, field)
            if old_val != new_val:
                if field == "status" and new_val is not None:
                    from app.services.delivery_service import ALLOWED_TRANSITIONS, DeliveryService
                    if not DeliveryService.validate_transition(old_val, new_val):
                        allowed = list(ALLOWED_TRANSITIONS.get(old_val, []))
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid transition: cannot move from '{old_val}' to '{new_val}'. Permitted next states: {allowed}",
                        )
                    if new_val in ("SHIPPED", "OUT_FOR_DELIVERY", "NDR", "DELIVERED", "RTO"):
                        order.fulfillment_status = "FULFILLED"
                    elif new_val in ("PENDING", "CONFIRMED", "READY_TO_SHIP"):
                        order.fulfillment_status = "UNFULFILLED"
                    elif new_val in ("HOLD", "CANCELLED"):
                        order.fulfillment_status = "HOLD"
                setattr(order, field, new_val)
                changes[field] = {"old": str(old_val) if old_val is not None else None, "new": str(new_val) if new_val is not None else None}

        if changes:
            AuditService.record_event(
                session=session,
                org_id=org_id,
                actor_user_id=user_id,
                action="ORDER_UPDATED",
                resource_type="Order",
                resource_id=str(order.id),
                payload={"changes": changes},
            )
            session.commit()
            session.refresh(order)

        return order

    @staticmethod
    def list_order_items(
        org_id: UUID,
        order_id: UUID,
        session: Session,
    ) -> List[OrderItem]:
        """Lists line items for an order, verifying tenant ownership."""
        # Ensure order belongs to this tenant
        _ = OrderService.get_order(org_id=org_id, order_id=order_id, session=session)

        items = list(
            session.scalars(
                select(OrderItem).where(
                    OrderItem.org_id == org_id,
                    OrderItem.order_id == order_id,
                )
            ).all()
        )
        return items

    @staticmethod
    def get_dashboard_summary(org_id: UUID, session: Session) -> dict:
        """Calculates tenant-scoped summary metrics derived from database records."""
        total_orders = session.scalar(select(func.count(Order.id)).where(Order.org_id == org_id)) or 0
        total_gmv = session.scalar(
            select(func.coalesce(func.sum(Order.order_value), 0)).where(Order.org_id == org_id)
        ) or Decimal("0.00")

        # Status breakdown
        status_rows = session.execute(
            select(Order.status, func.count(Order.id))
            .where(Order.org_id == org_id)
            .group_by(Order.status)
        ).all()
        status_breakdown = {str(row[0]): int(row[1]) for row in status_rows}

        # Payment method breakdown
        pm_rows = session.execute(
            select(Order.payment_method, func.count(Order.id))
            .where(Order.org_id == org_id)
            .group_by(Order.payment_method)
        ).all()
        payment_method_breakdown = {str(row[0]): int(row[1]) for row in pm_rows}

        # Expected contribution sum from OrderEvaluation (best_ec)
        ec_sum = session.scalar(
            select(func.coalesce(func.sum(OrderEvaluation.best_ec), 0))
            .where(OrderEvaluation.org_id == org_id)
        ) or Decimal("0.00")

        # Realized contribution sum from OrderFinancialReconciliation
        rc_sum = session.scalar(
            select(func.coalesce(func.sum(OrderFinancialReconciliation.realized_contribution), 0))
            .where(OrderFinancialReconciliation.org_id == org_id)
        ) or Decimal("0.00")

        # High risk count
        high_risk_count = session.scalar(
            select(func.count(func.distinct(OrderEvaluation.order_id)))
            .where(
                OrderEvaluation.org_id == org_id,
                OrderEvaluation.risk_tier.in_(["HIGH", "CRITICAL"]),
            )
        ) or 0

        # Active NDR cases
        active_ndr_count = session.scalar(
            select(func.count(NDRCase.id))
            .where(
                NDRCase.org_id == org_id,
                NDRCase.status.in_(["OPEN", "IN_PROGRESS", "REATTEMPT_SCHEDULED"]),
            )
        ) or 0

        return {
            "total_orders": total_orders,
            "total_gmv": Decimal(str(total_gmv)),
            "expected_contribution": Decimal(str(ec_sum)),
            "realized_contribution": Decimal(str(rc_sum)),
            "high_risk_count": high_risk_count,
            "active_ndr_count": active_ndr_count,
            "status_breakdown": status_breakdown,
            "payment_method_breakdown": payment_method_breakdown,
        }

