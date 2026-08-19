from __future__ import annotations

import pandas as pd

from phase8.outcome_validation import audit_outcome_quality, revenue_consistency_audit, validate_outcome_join


def _outcomes() -> pd.DataFrame:
    return pd.DataFrame([
        {"PricingDecisionID": "PDL1", "PurchasedFlag": 0, "QuantityPurchased": 0, "ActualRevenue": 0.0, "AppliedPrice": 100.0},
        {"PricingDecisionID": "PDL2", "PurchasedFlag": 1, "QuantityPurchased": 2, "ActualRevenue": 200.0, "AppliedPrice": 100.0},
    ])


def test_one_to_one_outcome_join_passes():
    result = validate_outcome_join(_outcomes(), ["PDL1", "PDL2"], expected_rows=2)
    assert result["one_to_one"] is True


def test_duplicate_and_missing_outcome_rejected():
    frame = pd.concat([_outcomes(), _outcomes().iloc[[0]]], ignore_index=True)
    result = validate_outcome_join(frame, ["PDL1", "PDL2"], expected_rows=2)
    assert result["duplicate_ids"] == 1
    assert result["one_to_one"] is False


def test_quality_rejects_invalid_rows():
    frame = _outcomes()
    frame.loc[0, "QuantityPurchased"] = -1
    frame.loc[1, "ActualRevenue"] = -2
    result = audit_outcome_quality(frame)
    assert result["status"] == "BLOCKED"


def test_nonpurchase_positive_values_are_contradictions():
    frame = _outcomes()
    frame.loc[0, "QuantityPurchased"] = 1
    frame.loc[0, "ActualRevenue"] = 100
    result = audit_outcome_quality(frame)
    assert result["contradictory_rows"] == 2


def test_revenue_consistency_is_cent_exact():
    assert revenue_consistency_audit(_outcomes())["exact_cent_match_rate"] == 1.0
