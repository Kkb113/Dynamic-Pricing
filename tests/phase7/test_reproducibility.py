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
