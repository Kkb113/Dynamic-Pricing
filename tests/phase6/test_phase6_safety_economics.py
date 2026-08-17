from __future__ import annotations

import numpy as np

from optimization.economics import score_economics
from optimization.response_safety import apply_response_safety


def test_response_safety_is_low_to_high_cumulative_minimum(candidate_surface):
    safe, diagnostics = apply_response_safety(candidate_surface)
    one = safe[safe["PricingDecisionID"] == "D1"].sort_values("CandidatePrice")
    assert np.allclose(one["safe_expected_units"], [0.30, 0.28, 0.28, 0.24])
    assert np.all(np.diff(one["safe_expected_units"]) <= 1e-12)
    assert diagnostics["summary"]["raw_non_monotonic_decision_rate"] == 1.0
    assert (safe["safe_expected_units"] <= safe["raw_expected_units"] + 1e-12).all()


def test_economic_formulas(candidate_surface):
    safe, _ = apply_response_safety(candidate_surface)
    scored = score_economics(safe)
    row = scored[(scored["PricingDecisionID"] == "D1") & (scored["CandidatePrice"] == 100.0)].iloc[0]
    assert np.isclose(row["expected_revenue"], 28.0)
    assert np.isclose(row["unit_gross_profit"], 30.0)
    assert np.isclose(row["expected_gross_profit"], 8.4)
    assert np.isclose(row["candidate_margin_pct"], 0.30)
