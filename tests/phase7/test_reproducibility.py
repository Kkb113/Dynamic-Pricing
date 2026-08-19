from __future__ import annotations

import pandas as pd

from phase7.validation import reproducibility_check


def test_business_decision_reproducibility_is_exact():
    frame = pd.DataFrame([{
        "PricingDecisionID": "D1", "PricingRuleID": "R1", "RecommendedPromotionID": None,
        "MarkdownAction": "NO_MARKDOWN", "FinalRecommendedPrice": 100.0,
        "FinalAction": "HOLD_PRICE", "manual_review_flag": False,
    }])
    result = reproducibility_check(frame.copy(), frame.copy())
    assert result["status"] == "PASS"
    assert result["max_economic_delta"] == 0.0


def test_business_decision_reproducibility_compares_economics():
    first = pd.DataFrame([{
        "PricingDecisionID": "D1", "PricingRuleID": "R1", "RecommendedPromotionID": None,
        "MarkdownAction": "NO_MARKDOWN", "FinalRecommendedPrice": 100.0,
        "FinalAction": "HOLD_PRICE", "manual_review_flag": False,
        "expected_units": 1.0, "expected_revenue": 100.0, "expected_gross_profit": 40.0,
    }])
    second = first.copy()
    second.loc[0, "expected_revenue"] = 101.0
    result = reproducibility_check(first, second)
    assert result["status"] == "FAIL"
    assert result["economic_mismatches"] == 1
    assert result["max_economic_delta"] == 1.0
