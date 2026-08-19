"""Controlled Phase 7 action vocabulary and precedence."""

from __future__ import annotations

from typing import Any


ACTION_PRECEDENCE = (
    "INVENTORY_SAFETY",
    "RULE_SAFETY",
    "PROMOTION_COMMITMENT",
    "MARKDOWN_POLICY",
    "NORMAL_MODEL_PRICING",
)


def action_precedence(
    *,
    inventory_status: str | None,
    inventory_available: bool,
    rule_conflict: bool,
    no_compliant_candidate: bool,
    promotion_action: str,
    markdown_action: str,
    base_action: str,
) -> str:
    if not inventory_available:
        return "MANUAL_REVIEW_INVENTORY_UNAVAILABLE"
    if inventory_status == "OUT_OF_STOCK" or inventory_status == "OUT_OF_STOCK_NO_PRICE_ACTION":
        return "OUT_OF_STOCK_NO_PRICE_ACTION"
    if rule_conflict:
        return "MANUAL_REVIEW_RULE_CONFLICT"
    if no_compliant_candidate:
        return "MANUAL_REVIEW_NO_COMPLIANT_CANDIDATE"
    if promotion_action == "PROMOTION_CONFLICT_REVIEW":
        return "PROMOTION_REVIEW"
    if promotion_action == "PROMOTION_RULE_CONFLICT":
        return "PROMOTION_REVIEW"
    if promotion_action == "HONOR_ACTIVE_PROMOTION":
        return "HONOR_ACTIVE_PROMOTION"
    if markdown_action in {"SEASONAL_SLOW_MOVING_MARKDOWN", "MARKDOWN_REVIEW_REQUIRED"}:
        return markdown_action
    return base_action


def final_action(
    *,
    current_price: float,
    final_price: float | None,
    inventory_status: str | None = None,
    inventory_available: bool = True,
    rule_conflict: bool = False,
    no_compliant_candidate: bool = False,
    promotion_action: str = "NO_ACTIVE_PROMOTION",
    markdown_action: str = "NO_MARKDOWN",
) -> str:
    if final_price is None:
        return action_precedence(
            inventory_status=inventory_status,
            inventory_available=inventory_available,
            rule_conflict=rule_conflict,
            no_compliant_candidate=no_compliant_candidate,
            promotion_action=promotion_action,
            markdown_action=markdown_action,
            base_action="HOLD_PRICE",
        )
    if promotion_action == "HONOR_ACTIVE_PROMOTION":
        base = "HONOR_ACTIVE_PROMOTION"
    elif markdown_action in {"SEASONAL_SLOW_MOVING_MARKDOWN", "MARKDOWN_REVIEW_REQUIRED"}:
        base = markdown_action
    elif final_price > current_price + 0.005:
        base = "PRICE_INCREASE"
    elif final_price < current_price - 0.005:
        base = "PRICE_DECREASE"
    else:
        base = "HOLD_PRICE"
    return action_precedence(
        inventory_status=inventory_status,
        inventory_available=inventory_available,
        rule_conflict=rule_conflict,
        no_compliant_candidate=no_compliant_candidate,
        promotion_action=promotion_action,
        markdown_action=markdown_action,
        base_action=base,
    )


__all__ = ["ACTION_PRECEDENCE", "action_precedence", "final_action"]
