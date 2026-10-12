"""Pydantic Schemas for Order Decision Engine & 5-Action Evaluation."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionEvaluation(BaseModel):
    action: str = Field(..., description="SHIP_AS_IS | VERIFY_OTP | INCENTIVIZE_PREPAID | MANUAL_REVIEW | HOLD_CANCEL")
    expected_contribution: Decimal = Field(..., description="EC(a) in ₹")
    lift_vs_ship_as_is: Decimal = Field(..., description="EC(a) - EC(SHIP_AS_IS) in ₹")
    intervention_cost: Decimal = Field(..., description="Pre-dispatch intervention expense deducted once")
    probabilities: Dict[str, Any] = Field(default_factory=dict)
    terminal_payoffs: Dict[str, Any] = Field(default_factory=dict)
    is_recommended: bool = False
    is_policy_eligible: bool = True
    disqualification_reason: Optional[str] = None


class TriggeredRule(BaseModel):
    rule_name: str
    factor: str
    risk_delta: str
    description: str


class PolicyGuard(BaseModel):
    guard_name: str
    passed: bool
    detail: str


class DecisionExplanation(BaseModel):
    primary_reason: str
    triggered_rules: List[TriggeredRule] = Field(default_factory=list)
    policy_guards: List[PolicyGuard] = Field(default_factory=list)
    uncertainty_disclosure: Dict[str, Any] = Field(default_factory=dict)
    financial_assumptions: Dict[str, Any] = Field(default_factory=dict)
    operational_probability_assumptions: Dict[str, Any] = Field(default_factory=dict)


class OrderEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    order_id: UUID
    evaluated_at: datetime
    recommended_action: str
    recommended_action_deterministic: Optional[str] = None
    recommended_action_ml_assisted: Optional[str] = None
    decision_policy_version: Optional[str] = None
    ml_operating_mode: Optional[str] = None
    ml_decision_rationale: Optional[str] = None
    recommended_lift: Decimal
    ship_as_is_ec: Decimal
    best_ec: Decimal
    profit_at_risk: Decimal
    baseline_p_rto: Decimal
    uncertainty_score: Decimal
    risk_tier: str
    comparison_data: List[ActionEvaluation]
    explanation_data: DecisionExplanation
    decision_status: str
    selected_action: Optional[str] = None
    override_reason: Optional[str] = None
    decided_at: Optional[datetime] = None
    intervention_status: str
    intervention_notes: Optional[str] = None
    intervention_resolved_at: Optional[datetime] = None


class OrderDecisionRecordRequest(BaseModel):
    action: str = Field(..., description="Action to execute: SHIP_AS_IS | VERIFY_OTP | INCENTIVIZE_PREPAID | MANUAL_REVIEW | HOLD_CANCEL")
    override_reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        clean = v.strip().upper()
        allowed = {"SHIP_AS_IS", "VERIFY_OTP", "INCENTIVIZE_PREPAID", "MANUAL_REVIEW", "HOLD_CANCEL"}
        if clean not in allowed:
            raise ValueError(f"Invalid decision action '{v}'. Allowed actions: {', '.join(sorted(allowed))}")
        return clean


class InterventionOutcomeRequest(BaseModel):
    outcome: str = Field(
        ...,
        description="Outcome: OTP_VERIFIED | OTP_FAILED | PREPAID_CONVERTED | PREPAID_DECLINED | MANUAL_APPROVED | MANUAL_REJECTED",
    )
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str) -> str:
        clean = v.strip().upper()
        allowed = {
            "OTP_VERIFIED",
            "OTP_FAILED",
            "PREPAID_CONVERTED",
            "PREPAID_DECLINED",
            "MANUAL_APPROVED",
            "MANUAL_REJECTED",
        }
        if clean not in allowed:
            raise ValueError(f"Invalid intervention outcome '{v}'. Allowed: {', '.join(sorted(allowed))}")
        return clean
