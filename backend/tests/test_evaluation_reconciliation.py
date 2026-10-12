"""
test_evaluation_reconciliation.py
Phase 3.1: Automated Regression Tests for Reconciled ML Metrics and Financial Calculations.

Verifies:
1. Dataset identity, integrity, and SHA-256 hash.
2. Model artifact package integrity and metadata contract.
3. Chronological holdout Random Forest metrics reconciliation (100 flagged, 26 TP, 74 FP at tau*=0.18).
4. Serving artifact Logistic Regression metrics reconciliation (84 flagged, 29 TP, 55 FP at tau=0.18).
5. Exact financial payoff and break-even calculations across Policies 1, 2, 3A, and 3B.
6. Absolute invariance of the 5-action decision engine under shadow evaluation.
"""

import sys
import types
from pathlib import Path
from decimal import Decimal
import json
import hashlib
from uuid import uuid4
import pytest
import numpy as np
import pandas as pd

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
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.ensemble import RandomForestClassifier

from app.models.order import Order
from app.models.merchant_economics import MerchantEconomics
from app.services.decision_engine import DecisionEngineService
from app.services.ml_shadow_service import MLShadowService


def _find_path(rel_path: str) -> Path:
    candidates = [
        Path(rel_path),
        Path(__file__).resolve().parents[2] / rel_path,
        Path(__file__).resolve().parents[1] / rel_path,
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


DATASET_PATH = _find_path("data/development/rto_feature_table_sample.csv")
MODEL_PATH = _find_path("data/development/models/rto_model_v1.joblib")
ML_EVAL_PATH = _find_path("data/development/SYNTHETIC_ML_EVALUATION.json")
ECON_EVAL_PATH = _find_path("data/development/ECONOMIC_EVALUATION_REPORT.json")
FEATURES_SPEC_PATH = _find_path("data/development/upstream_artifacts/selected_features.json")

EXPECTED_DATASET_SHA256 = "d00b1c78d876c17322c7c412d8804f0ed979fde95f9b28e5231fefa4ae336b2a"


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_dataset_identity_and_integrity():
    """Confirms dataset file identity, SHA-256 hash, and row/column shape."""
    assert DATASET_PATH.exists(), f"Dataset missing at {DATASET_PATH}"
    dataset_hash = compute_file_sha256(DATASET_PATH)
    assert dataset_hash == EXPECTED_DATASET_SHA256, (
        f"Dataset hash mismatch: expected {EXPECTED_DATASET_SHA256}, got {dataset_hash}"
    )
    df = pd.read_csv(DATASET_PATH)
    assert len(df) == 1000, f"Expected 1,000 rows, got {len(df)}"
    assert "target_rto" in df.columns, "target_rto missing from columns"
    assert "order_timestamp" in df.columns, "order_timestamp missing from columns"


def test_model_artifact_package_integrity():
    """Verifies that the serialized serving package exists with valid metadata and contract."""
    assert MODEL_PATH.exists(), f"Model artifact missing at {MODEL_PATH}"
    artifact = joblib.load(MODEL_PATH)
    
    assert "pipeline" in artifact
    assert "feature_names" in artifact
    assert len(artifact["feature_names"]) == 41
    assert artifact.get("model_version") == "v1.0.0-synthetic-dev"
    assert artifact.get("model_type") == "LogisticRegression"
    assert artifact.get("dataset_sha256") == EXPECTED_DATASET_SHA256
    assert artifact.get("is_shadow_mode") is True


def test_chronological_holdout_random_forest_reconciliation():
    """
    Reconstructs strict 600/200/200 chronological train/val/test split.
    Fits preprocessors strictly on Train (600 rows).
    Verifies that Random Forest at tau*=0.18 exactly reproduces 100 flagged, 26 TP, 74 FP.
    """
    df = pd.read_csv(DATASET_PATH)
    df["order_timestamp_dt"] = pd.to_datetime(df["order_timestamp"])
    df = df.sort_values("order_timestamp_dt").reset_index(drop=True)

    with open(FEATURES_SPEC_PATH, "r") as f:
        features = json.load(f)["features"]

    X = df[features]
    y = df["target_rto"].astype(int)

    X_train, y_train = X.iloc[:600], y.iloc[:600]
    X_val, y_val = X.iloc[600:800], y.iloc[600:800]
    X_test, y_test = X.iloc[800:], y.iloc[800:]

    num_cols = X_train.select_dtypes(include=["number", "bool"]).columns.tolist()
    cat_cols = [c for c in features if c not in num_cols]

    preprocessor = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), num_cols),
        ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), cat_cols)
    ])

    rf = Pipeline([
        ("preprocessor", preprocessor),
        ("clf", RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42))
    ])
    rf.fit(X_train, y_train)

    test_probs = rf.predict_proba(X_test)[:, 1]
    preds = (test_probs >= 0.18).astype(int)

    tp = int(((preds == 1) & (y_test == 1)).sum())
    fp = int(((preds == 1) & (y_test == 0)).sum())
    fn = int(((preds == 0) & (y_test == 1)).sum())
    tn = int(((preds == 0) & (y_test == 0)).sum())

    assert preds.sum() == 100, f"Expected 100 flagged orders, got {preds.sum()}"
    assert tp == 26, f"Expected 26 true positives, got {tp}"
    assert fp == 74, f"Expected 74 false positives, got {fp}"
    assert fn == 11, f"Expected 11 false negatives, got {fn}"
    assert tn == 89, f"Expected 89 true negatives, got {tn}"

    # Verify matching with SYNTHETIC_ML_EVALUATION.json
    with open(ML_EVAL_PATH, "r") as f:
        ml_eval = json.load(f)
    rf_eval = ml_eval["models_evaluated"]["Random Forest (Full)"]["validation_tuned_threshold_eval"]
    assert rf_eval["predicted_positive_count"] == 100
    assert rf_eval["confusion_matrix"] == [[89, 74], [11, 26]]
    assert round(rf_eval["recall"], 4) == 0.7027
    assert round(rf_eval["precision"], 4) == 0.2600


def test_serving_artifact_logistic_regression_reconciliation():
    """
    Loads rto_model_v1.joblib (Logistic Regression trained on full sample).
    Verifies that evaluation across the 200 holdout test orders at tau=0.18
    exactly reproduces 84 flagged, 29 TP, 55 FP.
    """
    artifact = joblib.load(MODEL_PATH)
    pipeline = artifact["pipeline"]
    features = artifact["feature_names"]

    df = pd.read_csv(DATASET_PATH)
    df["order_timestamp_dt"] = pd.to_datetime(df["order_timestamp"])
    df = df.sort_values("order_timestamp_dt").reset_index(drop=True)
    test_df = df.iloc[800:].copy().reset_index(drop=True)

    X_test = test_df[features]
    y_test = test_df["target_rto"].astype(int).values

    probs = pipeline.predict_proba(X_test)[:, 1]
    preds = (probs >= 0.18).astype(int)

    tp = int(((preds == 1) & (y_test == 1)).sum())
    fp = int(((preds == 1) & (y_test == 0)).sum())
    fn = int(((preds == 0) & (y_test == 1)).sum())
    tn = int(((preds == 0) & (y_test == 0)).sum())

    assert preds.sum() == 84, f"Expected 84 flagged orders, got {preds.sum()}"
    assert tp == 29, f"Expected 29 true positives, got {tp}"
    assert fp == 55, f"Expected 55 false positives, got {fp}"
    assert fn == 8, f"Expected 8 false negatives, got {fn}"
    assert tn == 108, f"Expected 108 true negatives, got {tn}"

    # Verify matching with ECONOMIC_EVALUATION_REPORT.json Policy 3A
    with open(ECON_EVAL_PATH, "r") as f:
        econ_eval = json.load(f)
    p3a = econ_eval["policy_comparison"]["Policy_3A_Serving_Artifact_Package"]
    assert p3a["flagged_orders"] == 84
    assert p3a["true_positives_captured"] == 29
    assert p3a["false_positives_flagged"] == 55
    assert p3a["missed_rtos_fn"] == 8
    assert p3a["true_negatives_tn"] == 108
    assert round(p3a["recall_pct"], 2) == 78.38
    assert round(p3a["precision_pct"], 2) == 34.52


def test_financial_simulation_metrics_integrity():
    """
    Independently recomputes merchant economics payoffs, OTP expenses,
    false-positive drop-off friction, and break-even effectiveness.
    """
    df = pd.read_csv(DATASET_PATH)
    df["order_timestamp_dt"] = pd.to_datetime(df["order_timestamp"])
    df = df.sort_values("order_timestamp_dt").reset_index(drop=True)
    test_df = df.iloc[800:].copy().reset_index(drop=True)
    y_test = test_df["target_rto"].astype(int).values

    COGS_PCT = 0.30
    FWD_SHIPPING = 70.0
    REV_SHIPPING = 65.0
    PACKAGING = 20.0
    COD_FEE = 35.0
    DAMAGE_RATE = 0.05
    OTP_COST = 0.50

    base_payoffs = []
    rto_losses = []
    for i in range(len(test_df)):
        v = float(test_df["order_value"].iloc[i])
        cogs = COGS_PCT * v
        is_cod = int(test_df["is_cod"].iloc[i])
        if y_test[i] == 0:
            if is_cod:
                margin = v - cogs - FWD_SHIPPING - PACKAGING - COD_FEE
            else:
                gw_fee = 0.02 * v + 3.0
                margin = v - cogs - FWD_SHIPPING - PACKAGING - gw_fee
            base_payoffs.append(margin)
            rto_losses.append(0.0)
        else:
            damage = DAMAGE_RATE * cogs
            loss = FWD_SHIPPING + REV_SHIPPING + PACKAGING + damage
            base_payoffs.append(-loss)
            rto_losses.append(loss)

    unmitigated_net = round(sum(base_payoffs), 2)
    unmitigated_rto_loss = round(sum(rto_losses), 2)
    total_gmv = round(float(test_df["order_value"].sum()), 2)

    assert total_gmv == 810509.51
    assert unmitigated_net == 438625.48
    assert unmitigated_rto_loss == 7754.81

    # Verify Policy 1 (Rules)
    rule_flagged = 0
    rule_cost = 0.0
    rule_prev_loss = 0.0
    for i in range(len(test_df)):
        v = float(test_df["order_value"].iloc[i])
        is_cod = int(test_df["is_cod"].iloc[i])
        if is_cod and (v >= 2000.0 or test_df["customer_location_tier"].iloc[i] == "Tier_3_Rural"):
            rule_flagged += 1
            rule_cost += OTP_COST
            if y_test[i] == 1:
                rule_prev_loss += 0.10 * rto_losses[i]

    assert rule_flagged == 43
    assert round(rule_cost, 2) == 21.50
    assert round(rule_prev_loss, 2) == 185.09
    assert round(rule_prev_loss - rule_cost, 2) == 163.59

    # Verify Policy 3A Break-Even (Serving Package: 84 flagged, 29 TP, 55 FP)
    artifact = joblib.load(MODEL_PATH)
    probs_art = artifact["pipeline"].predict_proba(test_df[artifact["feature_names"]])[:, 1]
    preds_art = (probs_art >= 0.18).astype(int)
    tp_art = [i for i in range(len(preds_art)) if preds_art[i] == 1 and y_test[i] == 1]
    fp_art = [i for i in range(len(preds_art)) if preds_art[i] == 1 and y_test[i] == 0]

    otp_art = len(preds_art.nonzero()[0]) * OTP_COST
    fp_fric_art = sum(base_payoffs[i] * 0.01 for i in fp_art)
    tp_loss_art = sum(rto_losses[i] for i in tp_art)
    be_eta_art = (otp_art + fp_fric_art) / tp_loss_art

    assert round(otp_art, 2) == 42.00
    assert round(fp_fric_art, 2) == 1093.32
    assert round(tp_loss_art, 2) == 5744.48
    assert round(be_eta_art, 4) == 0.1976

    # Verify Policy 3B Break-Even (Holdout RF: 100 flagged, 26 TP, 74 FP)
    with open(ECON_EVAL_PATH, "r") as f:
        econ_eval = json.load(f)
    p3b = econ_eval["policy_comparison"]["Policy_3B_Chronological_Holdout_Random_Forest"]
    assert p3b["flagged_orders"] == 100
    assert p3b["true_positives_captured"] == 26
    assert p3b["false_positives_flagged"] == 74
    assert p3b["intervention_cost_inr"] == 50.00
    assert p3b["fp_friction_cost_inr"] == 1520.51
    assert p3b["tp_rto_loss_pool_inr"] == 4949.33
    assert p3b["break_even_effectiveness_eta"] == 0.3173


def test_shadow_mode_decision_engine_strict_invariance(db_session, create_org, create_user, tmp_path):
    """
    Verifies that the authoritative DecisionEngineService produces 100% invariant
    recommendations, baseline risks, and net expected contributions regardless of
    whether ML shadow inference is enabled, disabled, or fails schema validation.
    """
    from unittest.mock import patch

    org = create_org(name="Reconciliation Invariance Org")
    user = create_user(email="rec_invariance@example.com")
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = False
    db_session.commit()

    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="ORD-REC-INV-1",
        order_value=Decimal("3500.00"),
        payment_method="COD",
        shipping_pincode="560038",
        shipping_city="Bengaluru"
    )
    db_session.add(order)
    db_session.commit()

    # State 1: Active shadow ML service
    eval_1 = DecisionEngineService.evaluate_order(
        order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id
    )

    # State 2: Missing artifact
    missing_service = MLShadowService(artifact_path=tmp_path / "missing_rec.joblib")
    with patch("app.services.ml_shadow_service.ml_shadow_service", missing_service):
        eval_2 = DecisionEngineService.evaluate_order(
            order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id
        )

    # State 3: Corrupt artifact
    corrupt_file = tmp_path / "corrupt_rec.joblib"
    corrupt_file.write_bytes(b"CORRUPT")
    corrupt_service = MLShadowService(artifact_path=corrupt_file)
    with patch("app.services.ml_shadow_service.ml_shadow_service", corrupt_service):
        eval_3 = DecisionEngineService.evaluate_order(
            order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id
        )

    for other_eval in [eval_2, eval_3]:
        assert other_eval.recommended_action == eval_1.recommended_action
        assert other_eval.baseline_p_rto == eval_1.baseline_p_rto
        assert other_eval.ship_as_is_ec == eval_1.ship_as_is_ec
        assert other_eval.best_ec == eval_1.best_ec
        assert other_eval.profit_at_risk == eval_1.profit_at_risk
        assert len(other_eval.comparison_data) == len(eval_1.comparison_data)
        for act1, act2 in zip(eval_1.comparison_data, other_eval.comparison_data):
            assert act1["action"] == act2["action"]
            assert act1["expected_contribution"] == act2["expected_contribution"]
            assert act1["lift_vs_ship_as_is"] == act2["lift_vs_ship_as_is"]

