"""Exact-cent business-rule bounds and candidate compliance checks."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import numpy as np

from .rule_semantics import is_null, normalize_percentage


CENT = Decimal("0.01")


def _decimal(value: Any) -> Decimal | None:
    if is_null(value):
        return None
    try:
        result = Decimal(str(float(value)))
    except (TypeError, ValueError, ArithmeticError):
        return None
    return result if result.is_finite() else None


def round_price_half_up(value: Any) -> float:
    decimal = _decimal(value)
    if decimal is None:
        raise ValueError("INVALID_PRICE")
    return float(decimal.quantize(CENT, rounding=ROUND_HALF_UP))


def derive_rule_bounds(
    rule: Mapping[str, Any] | None,
    *,
    base_price: Any,
    current_price: Any,
    cost_price: Any,
    percentage_convention: str = "PERCENT_POINTS",
) -> dict[str, Any]:
    """Derive independent floors/ceilings without silently clipping a price."""

    if rule is None:
        return {"effective_price_floor": None, "effective_price_ceiling": None, "floor_reasons": [], "ceiling_reasons": [], "conflict": False}
    base, current, cost = _decimal(base_price), _decimal(current_price), _decimal(cost_price)
    floor_values: list[tuple[str, Decimal]] = []
    ceiling_values: list[tuple[str, Decimal]] = []
    for field, reason in (("MinPrice", "RULE_MIN_PRICE"),):
        value = _decimal(rule.get(field))
        if value is not None:
            floor_values.append((reason, value))
    value = _decimal(rule.get("MaxPrice"))
    if value is not None:
        ceiling_values.append(("RULE_MAX_PRICE", value))
    margin = normalize_percentage(rule.get("MinMarginPct"), percentage_convention)
    if margin is not None and cost is not None:
        if margin >= 1.0:
            raise ValueError("MIN_MARGIN_FRACTION_INVALID")
        floor_values.append(("RULE_MIN_MARGIN", cost / (Decimal("1") - Decimal(str(margin)))))
    discount = normalize_percentage(rule.get("MaxDiscountPct"), percentage_convention)
    if discount is not None and base is not None:
        if discount < 0 or discount > 1:
            raise ValueError("MAX_DISCOUNT_FRACTION_INVALID")
        floor_values.append(("RULE_MAX_DISCOUNT", base * (Decimal("1") - Decimal(str(discount)))))
    movement = normalize_percentage(rule.get("MaxPriceChangePct"), percentage_convention)
    if movement is not None and current is not None:
        if movement < 0 or movement > 1:
            raise ValueError("MAX_PRICE_CHANGE_FRACTION_INVALID")
        fraction = Decimal(str(movement))
        floor_values.append(("RULE_MAX_PRICE_CHANGE", current * (Decimal("1") - fraction)))
        ceiling_values.append(("RULE_MAX_PRICE_CHANGE", current * (Decimal("1") + fraction)))
    floor = max((value for _, value in floor_values), default=None)
    ceiling = min((value for _, value in ceiling_values), default=None)
    return {
        "effective_price_floor": None if floor is None else float(floor),
        "effective_price_ceiling": None if ceiling is None else float(ceiling),
        "floor_reasons": [reason for reason, value in floor_values if value == floor],
        "ceiling_reasons": [reason for reason, value in ceiling_values if value == ceiling],
        "conflict": bool(floor is not None and ceiling is not None and floor > ceiling),
        "raw_floor": None if floor is None else str(floor),
        "raw_ceiling": None if ceiling is None else str(ceiling),
    }


def evaluate_candidate_constraints(
    candidate_price: Any,
    rule: Mapping[str, Any] | None,
    *,
    base_price: Any,
    current_price: Any,
    cost_price: Any,
    percentage_convention: str = "PERCENT_POINTS",
) -> dict[str, Any]:
    """Return every required compliance flag and machine-readable violations."""

    price = _decimal(candidate_price)
    if price is None:
        raise ValueError("INVALID_CANDIDATE_PRICE")
    if rule is None:
        return {
            "passes_min_price": True,
            "passes_max_price": True,
            "passes_min_margin": True,
            "passes_max_discount": True,
            "passes_max_price_change": True,
            "passes_all_pricing_rules": True,
            "rule_violation_count": 0,
            "rule_violation_reasons": [],
            "rule_constraint_conflict": False,
        }
    base, current, cost = _decimal(base_price), _decimal(current_price), _decimal(cost_price)
    min_price = _decimal(rule.get("MinPrice"))
    max_price = _decimal(rule.get("MaxPrice"))
    margin = normalize_percentage(rule.get("MinMarginPct"), percentage_convention)
    discount = normalize_percentage(rule.get("MaxDiscountPct"), percentage_convention)
    movement = normalize_percentage(rule.get("MaxPriceChangePct"), percentage_convention)
    flags = {
        "passes_min_price": min_price is None or price >= min_price,
        "passes_max_price": max_price is None or price <= max_price,
        "passes_min_margin": True,
        "passes_max_discount": True,
        "passes_max_price_change": True,
    }
    if margin is not None and cost is not None:
        flags["passes_min_margin"] = price > 0 and (price - cost) / price >= Decimal(str(margin))
    if discount is not None and base is not None:
        flags["passes_max_discount"] = price >= base * (Decimal("1") - Decimal(str(discount)))
    if movement is not None and current is not None:
        lower = current * (Decimal("1") - Decimal(str(movement)))
        upper = current * (Decimal("1") + Decimal(str(movement)))
        flags["passes_max_price_change"] = lower <= price <= upper
    reasons = [name.replace("passes_", "RULE_").upper() for name, passed in flags.items() if not passed]
    bounds = derive_rule_bounds(rule, base_price=base_price, current_price=current_price, cost_price=cost_price, percentage_convention=percentage_convention)
    if bounds["conflict"]:
        reasons.append("RULE_CONSTRAINT_CONFLICT")
    unique_reasons = list(dict.fromkeys(reasons))
    flags.update({
        "passes_all_pricing_rules": not unique_reasons,
        "rule_violation_count": int(len(unique_reasons)),
        "rule_violation_reasons": unique_reasons,
        "rule_constraint_conflict": bool(bounds["conflict"]),
    })
    return flags


__all__ = ["CENT", "derive_rule_bounds", "evaluate_candidate_constraints", "round_price_half_up"]
