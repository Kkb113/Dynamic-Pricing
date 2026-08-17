"""Strict, read-only loader and snapshot audit for Inventory."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


INVENTORY_COLUMNS = (
    "InventoryID",
    "StoreID",
    "ProductID",
    "SnapshotDate",
    "OpeningQty",
    "ReceivedQty",
    "SoldQty",
    "ReturnedQty",
    "AdjustmentQty",
    "ReservedQty",
    "OnHandQty",
    "AvailableQty",
    "StockStatus",
)


def validate_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(INVENTORY_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"INVENTORY_SCHEMA_MISMATCH: missing={missing}")
    result = frame.loc[:, list(INVENTORY_COLUMNS)].copy()
    result["SnapshotDate"] = pd.to_datetime(result["SnapshotDate"], errors="coerce").dt.normalize()
    if result["SnapshotDate"].isna().any():
        raise ValueError("INVENTORY_SNAPSHOT_DATE_INVALID")
    for column in INVENTORY_COLUMNS[4:-1]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in ("OnHandQty", "AvailableQty"):
        values = result[column].to_numpy(float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("INVENTORY_QUANTITY_INVALID")
    duplicate_key = ["ProductID", "StoreID", "SnapshotDate"]
    duplicates = result.duplicated(duplicate_key, keep=False)
    if duplicates.any():
        # Identical duplicates can be safely deduplicated; conflicting rows must
        # be reviewed instead of silently summed.
        conflicting = result.loc[duplicates].groupby(duplicate_key, dropna=False)["AvailableQty"].nunique().gt(1)
        if conflicting.any():
            raise ValueError("INVENTORY_DUPLICATE_CONFLICT")
        result = result.drop_duplicates(duplicate_key, keep="last")
    return result.reset_index(drop=True)


def audit_inventory(frame: pd.DataFrame) -> dict[str, Any]:
    result = validate_inventory(frame)
    values = result["AvailableQty"].astype(float)
    status_counts = result["StockStatus"].astype(str).value_counts(dropna=False).sort_index()
    return {
        "rows": int(len(result)),
        "unique_product_count": int(result["ProductID"].nunique()),
        "unique_store_count": int(result["StoreID"].nunique()),
        "snapshot_dates": [value.strftime("%Y-%m-%d") for value in sorted(result["SnapshotDate"].dropna().unique())],
        "latest_snapshot_date": None if result.empty else result["SnapshotDate"].max().strftime("%Y-%m-%d"),
        "duplicate_product_store_snapshot_rows": int(frame.duplicated(["ProductID", "StoreID", "SnapshotDate"], keep=False).sum()),
        "available_qty": {
            "min": float(values.min()) if len(values) else None,
            "max": float(values.max()) if len(values) else None,
            "mean": float(values.mean()) if len(values) else None,
            "median": float(values.median()) if len(values) else None,
            "zero_rate": float((values <= 0).mean()) if len(values) else None,
        },
        "stock_status_counts": {str(key): int(value) for key, value in status_counts.items()},
    }


def freeze_status_mapping(statuses: Any) -> dict[str, str]:
    """Map observed labels only when their meaning is explicit; unknown stays UNKNOWN."""

    mapping: dict[str, str] = {}
    for value in sorted({str(item) for item in statuses if not pd.isna(item)}):
        normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
        if normalized in {"OUT_OF_STOCK", "OOS", "OUTOFSTOCK", "STOCKOUT"}:
            target = "OUT_OF_STOCK"
        elif normalized in {"LOW_STOCK", "LOW", "LOWSTOCK"}:
            target = "LOW_STOCK"
        elif normalized in {"OVERSTOCK", "HIGH_STOCK", "HIGH_INVENTORY"}:
            target = "OVERSTOCK"
        elif normalized in {"NORMAL", "IN_STOCK", "AVAILABLE", "HEALTHY"}:
            target = "NORMAL"
        else:
            target = "UNKNOWN"
        mapping[value] = target
    return mapping


def load_inventory(db: Any | None = None, *, source: pd.DataFrame | None = None, schema: str = "dbo") -> pd.DataFrame:
    if source is not None:
        return validate_inventory(source)
    if db is None:
        raise RuntimeError("INVENTORY_SOURCE_UNAVAILABLE")
    fields = ", ".join(f"[{column}]" for column in INVENTORY_COLUMNS)
    table = schema.replace("]", "]]" )
    rows = db.rows(f"SELECT {fields} FROM [{table}].[Inventory]")
    return validate_inventory(pd.DataFrame(rows, columns=list(INVENTORY_COLUMNS)))


__all__ = ["INVENTORY_COLUMNS", "audit_inventory", "freeze_status_mapping", "load_inventory", "validate_inventory"]
