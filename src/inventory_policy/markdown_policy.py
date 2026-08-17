"""TRAIN-derived, seasonal/slow-moving markdown policy (no expiry logic)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


def derive_slow_moving_thresholds(
    train: pd.DataFrame,
    *,
    category_column: str = "CategoryID",
    primary_metric: str = "product_store_sales_30d",
    fallback_metric: str = "product_sales_30d",
    minimum_category_rows: int = 100,
) -> dict[str, Any]:
    metric = primary_metric if primary_metric in train.columns and train[primary_metric].notna().any() else fallback_metric
    if metric not in train.columns:
        raise ValueError("SLOW_MOVING_METRIC_UNAVAILABLE")
    values = pd.to_numeric(train[metric], errors="coerce")
    valid = values.dropna()
    if valid.empty:
        raise ValueError("SLOW_MOVING_METRIC_EMPTY")
    global_threshold = float(valid.quantile(0.25))
    thresholds: dict[str, float] = {}
    support: dict[str, int] = {}
    if category_column in train.columns:
        grouped = pd.DataFrame({"category": train[category_column].astype(str), "metric": values}).dropna(subset=["metric"]).groupby("category", sort=True)
        for category, group in grouped:
            support[str(category)] = int(len(group))
            thresholds[str(category)] = float(group["metric"].quantile(0.25)) if len(group) >= minimum_category_rows else global_threshold
    return {
        "metric": metric,
        "fallback_metric": fallback_metric,
        "quantile": 0.25,
        "minimum_category_rows": int(minimum_category_rows),
        "global_threshold": global_threshold,
        "category_thresholds": thresholds,
        "category_support": support,
        "source_split": "TRAIN",
        "policy_type": "RELATIVE_SYNTHETIC_POC_POLICY",
    }


def slow_moving_flag(value: Any, *, category_id: Any, thresholds: Mapping[str, Any]) -> bool:
    if value is None or pd.isna(value):
        return False
    threshold = thresholds.get("category_thresholds", {}).get(str(category_id), thresholds.get("global_threshold"))
    return bool(threshold is not None and float(value) <= float(threshold))


def seasonal_product_flag(season: Any, *, semantics: str = "SOURCE_NON_GENERIC_VALUES") -> bool:
    if season is None or pd.isna(season):
        return False
    value = str(season).strip().casefold()
    generic = {"all", "year-round", "year round", "year_round", "generic", "none", "na", "n/a", "unknown"}
    return value not in generic


def audit_seasonal_semantics(product_seasons: Any) -> dict[str, Any]:
    values = sorted({str(value) for value in product_seasons if not pd.isna(value)})
    generic = [value for value in values if value.strip().casefold() in {"all", "year-round", "year round", "year_round", "generic", "none"}]
    return {
        "observed_values": values,
        "generic_values": generic,
        "seasonal_values": [value for value in values if value not in generic],
        "semantics": "SOURCE_NON_GENERIC_VALUES",
        "calendar_mapping_used": False,
    }


def markdown_eligibility(
    *,
    mode: str,
    seasonal: bool,
    slow_moving: bool,
    high_inventory_or_overstock: bool,
    available_qty: Any,
    stock_status: str | None,
) -> dict[str, Any]:
    available = None if available_qty is None or pd.isna(available_qty) else float(available_qty)
    low_stock = str(stock_status or "").upper() == "LOW_STOCK"
    eligible = mode == "CURRENT_INVENTORY_MODE" and seasonal and slow_moving and high_inventory_or_overstock and available is not None and available > 0 and not low_stock
    return {
        "markdown_eligible": bool(eligible),
        "low_stock_protection": bool(low_stock),
        "inventory_directional_constraint": "NO_NEW_DISCOUNT_LOW_STOCK" if low_stock else None,
        "reasons": [name for name, flag in (("SEASONAL", seasonal), ("SLOW_MOVING", slow_moving), ("OVERSTOCK", high_inventory_or_overstock)) if flag],
    }


__all__ = [
    "audit_seasonal_semantics",
    "derive_slow_moving_thresholds",
    "markdown_eligibility",
    "seasonal_product_flag",
    "slow_moving_flag",
]
