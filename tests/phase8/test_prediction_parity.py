from __future__ import annotations

import pandas as pd

from phase8.scenario_evaluation import automatic_scenario_summaries, scenario_delta, scenario_prices, score_scenarios


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


def test_automatic_scenario_summaries_use_identical_s3_cohort():
    rows = []
    for identifier, automatic in (("D1", True), ("D2", False)):
        row = {"PricingDecisionID": identifier}
        for scenario, price, gp in (
            ("S0_HISTORICAL_APPLIED", 100.0, 40.0),
            ("S1_CURRENT_PRICE", 100.0, 40.0),
            ("S2_PHASE6_MODEL_OPTIMAL", 110.0, 50.0),
            ("S4_PHASE7_WITH_HISTORICAL_FALLBACK", 110.0 if automatic else 100.0, 50.0 if automatic else 40.0),
        ):
            row[f"{scenario}_price"] = price
            row[f"{scenario}_expected_units"] = 1.0
            row[f"{scenario}_expected_revenue"] = price
            row[f"{scenario}_expected_gross_profit"] = gp
        row["S3_PHASE7_FINAL_AUTOMATIC_price"] = 110.0 if automatic else None
        row["S3_PHASE7_FINAL_AUTOMATIC_expected_units"] = 1.0 if automatic else None
        row["S3_PHASE7_FINAL_AUTOMATIC_expected_revenue"] = 110.0 if automatic else None
        row["S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit"] = 50.0 if automatic else None
        rows.append(row)
    summaries = automatic_scenario_summaries(pd.DataFrame(rows))
    assert {value["rows"] for value in summaries.values()} == {1}
    assert scenario_delta(summaries, "S3_PHASE7_FINAL_AUTOMATIC")["expected_gross_profit_delta_pct"] == 0.25
