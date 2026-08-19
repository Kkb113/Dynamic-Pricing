from __future__ import annotations

import pandas as pd

from decisioning.business_selector import select_business_candidates


def _surface(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_augmented_selection_excludes_ineligible_high_gp_candidate():
    result = select_business_candidates(_surface([
        {"PricingDecisionID": "D1", "CurrentPrice": 100.0, "CandidatePrice": 100.0, "candidate_rank_by_price": 0, "expected_gross_profit": 10.0, "passes_all_pricing_rules": True},
        {"PricingDecisionID": "D1", "CurrentPrice": 100.0, "CandidatePrice": 110.0, "candidate_rank_by_price": 1, "expected_gross_profit": 20.0, "passes_all_pricing_rules": True},
        {"PricingDecisionID": "D1", "CurrentPrice": 100.0, "CandidatePrice": 120.0, "candidate_rank_by_price": 2, "expected_gross_profit": 100.0, "passes_all_pricing_rules": False},
    ]))
    assert result.loc[0, "CandidatePrice"] == 110.0
    assert bool(result.loc[0, "passes_all_pricing_rules"])


def test_augmented_selection_reuses_materiality_and_closest_price_tie_policy():
    material = select_business_candidates(_surface([
        {"PricingDecisionID": "D1", "CurrentPrice": 100.0, "CandidatePrice": 100.0, "candidate_rank_by_price": 0, "expected_gross_profit": 10.0, "passes_all_pricing_rules": True},
        {"PricingDecisionID": "D1", "CurrentPrice": 100.0, "CandidatePrice": 110.0, "candidate_rank_by_price": 1, "expected_gross_profit": 10.04, "passes_all_pricing_rules": True},
    ]))
    assert material.loc[0, "selection_status"] == "KEEP_CURRENT_NO_MATERIAL_UPLIFT"
    assert material.loc[0, "CandidatePrice"] == 100.0

    tied = select_business_candidates(_surface([
        {"PricingDecisionID": "D2", "CurrentPrice": 100.0, "CandidatePrice": 100.0, "candidate_rank_by_price": 0, "expected_gross_profit": 10.0, "passes_all_pricing_rules": True},
        {"PricingDecisionID": "D2", "CurrentPrice": 100.0, "CandidatePrice": 105.0, "candidate_rank_by_price": 1, "expected_gross_profit": 20.0, "passes_all_pricing_rules": True},
        {"PricingDecisionID": "D2", "CurrentPrice": 100.0, "CandidatePrice": 110.0, "candidate_rank_by_price": 2, "expected_gross_profit": 20.01, "passes_all_pricing_rules": True},
    ]))
    assert tied.loc[0, "CandidatePrice"] == 105.0
