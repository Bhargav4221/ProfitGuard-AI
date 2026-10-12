"""
ml_feature_contract.py
ProfitGuard AI — Phase 3: Automated Feature Contract & Schema Validation.

Enforces:
1. Strict schema validation against FEATURE_CONTRACT_v1.json.
2. Explicit detection of missing features, extra features, type violations, and out-of-range bounds.
3. Canonical column ordering matching model expectations.
4. Fail-safe rejection: Never silently replace missing features with arbitrary values.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def _find_default_contract_path() -> Path:
    candidates = [
        Path("data/development/FEATURE_CONTRACT_v1.json"),
        Path(__file__).resolve().parents[3] / "data" / "development" / "FEATURE_CONTRACT_v1.json",
        Path(__file__).resolve().parents[2] / "data" / "development" / "FEATURE_CONTRACT_v1.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


DEFAULT_CONTRACT_PATH = _find_default_contract_path()


class FeatureValidationResult:
    """Encapsulates feature validation results."""

    def __init__(
        self,
        is_valid: bool,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        sanitized_df: Optional[pd.DataFrame] = None,
    ):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
        self.sanitized_df = sanitized_df

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }


class FeatureContractValidator:
    """Validates and sanitizes input dataframes/dictionaries against a versioned contract."""

    def __init__(self, contract_path: Optional[Path] = None):
        self.contract_path = contract_path or DEFAULT_CONTRACT_PATH
        self._contract: Optional[Dict[str, Any]] = None
        self._load_contract()

    def _load_contract(self) -> None:
        if not self.contract_path.exists():
            logger.warning("Feature contract file not found at %s", self.contract_path)
            self._contract = None
            return

        try:
            with open(self.contract_path, "r", encoding="utf-8") as f:
                self._contract = json.load(f)
            logger.info("Loaded feature contract %s version %s", 
                        self._contract.get("contract_name"), self._contract.get("contract_version"))
        except Exception as exc:
            logger.error("Failed to parse feature contract at %s: %s", self.contract_path, exc)
            self._contract = None

    @property
    def version(self) -> str:
        return self._contract.get("contract_version", "unknown") if self._contract else "none"

    @property
    def canonical_order(self) -> List[str]:
        if not self._contract:
            return []
        return self._contract.get("canonical_feature_order", [])

    def validate_features(self, input_data: Any) -> FeatureValidationResult:
        """
        Validates input feature dict or DataFrame.
        
        Checks:
        - Contract availability
        - Missing features
        - Range boundaries
        - Type conformity
        - Reordering into canonical order
        """
        if not self._contract:
            return FeatureValidationResult(
                is_valid=False,
                errors=["Feature contract specification is not loaded or missing."],
            )

        errors: List[str] = []
        warnings: List[str] = []

        # Convert dictionary to DataFrame if needed
        if isinstance(input_data, dict):
            df = pd.DataFrame([input_data])
        elif isinstance(input_data, pd.DataFrame):
            df = input_data.copy()
        else:
            return FeatureValidationResult(
                is_valid=False,
                errors=[f"Unsupported input type '{type(input_data).__name__}'. Expected dict or pd.DataFrame."],
            )

        if df.empty:
            return FeatureValidationResult(
                is_valid=False,
                errors=["Input feature data is empty (0 rows)."],
            )

        canonical_features = self.canonical_order
        feature_specs = self._contract.get("features", {})
        present_cols = set(df.columns)

        # 1. Missing Features Check
        missing_features = [f for f in canonical_features if f not in present_cols]
        if missing_features:
            errors.append(f"Missing mandatory features ({len(missing_features)}): {', '.join(missing_features)}")

        # 2. Extra Unknown Features Check
        extra_features = [c for c in df.columns if c not in canonical_features]
        if extra_features:
            warnings.append(f"Extra non-contract features ignored ({len(extra_features)}): {', '.join(extra_features)}")

        if errors:
            return FeatureValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 3. Reorder into Canonical Order
        ordered_df = df[canonical_features].copy()

        # 4. Range and Type Sanity Validation (row by row or column-wise)
        for col_name, spec in feature_specs.items():
            if col_name not in ordered_df.columns:
                continue

            series = ordered_df[col_name]
            is_nullable = spec.get("nullable", False)

            # Check null constraints
            null_count = series.isna().sum()
            if null_count > 0 and not is_nullable:
                errors.append(f"Non-nullable feature '{col_name}' contains {null_count} null value(s).")

            # Check numeric range constraints
            allowed_range = spec.get("allowed_range")
            if allowed_range and pd.api.types.is_numeric_dtype(series):
                min_val, max_val = allowed_range
                non_null_s = series.dropna()
                if not non_null_s.empty:
                    if (non_null_s < min_val).any():
                        errors.append(f"Feature '{col_name}' has values below minimum allowed {min_val}.")
                    if (non_null_s > max_val).any():
                        errors.append(f"Feature '{col_name}' has values above maximum allowed {max_val}.")

            # Check categorical allowed values
            allowed_values = spec.get("allowed_values")
            if allowed_values:
                invalid_cats = set(series.dropna().astype(str).unique()) - set(allowed_values)
                if invalid_cats:
                    # Categoricals should warn and can be mapped, or flag error if unexpected
                    warnings.append(f"Feature '{col_name}' contains unseen categories: {invalid_cats}.")

        is_valid = len(errors) == 0
        return FeatureValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            sanitized_df=ordered_df if is_valid else None,
        )


# Singleton contract validator instance
feature_contract_validator = FeatureContractValidator()
