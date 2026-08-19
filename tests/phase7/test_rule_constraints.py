from __future__ import annotations

from business_rules.rule_constraints import derive_rule_bounds, evaluate_candidate_constraints


def test_constraint_formulas_and_margin_example(rules):
    rule = rules.iloc[1].to_dict()
    bounds = derive_rule_bounds(rule, base_price=100, current_price=100, cost_price=70)
    assert bounds["effective_price_floor"] == 100.0
    assert bounds["effective_price_ceiling"] == 110.0
    assert evaluate_candidate_constraints(80, rule, base_price=100, current_price=100, cost_price=70)["passes_min_margin"] is False
    assert evaluate_candidate_constraints(100, rule, base_price=100, current_price=100, cost_price=70)["passes_all_pricing_rules"] is True


def test_max_discount_and_movement():
    rule = {"MinPrice": None, "MaxPrice": None, "MinMarginPct": None, "MaxDiscountPct": 20, "MaxPriceChangePct": 10}
    bounds = derive_rule_bounds(rule, base_price=100, current_price=100, cost_price=70)
    assert bounds["effective_price_floor"] == 90.0
    assert bounds["effective_price_ceiling"] == 110.0
    assert evaluate_candidate_constraints(90, rule, base_price=100, current_price=100, cost_price=70)["passes_all_pricing_rules"] is True
    assert evaluate_candidate_constraints(75, rule, base_price=100, current_price=100, cost_price=70)["passes_all_pricing_rules"] is False
