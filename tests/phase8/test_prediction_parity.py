from __future__ import annotations

import pandas as pd

from phase8.scenario_evaluation import scenario_prices, score_scenarios


class FakeFrozenScorer:
    def score_candidates(self, sources, candidate_prices):
        return [{"raw_purchase_probability": 0.25 + float(price) / 1000.0, "conditional_quantity": 2.0, "safe_expected_units": 0.5, "expected_revenue": float(price) * 0.5, "expected_gross_profit": (float(price) - 60.0) * 0.5} for price in candidate_prices]


def test_historical_applied_price_is_the_scored_candidate():
    outcomes = pd.DataFrame([{ "PricingDecisionID": "PDL1", "AppliedPrice": 100.0 }])
    recs = pd.DataFrame([{ "PricingDecisionID": "PDL1", "ModelOptimalCandidatePrice": 110.0 }])
    decisions = pd.DataFrame([{ "PricingDecisionID": "PDL1", "CurrentPrice": 95.0, "FinalRecommendedPrice": 108.0, "manual_review_flag": False }])
    prices = scenario_prices(outcomes, recs, decisions)
    result = score_scenarios(pd.DataFrame([{ "PricingDecisionID": "PDL1", "CurrentPrice": 95.0, "AppliedPrice": 100.0 }]), prices, FakeFrozenScorer())
    assert result.loc[0, "S0_HISTORICAL_APPLIED_price"] == 100.0
    assert result.loc[0, "S0_HISTORICAL_APPLIED_purchase_probability"] == 0.35
