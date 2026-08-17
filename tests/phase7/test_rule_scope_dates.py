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
