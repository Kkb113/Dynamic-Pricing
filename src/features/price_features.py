from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


PRICE_DEPENDENT_FEATURES = [
    "price_change_amount",
    "price_change_pct",
    "price_vs_base_pct",
    "discount_from_base_pct",
    "price_vs_competitor_pct",
]


def safe_divide(numerator: Any, denominator: Any) -> Any:
    """Divide only by positive denominators; invalid denominators become null."""
    if isinstance(numerator, pd.Series) or isinstance(denominator, pd.Series):
        num = pd.to_numeric(pd.Series(numerator), errors="coerce")
        den = pd.to_numeric(pd.Series(denominator), errors="coerce")
        return pd.Series(np.where(den > 0, num / den, np.nan), index=num.index, dtype="float64")
    try:
        num = float(numerator) if numerator is not None else np.nan
        den = float(denominator) if denominator is not None else np.nan
    except (TypeError, ValueError):
        return np.nan
    return num / den if den > 0 else np.nan


def build_price_dependent_features(
    offered_price: Any,
    current_price: Any,
    base_price: Any,
    competitor_price: Any = None,
) -> pd.DataFrame:
    """Build the reusable price-response features used for training and simulation.

    ``offered_price`` is ``AppliedPrice`` during historical dataset construction and
    can be replaced by a candidate price at inference time.  No learned state is
    stored in this function.
    """
    scalar_input = all(np.isscalar(value) or value is None for value in (offered_price, current_price, base_price, competitor_price))
    values = {
        "offered_price": offered_price,
        "current_price": current_price,
        "base_price": base_price,
        "competitor_price": competitor_price,
    }
    if scalar_input:
        values = {key: [value] for key, value in values.items()}
    frame = pd.DataFrame(values)
    for column in values:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["price_change_amount"] = frame["offered_price"] - frame["current_price"]
    frame["price_change_pct"] = safe_divide(
        frame["price_change_amount"], frame["current_price"]
    )
    frame["price_vs_base_pct"] = safe_divide(
        frame["offered_price"] - frame["base_price"], frame["base_price"]
    )
    frame["current_vs_base_pct"] = safe_divide(
        frame["current_price"] - frame["base_price"], frame["base_price"]
    )
    frame["discount_from_base_pct"] = safe_divide(
        frame["base_price"] - frame["offered_price"], frame["base_price"]
    )
    frame["price_vs_competitor_pct"] = safe_divide(
        frame["offered_price"] - frame["competitor_price"], frame["competitor_price"]
    )
    result = frame[PRICE_DEPENDENT_FEATURES + ["current_vs_base_pct"]]
    return result.iloc[0] if scalar_input else result
