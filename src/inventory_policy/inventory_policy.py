"""Explicit separation between historical policy replay and current snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


HISTORICAL_POLICY_MODE = "HISTORICAL_POLICY_MODE"
CURRENT_INVENTORY_MODE = "CURRENT_INVENTORY_MODE"


def assert_historical_policy_safe(frame: pd.DataFrame) -> None:
    """Fail closed if a historical output carries current-inventory fields."""

    if "InventorySnapshotDate" in frame and frame["InventorySnapshotDate"].notna().any():
        raise ValueError("HISTORICAL_INVENTORY_LEAKAGE")
    if "AvailableQty" in frame and frame["AvailableQty"].notna().any():
        raise ValueError("HISTORICAL_INVENTORY_LEAKAGE")
    if "inventory_constraint_applied" in frame and frame["inventory_constraint_applied"].astype(bool).any():
        raise ValueError("HISTORICAL_INVENTORY_LEAKAGE")


def resolve_current_inventory(
    inventory: pd.DataFrame,
    *,
    product_id: Any,
    store_id: Any,
    as_of_date: Any | None = None,
    status_mapping: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if inventory.empty:
        return {"status": "MANUAL_REVIEW_INVENTORY_UNAVAILABLE", "inventory_constraint_applied": True, "InventorySnapshotDate": None, "AvailableQty": None, "StockStatus": None}
    as_of = pd.Timestamp(as_of_date).normalize() if as_of_date is not None else inventory["SnapshotDate"].max()
    match = inventory.loc[
        inventory["ProductID"].astype(str).eq(str(product_id))
        & inventory["StoreID"].astype(str).eq(str(store_id))
        & (inventory["SnapshotDate"] <= as_of)
    ].sort_values("SnapshotDate", ascending=False, kind="mergesort")
    if match.empty:
        return {"status": "MANUAL_REVIEW_INVENTORY_UNAVAILABLE", "inventory_constraint_applied": True, "InventorySnapshotDate": None, "AvailableQty": None, "StockStatus": None}
    row = match.iloc[0]
    raw_status = row["StockStatus"]
    normalized = status_mapping.get(str(raw_status), "UNKNOWN") if status_mapping else str(raw_status)
    available = float(row["AvailableQty"])
    if available <= 0 or normalized == "OUT_OF_STOCK":
        status = "OUT_OF_STOCK_NO_PRICE_ACTION"
    else:
        status = "AVAILABLE"
    return {
        "status": status,
        "inventory_constraint_applied": True,
        "InventorySnapshotDate": row["SnapshotDate"],
        "AvailableQty": available,
        "StockStatus": normalized,
        "raw_stock_status": raw_status,
        "OnHandQty": float(row["OnHandQty"]),
    }


def cap_inventory_economics(row: Mapping[str, Any], available_qty: Any) -> dict[str, float]:
    available = float(available_qty)
    if not np.isfinite(available) or available < 0:
        raise ValueError("INVENTORY_QUANTITY_INVALID")
    units = min(float(row.get("safe_expected_units", row.get("expected_units", 0.0))), available)
    price = float(row.get("CandidatePrice", row.get("FinalRecommendedPrice", 0.0)))
    cost = float(row.get("CostPrice", 0.0))
    revenue = price * units
    profit = (price - cost) * units
    return {
        "inventory_capped_expected_units": units,
        "inventory_capped_expected_revenue": revenue,
        "inventory_capped_expected_gross_profit": profit,
    }


__all__ = [
    "CURRENT_INVENTORY_MODE",
    "HISTORICAL_POLICY_MODE",
    "assert_historical_policy_safe",
    "cap_inventory_economics",
    "resolve_current_inventory",
]
