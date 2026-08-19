from __future__ import annotations

import pandas as pd

from phase8.outcome_validation import attach_observed_economics


def test_static_cost_observed_gross_profit():
    outcomes = pd.DataFrame([{ "PricingDecisionID": "PDL1", "AppliedPrice": 100.0, "QuantityPurchased": 2, "ActualRevenue": 200.0 }])
    costs = pd.DataFrame([{ "PricingDecisionID": "PDL1", "CostPrice": 60.0 }])
    result = attach_observed_economics(outcomes, costs)
    assert result.loc[0, "ObservedGrossProfit"] == 80.0
    assert result.loc[0, "ObservedGrossProfit_formula_check"] == 80.0
