"""Strict, read-only loading of the Phase 7 pricing-rule source table."""

from __future__ import annotations

from typing import Any

import pandas as pd


PRICING_RULE_COLUMNS = (
    "PricingRuleID",
    "RuleName",
    "ProductID",
    "CategoryID",
    "StoreID",
    "Channel",
    "MinPrice",
    "MaxPrice",
    "MinMarginPct",
    "MaxDiscountPct",
    "MaxPriceChangePct",
    "Priority",
    "EffectiveFrom",
    "EffectiveTo",
    "ActiveFlag",
)


def validate_pricing_rules(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized copy while rejecting schema drift and bad IDs."""

    missing = sorted(set(PRICING_RULE_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"PRICING_RULE_SCHEMA_MISMATCH: missing={missing}")
    result = frame.loc[:, list(PRICING_RULE_COLUMNS)].copy()
    if result["PricingRuleID"].isna().any() or result["PricingRuleID"].duplicated().any():
        raise ValueError("PRICING_RULE_ID_NOT_UNIQUE")
    for column in ("EffectiveFrom", "EffectiveTo"):
        result[column] = pd.to_datetime(result[column], errors="coerce")
    for column in ("MinPrice", "MaxPrice", "MinMarginPct", "MaxDiscountPct", "MaxPriceChangePct", "Priority"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["ActiveFlag"] = result["ActiveFlag"].astype("boolean")
    return result.reset_index(drop=True)


def load_pricing_rules(db: Any | None = None, *, source: pd.DataFrame | None = None, schema: str = "dbo") -> pd.DataFrame:
    """Load Pricing_Rules through a read-only connector or an explicit fixture.

    The SQL text contains only a projection of the documented source columns.  No
    write path is exposed by this module.
    """

    if source is not None:
        return validate_pricing_rules(source)
    if db is None:
        raise RuntimeError("PRICING_RULE_SOURCE_UNAVAILABLE")
    fields = ", ".join(f"[{column}]" for column in PRICING_RULE_COLUMNS)
    table = schema.replace("]", "]]" )
    rows = db.rows(f"SELECT {fields} FROM [{table}].[Pricing_Rules]")
    return validate_pricing_rules(pd.DataFrame(rows, columns=list(PRICING_RULE_COLUMNS)))


__all__ = ["PRICING_RULE_COLUMNS", "load_pricing_rules", "validate_pricing_rules"]
