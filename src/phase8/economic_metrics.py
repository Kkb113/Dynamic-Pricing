"""Economic metric helpers shared by factual and scenario reports."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def static_cost_gross_profit(price: Any, cost: Any, units: Any) -> Any:
    return (pd.to_numeric(price, errors="coerce") - pd.to_numeric(cost, errors="coerce")) * pd.to_numeric(units, errors="coerce")


def price_distribution(frame: pd.DataFrame, price_column: str, baseline_column: str = "AppliedPrice") -> dict[str, Any]:
    price = pd.to_numeric(frame[price_column], errors="coerce")
    baseline = pd.to_numeric(frame[baseline_column], errors="coerce")
    change_pct = (price - baseline) / baseline
    valid = price.notna()
    return {
        "rows": int(valid.sum()),
        "price_increase_rate": float((change_pct[valid] > 0.005).mean()) if valid.any() else 0.0,
        "price_decrease_rate": float((change_pct[valid] < -0.005).mean()) if valid.any() else 0.0,
        "hold_rate": float((change_pct[valid].abs() <= 0.005).mean()) if valid.any() else 0.0,
        "mean_price_change_pct": float(change_pct[valid].mean()) if valid.any() else None,
        "median_price_change_pct": float(change_pct[valid].median()) if valid.any() else None,
        "p05_price_change_pct": float(change_pct[valid].quantile(0.05)) if valid.any() else None,
        "p25_price_change_pct": float(change_pct[valid].quantile(0.25)) if valid.any() else None,
        "p75_price_change_pct": float(change_pct[valid].quantile(0.75)) if valid.any() else None,
        "p95_price_change_pct": float(change_pct[valid].quantile(0.95)) if valid.any() else None,
    }


def economic_deltas(summaries: dict[str, dict[str, Any]], scenario: str, baseline: str) -> dict[str, float]:
    left = summaries[scenario]
    right = summaries[baseline]
    return {
        "expected_units_delta": float(left["aggregate_expected_units"] - right["aggregate_expected_units"]),
        "expected_revenue_delta": float(left["aggregate_expected_revenue"] - right["aggregate_expected_revenue"]),
        "expected_gross_profit_delta": float(left["aggregate_expected_gross_profit"] - right["aggregate_expected_gross_profit"]),
        "expected_units_delta_pct": float((left["aggregate_expected_units"] - right["aggregate_expected_units"]) / right["aggregate_expected_units"]) if right["aggregate_expected_units"] else 0.0,
        "expected_revenue_delta_pct": float((left["aggregate_expected_revenue"] - right["aggregate_expected_revenue"]) / right["aggregate_expected_revenue"]) if right["aggregate_expected_revenue"] else 0.0,
        "expected_gross_profit_delta_pct": float((left["aggregate_expected_gross_profit"] - right["aggregate_expected_gross_profit"]) / right["aggregate_expected_gross_profit"]) if right["aggregate_expected_gross_profit"] else 0.0,
    }


__all__ = ["economic_deltas", "price_distribution", "static_cost_gross_profit"]
