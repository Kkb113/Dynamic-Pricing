from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from phase8.scenario_evaluation import guard_counterfactual_language
from phase8.bootstrap import bootstrap_intervals
from phase8.segment_analysis import segment_metrics
from phase8.validation import EvaluationFreeze


def test_small_segments_are_excluded():
    frame = pd.DataFrame([{ "PricingDecisionID": str(i), "Channel": "Web", "QuantityPurchased": 0, "historical_expected_units": 0.0, "ActualRevenue": 0.0, "historical_expected_revenue": 0.0, "ObservedGrossProfit": 0.0, "historical_expected_gross_profit": 0.0, "S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit": 0.0, "S0_HISTORICAL_APPLIED_expected_gross_profit": 0.0, "FinalRecommendedPrice": None, "AppliedPrice": 100.0, "phase7_upper_boundary": False } for i in range(99)])
    table, summary = segment_metrics(frame)
    assert table.empty
    assert summary["supported_segments"] == 0


def test_test_outcome_freeze_order(tmp_path: Path):
    freeze = EvaluationFreeze()
    with pytest.raises(RuntimeError, match="MISSING_FROZEN_EVALUATION_SPEC"):
        freeze.freeze(tmp_path / "missing.json")
    spec = tmp_path / "frozen.json"
    spec.write_text("{}", encoding="utf-8")
    freeze.freeze(spec)
    freeze.allow_test_outcomes("2026-01-01T00:00:01+00:00")
    with pytest.raises(RuntimeError, match="TEST_OUTCOMES_READ_MORE_THAN_ONCE"):
        freeze.allow_test_outcomes("2026-01-01T00:00:02+00:00")


def test_counterfactual_language_guard():
    guard_counterfactual_language("model-implied expected gross profit scenario")
    with pytest.raises(ValueError):
        guard_counterfactual_language("guaranteed uplift")


def test_bootstrap_gp_delta_uses_automatic_cohort_for_both_scenarios():
    frame = pd.DataFrame([
        {"QuantityPurchased": 1, "historical_expected_units": 1.0, "ActualRevenue": 100.0, "historical_expected_revenue": 100.0, "ObservedGrossProfit": 40.0, "historical_expected_gross_profit": 40.0, "S0_HISTORICAL_APPLIED_expected_gross_profit": 40.0, "S3_PHASE7_FINAL_AUTOMATIC_price": 110.0, "S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit": 50.0},
        {"QuantityPurchased": 1, "historical_expected_units": 1.0, "ActualRevenue": 100.0, "historical_expected_revenue": 100.0, "ObservedGrossProfit": 40.0, "historical_expected_gross_profit": 40.0, "S0_HISTORICAL_APPLIED_expected_gross_profit": 40.0, "S3_PHASE7_FINAL_AUTOMATIC_price": None, "S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit": None},
    ])
    result = bootstrap_intervals(frame, samples=20)
    assert result["intervals"]["phase7_model_implied_gp_delta_pct"]["mean"] == 0.25
