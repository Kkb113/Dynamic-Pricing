from __future__ import annotations

import pandas as pd

from phase8.boundary_analysis import actual_boundary_rates, exact_boundary_candidates, neighbor_fragility


def _surface():
    return pd.DataFrame([
        {"PricingDecisionID": "PDL1", "CandidatePrice": 90.0, "expected_gross_profit": 10.0},
        {"PricingDecisionID": "PDL1", "CandidatePrice": 100.0, "expected_gross_profit": 12.0},
        {"PricingDecisionID": "PDL1", "CandidatePrice": 110.0, "expected_gross_profit": 12.01},
    ])


def test_boundary_rate_uses_grid_min_max_not_price_change():
    surface = _surface()
    recommendations = pd.DataFrame([{ "PricingDecisionID": "PDL1", "ModelOptimalCandidatePrice": 110.0 }])
    decisions = pd.DataFrame([{ "PricingDecisionID": "PDL1", "FinalRecommendedPrice": 110.0 }])
    result = actual_boundary_rates(surface, recommendations, decisions)
    assert result["phase7_upper_grid_boundary_rate"] == 1.0


def test_exact_boundary_candidate_is_in_support_and_not_on_grid():
    surface = _surface()
    decisions = pd.DataFrame([{ "PricingDecisionID": "PDL1", "effective_price_floor": 91.0, "effective_price_ceiling": 109.0, "FinalRecommendedPrice": 100.0 }])
    result = exact_boundary_candidates(surface, decisions)
    assert set(result["boundary_price"]) == {91.0, 109.0}


def test_neighbor_fragility_selects_next_lower_candidate():
    surface = _surface()
    decisions = pd.DataFrame([{ "PricingDecisionID": "PDL1", "FinalRecommendedPrice": 110.0 }])
    boundary = pd.DataFrame([{ "PricingDecisionID": "PDL1", "phase7_upper_boundary": True }])
    result, stats = neighbor_fragility(surface, decisions, boundary)
    assert result.loc[0, "next_lower_candidate_price"] == 100.0
    assert stats["rows"] == 1
