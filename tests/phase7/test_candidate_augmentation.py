from __future__ import annotations

import pandas as pd
import pytest

from decisioning.candidate_augmentation import augment_rule_boundary_candidates


def test_boundary_candidate_requires_frozen_scorer():
    surface = pd.DataFrame([{
        "PricingDecisionID": "D1", "CurrentPrice": 100.0, "BasePrice": 100.0,
        "CandidatePrice": 100.0, "candidate_rank_by_price": 0,
        "support_low": 0.9, "support_high": 1.1,
    }])
    with pytest.raises(ValueError, match="RULE_BOUNDARY_REQUIRES_MODEL_SCORING"):
        augment_rule_boundary_candidates(surface, {"D1": {"effective_price_ceiling": 107.0}})


def test_boundary_candidate_is_scored_and_origin_is_recorded():
    surface = pd.DataFrame([{
        "PricingDecisionID": "D1", "CurrentPrice": 100.0, "BasePrice": 100.0,
        "CandidatePrice": 100.0, "candidate_rank_by_price": 0,
        "support_low": 0.9, "support_high": 1.1,
    }])
    result = augment_rule_boundary_candidates(
        surface,
        {"D1": {"effective_price_ceiling": 107.0}},
        score_candidate=lambda _row, price: {"expected_gross_profit": price - 70.0},
    )
    added = result.loc[result["CandidatePrice"].eq(107.0)].iloc[0]
    assert added["candidate_origin"] == "RULE_CEILING"
    assert added["expected_gross_profit"] == 37.0


def test_out_of_support_boundary_is_not_emitted():
    surface = pd.DataFrame([{
        "PricingDecisionID": "D1", "CurrentPrice": 100.0, "BasePrice": 100.0,
        "CandidatePrice": 100.0, "candidate_rank_by_price": 0,
        "support_low": 0.9, "support_high": 1.1,
    }])
    result = augment_rule_boundary_candidates(
        surface,
        {"D1": {"effective_price_floor": 120.0}},
        score_candidate=lambda _row, price: {"expected_gross_profit": price - 70.0},
    )
    assert result["CandidatePrice"].tolist() == [100.0]
