"""Strict loader for the documented category-level Promotions table."""

from __future__ import annotations

from typing import Any

import pandas as pd


PROMOTION_COLUMNS = (
    "PromotionID",
    "PromotionName",
    "CategoryID",
    "DiscountPct",
    "Season",
    "StartDate",
    "EndDate",
    "ActiveFlag",
)


def validate_promotions(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(PROMOTION_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"PROMOTION_SCHEMA_MISMATCH: missing={missing}")
    result = frame.loc[:, list(PROMOTION_COLUMNS)].copy()
    if result["PromotionID"].isna().any() or result["PromotionID"].duplicated().any():
        raise ValueError("PROMOTION_ID_NOT_UNIQUE")
    result["StartDate"] = pd.to_datetime(result["StartDate"], errors="coerce").dt.normalize()
    result["EndDate"] = pd.to_datetime(result["EndDate"], errors="coerce").dt.normalize()
    if result[["StartDate", "EndDate"]].isna().any().any() or (result["StartDate"] > result["EndDate"]).any():
        raise ValueError("PROMOTION_DATE_WINDOW_INVALID")
    result["DiscountPct"] = pd.to_numeric(result["DiscountPct"], errors="coerce")
    if result["DiscountPct"].isna().any() or (~result["DiscountPct"].between(0, 100)).any():
        raise ValueError("PROMOTION_DISCOUNT_INVALID")
    result["ActiveFlag"] = result["ActiveFlag"].astype("boolean")
    return result.reset_index(drop=True)


def load_promotions(db: Any | None = None, *, source: pd.DataFrame | None = None, schema: str = "dbo") -> pd.DataFrame:
    if source is not None:
        return validate_promotions(source)
    if db is None:
        raise RuntimeError("PROMOTION_SOURCE_UNAVAILABLE")
    fields = ", ".join(f"[{column}]" for column in PROMOTION_COLUMNS)
    table = schema.replace("]", "]]" )
    rows = db.rows(f"SELECT {fields} FROM [{table}].[Promotions]")
    return validate_promotions(pd.DataFrame(rows, columns=list(PROMOTION_COLUMNS)))


__all__ = ["PROMOTION_COLUMNS", "load_promotions", "validate_promotions"]
