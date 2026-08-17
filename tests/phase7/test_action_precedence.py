from __future__ import annotations

from decisioning.final_decision import final_action


def test_out_of_stock_wins_over_promotion_and_markdown():
    assert final_action(
        current_price=100.0,
        final_price=None,
        inventory_status="OUT_OF_STOCK_NO_PRICE_ACTION",
        promotion_action="HONOR_ACTIVE_PROMOTION",
        markdown_action="SEASONAL_SLOW_MOVING_MARKDOWN",
    ) == "OUT_OF_STOCK_NO_PRICE_ACTION"


def test_rule_conflict_wins_over_ordinary_model_pricing():
    assert final_action(
        current_price=100.0,
        final_price=110.0,
        rule_conflict=True,
        promotion_action="NO_ACTIVE_PROMOTION",
    ) == "MANUAL_REVIEW_RULE_CONFLICT"
