from __future__ import annotations

from pathlib import Path

import pandas as pd

from phase8.outcome_loader import fixture_outcomes, outcome_select_sql


def test_outcome_query_is_select_only_and_scoped():
    sql = outcome_select_sql(["PDL1", "PDL2"])
    assert sql.startswith("SELECT")
    assert "PurchasedFlag" in sql
    assert "IN ('PDL1', 'PDL2')" in sql
    assert "PricingDecisionID" in sql


def test_fixture_outcomes_are_explicitly_derived_after_freeze():
    context = pd.DataFrame([{ "PricingDecisionID": "PDL1", "AppliedPrice": 100.0, "DecisionTime": pd.Timestamp("2025-01-01") }])
    result = fixture_outcomes(context)
    assert list(result.columns) == ["PricingDecisionID", "PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime", "AppliedPrice"]
