from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.quantity_estimator import load_quantity_estimator
from optimization.candidate_simulator import OUTCOME_COLUMNS, load_outcome_blind_context
from phase6 import runner


def test_official_quantity_estimator_is_constant_mean():
    root = Path(__file__).resolve().parents[2]
    estimator = load_quantity_estimator(root / "artifacts/phase5/models/quantity_estimator_metadata.json", mean_path=root / "artifacts/phase5/models/conditional_quantity_mean.json")
    frame = pd.DataFrame({"AppliedPrice": [1.0, 2.0]})
    assert estimator.estimator_type == "CONSTANT_MEAN"
    assert np.allclose(estimator.predict_conditional_quantity(frame), 1.3057971014492753)


def test_outcome_blind_context_drops_forbidden_columns():
    frame = pd.DataFrame({"CurrentPrice": [10.0], "PurchasedFlag": [1], "QuantityPurchased": [2], "ActualRevenue": [20.0], "OutcomeTime": [pd.Timestamp("2025-01-01")], "OrderLineID": ["L1"]})
    blind = load_outcome_blind_context(frame)
    assert not OUTCOME_COLUMNS.intersection(blind.columns)


def test_cost_price_is_not_an_approved_model_feature():
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "artifacts/phase4/frozen_model_spec.json").read_text())
    assert "CostPrice" not in payload["ordered_feature_names"]


def test_test_optimizer_context_allowlist_is_outcome_free():
    root = Path(__file__).resolve().parents[2]
    contract = runner.load_contract(root / "contracts/phase2_feature_contract_v1.yaml")
    phase4_spec = json.loads((root / "artifacts/phase4/frozen_model_spec.json").read_text())
    phase5_metadata = json.loads((root / "artifacts/phase5/models/quantity_estimator_metadata.json").read_text())
    frame = pd.read_parquet(root / "artifacts/phase2/feature_dataset.parquet")
    assignments = pd.read_parquet(root / "artifacts/phase3/split_assignments.parquet")
    columns = runner._optimizer_context_columns(frame, phase4_spec, phase5_metadata)
    test_context = runner._split(frame.loc[:, columns], assignments, "test")
    assert not OUTCOME_COLUMNS.intersection(test_context.columns)
    assert "CostPrice" not in columns
    assert contract["features"]


def test_high_response_guard_usage_uses_adjusted_decision_rate():
    timings = [{"safety_summary": {"adjusted_decision_rate": 0.30, "raw_vs_safe_recommendation_change_rate": 0.01}}]
    assert runner._high_response_guard_usage(timings)
