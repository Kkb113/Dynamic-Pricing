from __future__ import annotations

import pandas as pd
import pytest

from inventory_policy.inventory_policy import assert_historical_policy_safe
from phase7.validation import validate_decision_frame


def test_historical_inventory_rejection():
    with pytest.raises(ValueError, match="HISTORICAL_INVENTORY_LEAKAGE"):
        assert_historical_policy_safe(pd.DataFrame({"InventorySnapshotDate": [pd.Timestamp("2025-12-31")], "AvailableQty": [1], "inventory_constraint_applied": [True]}))


def test_advisory_only_and_outcome_blind_schema():
    columns = [
        "PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "Channel", "CategoryID", "CurrentPrice", "BasePrice", "CostPrice", "Phase6ModelOptimalCandidatePrice", "FinalRecommendedPrice", "FinalAction", "PricingRuleID", "effective_price_floor", "effective_price_ceiling", "passes_all_pricing_rules", "PromotionAction", "MarkdownAction", "inventory_constraint_applied", "InventorySnapshotDate", "AvailableQty", "StockStatus", "expected_units", "expected_revenue", "expected_gross_profit", "manual_review_flag", "ADVISORY_ONLY", "AUTO_WRITEBACK",
    ]
    frame = pd.DataFrame([{column: None for column in columns}])
    frame.loc[0, ["PricingDecisionID", "FinalAction", "passes_all_pricing_rules", "inventory_constraint_applied", "manual_review_flag", "ADVISORY_ONLY", "AUTO_WRITEBACK"]] = ["D1", "HOLD_PRICE", True, False, False, True, False]
    validate_decision_frame(frame, mode="HISTORICAL_POLICY_MODE")
    assert frame.loc[0, "ADVISORY_ONLY"] is True
