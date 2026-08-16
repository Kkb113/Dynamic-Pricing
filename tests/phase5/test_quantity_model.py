from __future__ import annotations

import numpy as np

from models.quantity_catboost import fit_quantity_regressor, predict_quantity_raw, project_quantity
from models.quantity_data import build_quantity_feature_families, make_quantity_pool
from models.quantity_estimator import ConditionalQuantityEstimator
from models.quantity_selection import run_quantity_hpo


def test_small_catboost_regression_fixture(quantity_frame, phase2_contract):
    family = build_quantity_feature_families(phase2_contract)["QF0_CORE"]
    train = quantity_frame.iloc[:8].copy()
    validation = quantity_frame.iloc[8:14].copy()
    train.loc[train["PurchasedFlag"] == 0, "QuantityPurchased"] = 1
    validation.loc[validation["PurchasedFlag"] == 0, "QuantityPurchased"] = 1
    train["PurchasedFlag"] = 1
    validation["PurchasedFlag"] = 1
    model, _, _, _ = fit_quantity_regressor(train, validation, phase2_contract, family.feature_names, loss="RMSE", thread_count=1, iterations=12, early_stopping_rounds=3)
    raw = predict_quantity_raw(model, make_quantity_pool(validation, phase2_contract, family.feature_names))
    assert np.isfinite(raw).all()
    assert np.all(project_quantity(raw) >= 1.0)


def test_small_hpo_fixture_uses_only_three_fold_inputs(quantity_frame, phase2_contract):
    development = quantity_frame.copy()
    development["PurchasedFlag"] = 1
    development["QuantityPurchased"] = np.arange(1, len(development) + 1, dtype=float) % 3 + 1
    folds = [(np.arange(0, 8), np.arange(8, 12)), (np.arange(0, 12), np.arange(12, 15)), (np.arange(0, 15), np.arange(15, 18))]
    family = build_quantity_feature_families(phase2_contract)["QF0_CORE"]
    trials, summary, choice = run_quantity_hpo(development, folds, phase2_contract, family.feature_names, loss="RMSE", thread_count=1, n_trials=1, max_iterations=12)
    assert len(trials) == 1
    assert summary["completed_trials"] == 1
    assert "parameters" in choice


def test_constant_estimator_serializable_surface(quantity_frame, phase2_contract):
    estimator = ConditionalQuantityEstimator("CONSTANT_MEAN", mean_value=1.25, contract=phase2_contract, feature_names=(), minimum=1.0)
    assert np.allclose(estimator.predict_conditional_quantity(quantity_frame), 1.25)
    assert estimator.metadata()["estimator_type"] == "CONSTANT_MEAN"

