"""ml_inference_service.py
ProfitGuard AI — Production-Safe Live ML Inference Service (Phase 4C).

GOVERNANCE & SAFETY SPECIFICATIONS:
1. OPERATING MODES:
   - DISABLED: ML inference is bypassed entirely; returns status DISABLED with rto_probability=None.
   - SHADOW: ML executes inference and records audit prediction without altering decision policy.
   - LIVE_ASSISTED: ML executes inference and provides advisory risk probability to decision engine.
2. MODEL-READINESS GATE:
   - Synthetic-trained model (rto_model_v1.joblib) is restricted from autonomous consequential
     actions (HOLD_CANCEL). is_approved_for_consequential_actions = False.
   - Never automatically cancel orders, block customers, or impose irreversible actions solely due to ML.
3. FAIL-SAFE RESILIENCE & FEATURE VALIDATION:
   - Validates input features against FEATURE_CONTRACT_v1.json via FeatureContractValidator.
   - Cleanly handles missing/unsupported features (INSUFFICIENT_DATA) or corrupt/missing artifacts (RULE_BASED_FALLBACK).
   - Preserves strict distinction between ML failure (rto_probability is None) and genuine low-risk scores.
"""

import sys
import types
from pathlib import Path
from decimal import Decimal
from typing import Any, Dict, List, Optional
import math
import logging

# Ensure pyarrow DLL blockage does not prevent scikit-learn from importing
if "pyarrow" not in sys.modules:
    dummy_pa = types.ModuleType("pyarrow")
    class DummyType: pass
    dummy_pa.Table = DummyType
    dummy_pa.RecordBatch = DummyType
    dummy_pa.Array = DummyType
    dummy_pa.ChunkedArray = DummyType
    dummy_pa.__version__ = "0.0.0"
    sys.modules["pyarrow"] = dummy_pa

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order import Order
from app.services.ml_feature_contract import feature_contract_validator

logger = logging.getLogger(__name__)


def _find_default_artifact_path() -> Path:
    candidates = [
        Path("data/development/models/rto_model_v1.joblib"),
        Path(__file__).resolve().parents[3] / "data" / "development" / "models" / "rto_model_v1.joblib",
        Path(__file__).resolve().parents[2] / "data" / "development" / "models" / "rto_model_v1.joblib",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


DEFAULT_ARTIFACT_PATH = _find_default_artifact_path()

ALLOWED_OPERATING_MODES = {"SHADOW", "LIVE_ASSISTED", "DISABLED"}


class MLInferenceService:
    """Production-safe ML risk inference service supporting SHADOW, LIVE_ASSISTED, and DISABLED modes."""

    def __init__(self, artifact_path: Optional[Path] = None):
        self.artifact_path = artifact_path or DEFAULT_ARTIFACT_PATH
        self._artifact: Optional[Dict[str, Any]] = None
        self._load_error: Optional[str] = None
        self._runtime_mode_override: Optional[str] = None
        self._load_artifact()

    def _load_artifact(self) -> None:
        """Loads and verifies the serialized model package defensively."""
        self._artifact = None
        self._load_error = None

        if not self.artifact_path.exists():
            self._load_error = f"Model artifact not found at {self.artifact_path}"
            logger.warning(self._load_error)
            return

        try:
            payload = joblib.load(self.artifact_path)
            required_keys = ["pipeline", "feature_names", "model_version", "dataset_sha256"]
            for key in required_keys:
                if key not in payload:
                    raise ValueError(f"Corrupt artifact: missing required key '{key}'")

            if not isinstance(payload["feature_names"], list) or len(payload["feature_names"]) == 0:
                raise ValueError("Corrupt artifact: feature_names must be a non-empty list")

            self._artifact = payload
            logger.info("MLInferenceService loaded model %s (%s features)",
                        payload.get("model_version"), len(payload["feature_names"]))
        except Exception as exc:
            self._load_error = f"Failed to load model artifact: {exc}"
            logger.error(self._load_error, exc_info=True)
            self._artifact = None

    def get_operating_mode(self) -> str:
        """Returns the current ML operating mode."""
        if self._runtime_mode_override:
            return self._runtime_mode_override.upper()
        mode = getattr(settings, "ML_OPERATING_MODE", "SHADOW")
        return mode.upper() if mode else "SHADOW"

    def set_operating_mode(self, mode: str) -> None:
        """Sets a runtime operating mode override (e.g. for testing or temporary rollback)."""
        clean = (mode or "").strip().upper()
        if clean not in ALLOWED_OPERATING_MODES:
            raise ValueError(f"Invalid ML operating mode '{mode}'. Allowed: {sorted(list(ALLOWED_OPERATING_MODES))}")
        self._runtime_mode_override = clean

    def reset_operating_mode(self) -> None:
        """Clears any runtime operating mode override, returning to configuration setting."""
        self._runtime_mode_override = None

    def is_approved_for_consequential_actions(self) -> bool:
        """
        Model-Readiness Gate:
        Checks whether the active ML model is formally approved to drive consequential actions
        such as automated order cancellation (HOLD_CANCEL).
        Synthetic-trained models return False by default.
        """
        return bool(getattr(settings, "ML_MODEL_APPROVED_FOR_CONSEQUENTIAL_ACTIONS", False))

    def is_ready(self) -> bool:
        """Checks if the ML model artifact is loaded and ready for inference."""
        return self._artifact is not None

    def get_metadata(self) -> Dict[str, Any]:
        """Returns provenance, specification, and operating metadata."""
        current_mode = self.get_operating_mode()
        approved_consequential = self.is_approved_for_consequential_actions()

        if not self._artifact:
            return {
                "status": "UNAVAILABLE",
                "operating_mode": current_mode,
                "is_approved_for_consequential_actions": approved_consequential,
                "reason": self._load_error or "Artifact not loaded",
                "data_provenance": "RULE_BASED_ENGINE",
            }

        return {
            "status": "LOADED",
            "operating_mode": current_mode,
            "is_approved_for_consequential_actions": approved_consequential,
            "model_version": self._artifact.get("model_version"),
            "model_type": self._artifact.get("model_type"),
            "data_provenance": self._artifact.get("data_provenance", "SYNTHETIC_DEVELOPMENT_ONLY"),
            "dataset_sha256": self._artifact.get("dataset_sha256"),
            "feature_contract_version": feature_contract_validator.version,
            "feature_count": len(self._artifact.get("feature_names", [])),
            "thresholds": self._artifact.get("thresholds", {}),
            "readiness_notice": (
                "Synthetic development weights: approved for advisory scoring only. "
                "Consequential production actions (autonomous cancellation) are strictly blocked."
                if not approved_consequential else "Approved for consequential actions."
            ),
        }

    def extract_order_features(self, order: Order, db: Optional[Session] = None) -> Dict[str, Any]:
        """Maps an Order instance into the 41 prediction-time features expected by the model pipeline."""
        order_val = float(order.order_value) if order.order_value is not None else 0.0
        log_order_val = float(math.log1p(max(0.0, order_val)))
        pm_raw = (order.payment_method or "").strip().upper()
        is_cod = 1 if pm_raw == "COD" else 0
        if is_cod:
            payment_type = "COD"
        elif pm_raw in {"UPI", "CREDIT_CARD", "DEBIT_CARD", "WALLET"}:
            payment_type = "Credit_Card" if pm_raw == "CREDIT_CARD" else ("Debit_Card" if pm_raw == "DEBIT_CARD" else pm_raw.capitalize())
        else:
            payment_type = "UPI"

        items = list(order.items or [])
        item_line_count = len(items) if items else 1
        total_qty = sum(item.quantity for item in items) if items else 1
        avg_item_price = (order_val / total_qty) if total_qty > 0 else order_val

        pincode_str = str(order.shipping_pincode or "").strip()
        region = "West"
        location_tier = "Tier_2"
        serviceability = 0.85
        if pincode_str:
            prefix = pincode_str[:2]
            if prefix in {"11", "12", "20", "22", "30", "14"}:
                region = "North"
            elif prefix in {"40", "41", "38", "39", "44"}:
                region = "West"
            elif prefix in {"56", "60", "50", "68", "64", "53"}:
                region = "South"
            elif prefix in {"70", "80", "75", "78", "76"}:
                region = "East"
            elif prefix in {"45", "46"}:
                region = "Central"

            if pincode_str.startswith(("110", "400", "560", "600", "500", "700", "411", "380")):
                location_tier = "Metro"
                serviceability = 0.95
            elif pincode_str.startswith(("143", "753", "625", "250", "334")):
                location_tier = "Tier_3_Rural"
                serviceability = 0.65

        features: Dict[str, Any] = {
            "is_cod": is_cod,
            "payment_type": payment_type,
            "order_value": order_val,
            "log_order_value": log_order_val,
            "item_line_count": item_line_count,
            "total_quantity": total_qty,
            "unique_seller_count": 1,
            "unique_category_count": 1,
            "dominant_category": "Electronics",
            "contains_fragile_product": 0,
            "contains_premium_product": 1 if order_val >= 2500.0 else 0,
            "total_product_weight_g": 500.0 * total_qty,
            "average_item_price": avg_item_price,
            "customer_tenure_days": 30,
            "is_first_order": 1,
            "customer_prior_order_count": 0,
            "seller_tenure_days": 180,
            "customer_region": region,
            "customer_location_tier": location_tier,
            "customer_serviceability_score": serviceability,
            "is_event_period": 0,
            "event_category": "No_Event",
            "event_impact_score": 0.0,
            "customer_orders_last_30d": 0,
            "customer_orders_last_90d": 0,
            "customer_days_since_last_order": np.nan,
            "customer_prior_cod_share": np.nan,
            "customer_prior_avg_order_value": np.nan,
            "current_vs_customer_avg_value_ratio": 1.0,
            "customer_history_available": 0,
            "seller_prior_order_count": 50,
            "seller_orders_last_30d": 15,
            "seller_avg_dispatch_hours_prior_30d": 24.0,
            "seller_dispatch_hours_std_prior_30d": 4.0,
            "seller_dispatch_history_count_30d": 15,
            "seller_history_available": 1,
            "dominant_category_orders_last_30d": 100,
            "dominant_category_orders_last_90d": 300,
            "category_demand_acceleration": 1.0,
            "category_avg_order_value_prior_30d": order_val,
            "category_history_count_30d": 100,
        }
        return features

    def infer_order_risk(
        self,
        order: Order,
        db: Optional[Session] = None,
        mode_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes production-safe ML inference for an incoming or evaluated order.

        Operating modes:
        - DISABLED: Bypasses inference; returns rto_probability=None.
        - SHADOW: Executes inference; returns audit prediction.
        - LIVE_ASSISTED: Executes inference; provides advisory risk for decision engine.

        Guarantees:
        - Never throws unhandled exceptions.
        - rto_probability is None on failure, never 0.0.
        - Features validated against FEATURE_CONTRACT_v1.json.
        """
        mode = (mode_override or self.get_operating_mode()).upper()
        approved_consequential = self.is_approved_for_consequential_actions()

        # 1. Mode DISABLED
        if mode == "DISABLED":
            return {
                "status": "DISABLED",
                "operating_mode": "DISABLED",
                "is_shadow_mode": False,
                "is_approved_for_consequential_actions": approved_consequential,
                "rto_probability": None,
                "predicted_risk_tier": None,
                "fallback_used": True,
                "reason": "ML inference is disabled by configuration.",
                "data_provenance": "RULE_BASED_ENGINE",
            }

        # 2. Check for INSUFFICIENT_DATA (Order null or missing basic fields)
        if not order:
            return {
                "status": "INSUFFICIENT_DATA",
                "operating_mode": mode,
                "is_shadow_mode": (mode == "SHADOW"),
                "is_approved_for_consequential_actions": approved_consequential,
                "rto_probability": None,
                "predicted_risk_tier": None,
                "fallback_used": True,
                "reason": "Order object is null or missing.",
                "data_provenance": "RULE_BASED_ENGINE",
            }

        if order.order_value is None or float(order.order_value) <= 0 or not order.payment_method:
            return {
                "status": "INSUFFICIENT_DATA",
                "operating_mode": mode,
                "is_shadow_mode": (mode == "SHADOW"),
                "is_approved_for_consequential_actions": approved_consequential,
                "rto_probability": None,
                "predicted_risk_tier": None,
                "fallback_used": True,
                "reason": "Mandatory fields order_value or payment_method missing.",
                "data_provenance": "RULE_BASED_ENGINE",
            }

        # 3. Check for RULE_BASED_FALLBACK (artifact missing or unloadable)
        if not self._artifact or "pipeline" not in self._artifact:
            return {
                "status": "RULE_BASED_FALLBACK",
                "operating_mode": mode,
                "is_shadow_mode": (mode == "SHADOW"),
                "is_approved_for_consequential_actions": approved_consequential,
                "rto_probability": None,
                "predicted_risk_tier": None,
                "fallback_used": True,
                "reason": f"Model artifact unavailable ({self._load_error or 'not loaded'}). Using rule-based engine.",
                "model_version": None,
                "data_provenance": "RULE_BASED_ENGINE",
            }

        # 4. Feature Extraction & Schema Contract Validation
        try:
            raw_features = self.extract_order_features(order, db)
            validation = feature_contract_validator.validate_features(raw_features)
            if not validation.is_valid:
                logger.warning(
                    "Feature contract validation failed for order %s: %s",
                    getattr(order, "external_order_id", "unknown"),
                    validation.errors,
                )
                return {
                    "status": "INSUFFICIENT_DATA",
                    "operating_mode": mode,
                    "is_shadow_mode": (mode == "SHADOW"),
                    "is_approved_for_consequential_actions": approved_consequential,
                    "rto_probability": None,
                    "predicted_risk_tier": None,
                    "fallback_used": True,
                    "reason": f"Feature contract validation failed: {'; '.join(validation.errors)}",
                    "validation_errors": validation.errors,
                    "feature_contract_version": feature_contract_validator.version,
                    "model_version": self._artifact.get("model_version"),
                    "data_provenance": "RULE_BASED_ENGINE",
                }

            input_df = validation.sanitized_df
            pipeline = self._artifact["pipeline"]
            probs = pipeline.predict_proba(input_df)[0]
            p_rto = float(probs[1]) if len(probs) > 1 else float(probs[0])

            thresholds = self._artifact.get("thresholds", {})
            med_t = thresholds.get("medium_risk_threshold", 0.2178)
            high_t = thresholds.get("high_risk_threshold", 0.2826)

            if p_rto >= high_t:
                tier = "HIGH"
            elif p_rto >= med_t:
                tier = "MEDIUM"
            else:
                tier = "LOW"

            return {
                "status": "ML_PREDICTION",
                "operating_mode": mode,
                "is_shadow_mode": (mode == "SHADOW"),
                "is_approved_for_consequential_actions": approved_consequential,
                "rto_probability": round(p_rto, 4),
                "predicted_risk_tier": tier,
                "thresholds": thresholds,
                "fallback_used": False,
                "model_version": self._artifact.get("model_version"),
                "model_type": self._artifact.get("model_type"),
                "feature_contract_version": feature_contract_validator.version,
                "dataset_sha256": self._artifact.get("dataset_sha256"),
                "data_provenance": "SYNTHETIC_DEVELOPMENT_ONLY",
                "live_feature_source": "ORDER_PLACEMENT_ONLY",
                "unavailable_live_features": [
                    "seller_prior_order_count",
                    "seller_orders_last_30d",
                    "seller_dispatch_hours",
                    "dominant_category_demand_acceleration",
                    "event_impact_score",
                ],
                "readiness_notice": (
                    "Synthetic-trained model: advisory scoring only. Consequential cancellations "
                    "are blocked by model-readiness gate."
                    if not approved_consequential else "Approved for consequential actions."
                ),
                "shadow_governance_notice": (
                    "SHADOW MODE: This prediction is generated offline on synthetic development "
                    "weights for evaluation only. It does NOT modify the 5-action decision engine "
                    "or trigger automated merchant order cancellations."
                ),
            }

        except Exception as exc:
            logger.error("Exception during ML inference: %s", exc, exc_info=True)
            return {
                "status": "RULE_BASED_FALLBACK",
                "operating_mode": mode,
                "is_shadow_mode": (mode == "SHADOW"),
                "is_approved_for_consequential_actions": approved_consequential,
                "rto_probability": None,
                "predicted_risk_tier": None,
                "fallback_used": True,
                "reason": f"Inference execution exception: {exc}. Safely defaulting to rule-based engine.",
                "model_version": self._artifact.get("model_version") if self._artifact else None,
                "data_provenance": "RULE_BASED_ENGINE",
            }


# Global singleton instance
ml_inference_service = MLInferenceService()
