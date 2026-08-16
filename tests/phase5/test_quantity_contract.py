from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from demand.expected_units import compute_expected_units, expected_units_calibration, expected_units_metrics, observed_units
from models.quantity_catboost import project_quantity, quantity_metrics
from models.quantity_data import build_quantity_feature_families, build_quantity_model_features_for_candidate_price, prepare_quantity_catboost_frame, validate_quantity_feature_columns
from models.quantity_selection import adoption_gate, integrated_safety_gate


def test_quantity_families_are_explicit_and_leakage_free(phase2_contract):
    families = build_quantity_feature_families(phase2_contract)
    assert all(name in families for name in ["QF0_CORE", "QF1_CORE_HIGH_CARDINALITY", "QF2_CORE_COMPETITOR", "QF3_CORE_BEHAVIOR", "QF4_CORE_CUSTOMER", "QF5_CORE_HIGH_CARDINALITY_COMPETITOR", "QF6_CORE_HIGH_CARDINALITY_BEHAVIOR", "QF7_CORE_HIGH_CARDINALITY_COMPETITOR_BEHAVIOR", "QF8_CORE_ALL_APPROVED_CONTEXT", "F3_CORE_BEHAVIOR"])
    for family in families.values():
        assert "PurchasedFlag" not in family.feature_names
        assert "QuantityPurchased" not in family.feature_names
        assert "CustomerID" not in family.feature_names


def test_target_columns_are_rejected_as_predictors(phase2_contract):
    with pytest.raises(ValueError):
        validate_quantity_feature_columns(["QuantityPurchased"], phase2_contract)
    with pytest.raises(ValueError):
        validate_quantity_feature_columns(["PurchasedFlag"], phase2_contract)


def test_native_category_and_candidate_price_schema_parity(quantity_frame, phase2_contract):
    family = build_quantity_feature_families(phase2_contract)["QF3_CORE_BEHAVIOR"]
    historical = prepare_quantity_catboost_frame(quantity_frame, phase2_contract, family.feature_names)
    candidate = build_quantity_model_features_for_candidate_price(quantity_frame, quantity_frame["AppliedPrice"], phase2_contract, family.feature_names)
    numeric_delta = np.nanmax(np.abs(historical.select_dtypes(include=[np.number]).to_numpy(float) - candidate.select_dtypes(include=[np.number]).to_numpy(float)))
    assert historical.columns.tolist() == candidate.columns.tolist()
    assert numeric_delta <= 1e-10


def test_domain_projection_never_rounds():
    projected = project_quantity([0.7, 1.8, 2.25], minimum=1.0)
    assert np.allclose(projected, [1.0, 1.8, 2.25])


def test_expected_units_formula_and_support():
    probability = np.array([0.0, 0.25, 1.0])
    quantity = np.array([1.0, 1.8, 2.0])
    assert np.array_equal(compute_expected_units(probability, quantity, minimum=1.0), probability * quantity)
    with pytest.raises(ValueError):
        compute_expected_units([1.2], [1.0], minimum=1.0)


def test_observed_units_is_evaluation_only():
    assert np.array_equal(observed_units([0, 1, 1], [0, 2, 1]), [0.0, 2.0, 1.0])
    metrics = expected_units_metrics([0.0, 2.0], [0.1, 1.9])
    assert metrics["row_count"] == 2
    assert metrics["aggregate_actual_units"] == 2.0


def test_expected_units_calibration_has_deciles():
    table = expected_units_calibration(np.arange(20, dtype=float), np.arange(20, dtype=float) + 0.1, bins=10)
    assert len(table) == 10
    assert set(["mean_predicted_units", "mean_observed_units", "absolute_gap"]).issubset(table.columns)


def test_adoption_gate_falls_back_when_advanced_is_not_material():
    baseline = {"mae": 0.47, "rmse": 0.63, "mean_poisson_deviance": 0.24}
    advanced = {"mae": 0.469, "rmse": 0.629, "mean_poisson_deviance": 0.239}
    decision = adoption_gate(baseline, advanced)
    assert decision["decision"] == "CONSTANT_MEAN"
    assert decision["eligible"] is False


def test_adoption_gate_accepts_material_improvement():
    baseline = {"mae": 0.47, "rmse": 0.63, "mean_poisson_deviance": 0.24}
    advanced = {"mae": 0.45, "rmse": 0.625, "mean_poisson_deviance": 0.237}
    decision = adoption_gate(baseline, advanced)
    assert decision["decision"] == "CATBOOST"


def test_integrated_safety_gate_is_predeclared():
    mean = {"rmse": 0.5, "mean_poisson_deviance": 0.2}
    advanced = {"rmse": 0.503, "mean_poisson_deviance": 0.203}
    assert integrated_safety_gate(mean, advanced)["triggered"] is True


def test_quantity_metrics_reports_raw_floor_diagnostics():
    metrics = quantity_metrics([1.0, 2.0], [1.0, 1.8], raw=[0.7, 1.8], minimum=1.0)
    assert metrics["raw_predictions_below_minimum_count"] == 1
    assert metrics["bias"] < 0
