"""Pydantic schemas for Order Financial Reconciliation and Realized Contribution."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class FinancialReconciliationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    order_id: UUID
    external_order_id: str
    terminal_status: str
    order_value: Decimal
    collected_revenue: Decimal
    cogs: Decimal
    forward_shipping_cost: Decimal
    reverse_shipping_cost: Decimal
    payment_fee: Decimal
    packaging_cost: Decimal
    inventory_damage_cost: Decimal
    pre_dispatch_intervention_cost: Decimal
    ndr_recovery_intervention_cost: Decimal
    realized_contribution: Decimal
    expected_contribution: Optional[Decimal] = None
    variance_ec_vs_rc: Optional[Decimal] = None
    reconciliation_status: str
    accounting_notes: Optional[str] = None
    reconciled_at: datetime
    created_at: datetime
