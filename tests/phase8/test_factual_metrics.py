from __future__ import annotations

import pandas as pd

from phase8.factual_backtest import factual_metrics


def test_factual_revenue_metrics_fixture():
    frame = pd.DataFrame([
        {"PricingDecisionID": "PDL1", "PurchasedFlag": 0, "QuantityPurchased": 0, "ActualRevenue": 0.0, "ObservedGrossProfit": 0.0, "historical_purchase_probability": 0.1, "historical_expected_units": 10.0, "historical_expected_revenue": 10.0, "historical_expected_gross_profit": 10.0},
        {"PricingDecisionID": "PDL2", "PurchasedFlag": 1, "QuantityPurchased": 1, "ActualRevenue": 100.0, "ObservedGrossProfit": 40.0, "historical_purchase_probability": 0.9, "historical_expected_units": 0.9, "historical_expected_revenue": 90.0, "historical_expected_gross_profit": 36.0},
    ])
    result = factual_metrics(frame)
    assert result["revenue"]["aggregate_observed"] == 100.0
    assert result["revenue"]["aggregate_predicted"] == 100.0
    assert result["revenue"]["mean_bias"] == 0.0
    assert result["revenue"]["mae"] == 10.0
    assert result["revenue"]["rmse"] == 10.0
    assert result["revenue"]["wape"] == 0.2
