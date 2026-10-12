"""Pydantic Schemas for Real-Order Outcome Tracking and Monitoring."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class OrderOutcomeOut(BaseModel):
    id: UUID
    org_id: UUID
    order_id: UUID
    external_order_id: str

    evaluation_id: Optional[UUID] = None
    reconciliation_id: Optional[UUID] = None

    # Prediction-time model state
    model_version: Optional[str] = None
    feature_contract_version: Optional[str] = None
    prediction_timestamp: Optional[datetime] = None
    prediction_feature_ref: Optional[str] = None
    prediction_features_snapshot: Optional[Dict[str, Any]] = None
    predicted_p_rto: Optional[Decimal] = None
    predicted_risk_tier: Optional[str] = None

    # Policy & Decision
    deterministic_recommendation: str
    ml_assisted_recommendation: Optional[str] = None
    final_recommendation: Optional[str] = None
    ml_operating_mode: Optional[str] = None
    decision_policy_version: Optional[str] = None
    merchant_approved_action: Optional[str] = None
    intervention_status: str
    intervention_cost: Decimal

    # Terminal Outcome
    final_delivery_outcome: str
    carrier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    delivered_at: Optional[datetime] = None
    rto_reason_code: Optional[str] = None
    rto_reason_description: Optional[str] = None

    # Realized Financials
    realized_order_value: Decimal
    realized_collected_revenue: Decimal
    realized_cogs: Decimal
    realized_shipping_cost: Decimal
    realized_damage_cost: Decimal
    realized_rto_loss: Decimal
    realized_contribution: Decimal
    expected_contribution: Optional[Decimal] = None
    variance_ec_vs_rc: Optional[Decimal] = None

    recorded_at: datetime
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderOutcomeListOut(BaseModel):
    items: List[OrderOutcomeOut]
    total: int
    limit: int
    offset: int


class OutcomeRecordRequest(BaseModel):
    notes: Optional[str] = Field(default=None, description="Optional operator notes for outcome tracking")


class ClassificationMetrics(BaseModel):
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    evaluation_basis: str


class ObservedRealizedFacts(BaseModel):
    eligible_completed_orders_count: int
    outcome_records_count: int
    outcome_coverage_pct: float
    delivered_count: int
    rto_count: int
    cancelled_count: int
    observed_rto_rate_pct: float
    predictions_evaluated_count: int
    prediction_coverage_pct: float
    intervention_acceptance_rate_pct: float

    # Verified Cash & Loss Totals
    total_realized_revenue_inr: Decimal
    total_realized_cogs_inr: Decimal
    total_realized_shipping_inr: Decimal
    total_realized_damage_inr: Decimal
    total_realized_rto_loss_inr: Decimal
    total_realized_intervention_cost_inr: Decimal
    total_realized_net_contribution_inr: Decimal

    # Empirical Classification Performance
    classification_performance: ClassificationMetrics


class ModeledExAnteEstimates(BaseModel):
    total_expected_contribution_inr: Optional[Decimal] = None
    variance_realized_vs_expected_inr: Optional[Decimal] = None
    mean_predicted_p_rto: Optional[float] = None
    counterfactual_disclaimer: str
    counterfactual_scenarios: Dict[str, Any]


class OutcomeMonitoringMetricsOut(BaseModel):
    org_id: UUID
    generated_at: datetime
    time_window: Dict[str, Optional[str]]
    observed_realized_facts: ObservedRealizedFacts
    modeled_ex_ante_estimates: ModeledExAnteEstimates
