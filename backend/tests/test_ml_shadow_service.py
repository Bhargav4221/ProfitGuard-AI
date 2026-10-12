"""
test_ml_shadow_service.py
Phase 2: Comprehensive Unit & Integration Tests for ML Shadow Serving Readiness.

Verifies:
1. Artifact loading in a clean process and schema validation.
2. INSUFFICIENT_DATA behavior.
3. RULE_BASED_FALLBACK behavior on missing or corrupt artifacts.
4. ML_PREDICTION behavior with synthetic provenance tags.
5. Invariance of the 5-action decision engine under shadow evaluation.
"""

from decimal import Decimal
from pathlib import Path
import pytest
from uuid import uuid4

from app.models.order import Order
from app.services.ml_shadow_service import MLShadowService, ml_shadow_service
from app.services.decision_engine import DecisionEngineService
from app.models.merchant_economics import MerchantEconomics


def test_artifact_loading_clean_process():
    """Verifies that the serialized model artifact loads cleanly with expected schema and features."""
    service = MLShadowService()
    assert service.is_ready(), f"Service failed to load artifact: {service._load_error}"
    
    meta = service.get_metadata()
    assert meta["status"] == "LOADED"
    assert meta["model_version"] == "v1.0.0-synthetic-dev"
    assert meta["model_type"] == "LogisticRegression"
    assert meta["data_provenance"] == "SYNTHETIC_DEVELOPMENT_ONLY"
    assert meta["is_shadow_mode"] is True
    assert meta["feature_count"] == 41
    assert "dataset_sha256" in meta and len(meta["dataset_sha256"]) == 64
    assert "thresholds" in meta


def test_insufficient_data_behavior():
    """Verifies that orders with missing or invalid fields return INSUFFICIENT_DATA."""
    service = MLShadowService()
    
    # 1. Null order
    res_null = service.predict_order_shadow(None)
    assert res_null["status"] == "INSUFFICIENT_DATA"
    assert res_null["fallback_used"] is True
    assert res_null["rto_probability"] is None

    # 2. Order missing order_value
    order_no_val = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-EMPTY-1",
        order_value=Decimal("0.00"),
        payment_method="COD"
    )
    res_no_val = service.predict_order_shadow(order_no_val)
    assert res_no_val["status"] == "INSUFFICIENT_DATA"
    assert res_no_val["fallback_used"] is True
    assert res_no_val["rto_probability"] is None

    # 3. Order missing payment_method
    order_no_pm = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-EMPTY-2",
        order_value=Decimal("1200.00"),
        payment_method=""
    )
    res_no_pm = service.predict_order_shadow(order_no_pm)
    assert res_no_pm["status"] == "INSUFFICIENT_DATA"
    assert res_no_pm["fallback_used"] is True
    assert res_no_pm["rto_probability"] is None


def test_rule_based_fallback_missing_artifact(tmp_path):
    """Verifies safe failure and RULE_BASED_FALLBACK when artifact file is absent."""
    missing_path = tmp_path / "non_existent_model.joblib"
    fallback_service = MLShadowService(artifact_path=missing_path)
    
    assert not fallback_service.is_ready()
    meta = fallback_service.get_metadata()
    assert meta["status"] == "UNAVAILABLE"
    
    valid_order = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-FALLBACK-1",
        order_value=Decimal("1500.00"),
        payment_method="COD",
        shipping_pincode="560001"
    )
    res = fallback_service.predict_order_shadow(valid_order)
    assert res["status"] == "RULE_BASED_FALLBACK"
    assert res["fallback_used"] is True
    assert res["rto_probability"] is None
    assert res["data_provenance"] == "RULE_BASED_ENGINE"


def test_rule_based_fallback_corrupt_artifact(tmp_path):
    """Verifies safe failure when artifact is invalid or corrupt."""
    corrupt_file = tmp_path / "corrupt_model.joblib"
    corrupt_file.write_bytes(b"INVALID_CORRUPT_BYTES_DATA")
    
    corrupt_service = MLShadowService(artifact_path=corrupt_file)
    assert not corrupt_service.is_ready()
    
    valid_order = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-CORRUPT-1",
        order_value=Decimal("1500.00"),
        payment_method="COD",
        shipping_pincode="560001"
    )
    res = corrupt_service.predict_order_shadow(valid_order)
    assert res["status"] == "RULE_BASED_FALLBACK"
    assert res["fallback_used"] is True
    assert res["rto_probability"] is None


def test_ml_prediction_provenance_and_metadata():
    """Verifies that a valid order generates ML_PREDICTION with complete provenance."""
    service = MLShadowService()
    valid_order = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-PREDICT-1",
        order_value=Decimal("2499.00"),
        payment_method="COD",
        shipping_pincode="560038"
    )
    res = service.predict_order_shadow(valid_order)
    assert res["status"] == "ML_PREDICTION"
    assert res["fallback_used"] is False
    assert isinstance(res["rto_probability"], float)
    assert 0.0 <= res["rto_probability"] <= 1.0
    assert res["predicted_risk_tier"] in {"LOW", "MEDIUM", "HIGH"}
    assert res["is_shadow_mode"] is True
    assert res["model_version"] == "v1.0.0-synthetic-dev"
    assert res["data_provenance"] == "SYNTHETIC_DEVELOPMENT_ONLY"
    assert "dataset_sha256" in res
    assert "shadow_governance_notice" in res


def test_decision_engine_shadow_integration_invariance(db_session, create_org, create_user):
    """Verifies that decision engine attaches shadow prediction without mutating financial decisions."""
    org = create_org(name="Shadow Test Org")
    user = create_user(email="shadow_tester@example.com")
    
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.default_cogs_percent = Decimal("30.00")
    econ.forward_shipping_cost = Decimal("70.00")
    econ.reverse_shipping_cost = Decimal("65.00")
    econ.packaging_cost = Decimal("20.00")
    econ.cod_carrier_fee = Decimal("35.00")
    econ.allow_auto_cancel = False
    db_session.commit()
    
    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="ORD-SHADOW-INV-1",
        order_value=Decimal("1500.00"),
        payment_method="COD",
        shipping_pincode="560001",
        shipping_city="Bengaluru"
    )
    db_session.add(order)
    db_session.commit()
    
    evaluation = DecisionEngineService.evaluate_order(
        order=order,
        economics=econ,
        session=db_session,
        evaluated_by_user_id=user.id
    )
    
    # 1. Decision engine core fields remain authoritative and uncorrupted
    assert evaluation.recommended_action in {"SHIP_AS_IS", "VERIFY_OTP", "INCENTIVIZE_PREPAID", "MANUAL_REVIEW", "HOLD_CANCEL"}
    assert evaluation.baseline_p_rto > Decimal("0.00")
    assert evaluation.ship_as_is_ec is not None
    assert evaluation.best_ec is not None
    
    # 2. Shadow ML prediction attached inside uncertainty disclosure
    expl = evaluation.explanation_data
    uncert = expl.get("uncertainty_disclosure", {})
    assert "shadow_ml_prediction" in uncert
    shadow = uncert["shadow_ml_prediction"]
    assert shadow["is_shadow_mode"] is True
    assert shadow["status"] in {"ML_PREDICTION", "RULE_BASED_FALLBACK", "INSUFFICIENT_DATA"}
    if shadow["status"] == "ML_PREDICTION":
        assert shadow["data_provenance"] == "SYNTHETIC_DEVELOPMENT_ONLY"


def test_feature_contract_missing_features():
    """Verifies that missing features are explicitly rejected without silent defaults."""
    from app.services.ml_feature_contract import feature_contract_validator
    
    # Incomplete dictionary missing mandatory features
    incomplete = {
        "is_cod": 1,
        "payment_type": "COD",
        # order_value is omitted!
    }
    val = feature_contract_validator.validate_features(incomplete)
    assert not val.is_valid
    assert any("order_value" in err for err in val.errors)
    assert val.sanitized_df is None


def test_feature_contract_extra_features_warning():
    """Verifies that unrecognized features generate a warning but do not break valid features."""
    from app.services.ml_feature_contract import feature_contract_validator
    from app.services.ml_shadow_service import ml_shadow_service
    
    order = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-EXTRA-FEAT",
        order_value=Decimal("1999.00"),
        payment_method="COD",
        shipping_pincode="560001"
    )
    raw = ml_shadow_service._extract_order_features(order)
    raw["unrecognized_tracking_flag"] = "UNKNOWN_METADATA"
    
    val = feature_contract_validator.validate_features(raw)
    assert val.is_valid
    assert any("unrecognized_tracking_flag" in w for w in val.warnings)
    assert "unrecognized_tracking_flag" not in val.sanitized_df.columns


def test_feature_contract_invalid_ranges():
    """Verifies that out-of-range numeric values trigger explicit validation rejection."""
    from app.services.ml_feature_contract import feature_contract_validator
    from app.services.ml_shadow_service import ml_shadow_service
    
    order = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-RANGE-ERR",
        order_value=Decimal("1999.00"),
        payment_method="COD",
        shipping_pincode="560001"
    )
    raw = ml_shadow_service._extract_order_features(order)
    raw["order_value"] = -150.0  # Illegal negative GMV
    raw["is_cod"] = 99  # Illegal non-binary flag
    
    val = feature_contract_validator.validate_features(raw)
    assert not val.is_valid
    assert any("order_value" in err for err in val.errors)
    assert any("is_cod" in err for err in val.errors)


def test_feature_contract_reordered_features_alignment():
    """Verifies that columns in non-canonical order are safely aligned to contract order."""
    import pandas as pd
    from app.services.ml_feature_contract import feature_contract_validator
    from app.services.ml_shadow_service import ml_shadow_service
    
    order = Order(
        id=uuid4(),
        org_id=uuid4(),
        external_order_id="TEST-REORDER",
        order_value=Decimal("2500.00"),
        payment_method="COD",
        shipping_pincode="110001"
    )
    raw = ml_shadow_service._extract_order_features(order)
    
    # Scramble column keys
    keys = list(raw.keys())
    reversed_raw = {k: raw[k] for k in reversed(keys)}
    
    val = feature_contract_validator.validate_features(reversed_raw)
    assert val.is_valid
    assert val.sanitized_df.columns.tolist() == feature_contract_validator.canonical_order


def test_decision_engine_strict_invariance_across_all_shadow_states(db_session, create_org, create_user, tmp_path):
    """Proves that decision engine produces 100% identical financial decisions across ML states."""
    from unittest.mock import patch
    
    org = create_org(name="Invariance Org")
    user = create_user(email="invariance@example.com")
    econ = db_session.query(MerchantEconomics).filter_by(org_id=org.id).first()
    econ.allow_auto_cancel = False
    db_session.commit()
    
    order = Order(
        id=uuid4(),
        org_id=org.id,
        external_order_id="ORD-INV-STRICT",
        order_value=Decimal("2000.00"),
        payment_method="COD",
        shipping_pincode="560038",
        shipping_city="Bengaluru"
    )
    db_session.add(order)
    db_session.commit()
    
    # State 1: Normal working shadow ML
    eval_1 = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id)
    
    # State 2: Missing artifact (RULE_BASED_FALLBACK)
    missing_service = MLShadowService(artifact_path=tmp_path / "missing.joblib")
    with patch("app.services.ml_shadow_service.ml_shadow_service", missing_service):
        eval_2 = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id)
        
    # State 3: Corrupt artifact
    corrupt_file = tmp_path / "corrupt.joblib"
    corrupt_file.write_bytes(b"CORRUPT")
    corrupt_service = MLShadowService(artifact_path=corrupt_file)
    with patch("app.services.ml_shadow_service.ml_shadow_service", corrupt_service):
        eval_3 = DecisionEngineService.evaluate_order(order=order, economics=econ, session=db_session, evaluated_by_user_id=user.id)

    # Assert exact numerical and structural invariance
    for e in [eval_2, eval_3]:
        assert e.recommended_action == eval_1.recommended_action
        assert e.baseline_p_rto == eval_1.baseline_p_rto
        assert e.ship_as_is_ec == eval_1.ship_as_is_ec
        assert e.best_ec == eval_1.best_ec
        assert e.profit_at_risk == eval_1.profit_at_risk
        assert len(e.comparison_data) == len(eval_1.comparison_data)
        for act1, act_other in zip(eval_1.comparison_data, e.comparison_data):
            assert act1["action"] == act_other["action"]
            assert act1["expected_contribution"] == act_other["expected_contribution"]
            assert act1["lift_vs_ship_as_is"] == act_other["lift_vs_ship_as_is"]

