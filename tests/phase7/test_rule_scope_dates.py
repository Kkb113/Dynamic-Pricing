from __future__ import annotations

import pandas as pd

from business_rules.rule_loader import validate_pricing_rules
from business_rules.rule_resolver import resolve_pricing_rule


def test_scope_wildcards_and_specificity(rules):
    normalized = validate_pricing_rules(rules)
    context = {"PricingDecisionID": "D1", "DecisionTime": pd.Timestamp("2025-06-01"), "ProductID": "P1", "CategoryID": "C1", "StoreID": "S1", "Channel": "Web"}
    result = resolve_pricing_rule(context, normalized, policy="P3_SPECIFICITY_DESC_PRIORITY_DESC")
    assert result["PricingRuleID"] == "R_PRODUCT"
    assert result["RuleSpecificity"] == 3


def test_effective_date_boundaries(rules):
    normalized = validate_pricing_rules(rules)
    context = {"DecisionTime": pd.Timestamp("2026-01-01"), "ProductID": "P1", "CategoryID": "C1", "StoreID": "S1", "Channel": "Web"}
    result = resolve_pricing_rule(context, normalized, policy="P3_SPECIFICITY_DESC_PRIORITY_DESC")
    assert result["PricingRuleID"] == "R_PRODUCT"
    context["DecisionTime"] = pd.Timestamp("2024-12-31")
    assert resolve_pricing_rule(context, normalized)["status"] == "NO_APPLICABLE_RULE"


def test_constraint_adjustment_policy_prefers_largest_bound_change():
    rules = pd.DataFrame([
        {
            "PricingRuleID": "R_SMALL", "RuleName": "small", "ProductID": None, "CategoryID": "C1", "StoreID": None, "Channel": None,
            "MinPrice": 95.0, "MaxPrice": None, "MinMarginPct": None, "MaxDiscountPct": None, "MaxPriceChangePct": None, "Priority": 1,
            "EffectiveFrom": "2025-01-01", "EffectiveTo": None, "ActiveFlag": True,
        },
        {
            "PricingRuleID": "R_LARGE", "RuleName": "large", "ProductID": None, "CategoryID": "C1", "StoreID": None, "Channel": "Web",
            "MinPrice": None, "MaxPrice": 80.0, "MinMarginPct": None, "MaxDiscountPct": None, "MaxPriceChangePct": None, "Priority": 2,
            "EffectiveFrom": "2025-01-01", "EffectiveTo": None, "ActiveFlag": True,
        },
    ])
    context = {
        "DecisionTime": pd.Timestamp("2025-06-01"), "ProductID": "P1", "CategoryID": "C1",
        "StoreID": "S1", "Channel": "Web", "BasePrice": 100.0, "CurrentPrice": 100.0,
        "CostPrice": 50.0,
    }
    result = resolve_pricing_rule(
        context,
        rules,
        policy="P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
        reference_price=100.0,
    )
    assert result["PricingRuleID"] == "R_LARGE"
