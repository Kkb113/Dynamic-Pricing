from __future__ import annotations

import numpy as np
import pandas as pd


def score_economics(surface: pd.DataFrame) -> pd.DataFrame:
    """Score the frozen revenue, unit-margin, and expected-profit formulas."""

    result = surface.copy()
    candidate = pd.to_numeric(result["CandidatePrice"], errors="coerce").to_numpy(float)
    cost = pd.to_numeric(result["CostPrice"], errors="coerce").to_numpy(float)
    safe = pd.to_numeric(result["safe_expected_units"], errors="coerce").to_numpy(float)
    raw = pd.to_numeric(result["raw_expected_units"], errors="coerce").to_numpy(float)
    if not np.isfinite(candidate).all() or not np.isfinite(cost).all() or not np.isfinite(safe).all() or np.any(candidate <= 0) or np.any(cost <= 0):
        raise ValueError("INVALID_ECONOMIC_INPUT")
    result["expected_revenue"] = candidate * safe
    result["raw_expected_revenue"] = candidate * raw
    result["unit_gross_profit"] = candidate - cost
    result["candidate_margin_pct"] = result["unit_gross_profit"] / candidate
    result["expected_gross_profit"] = result["unit_gross_profit"] * safe
    result["raw_expected_gross_profit"] = result["unit_gross_profit"] * raw
    result["negative_unit_margin_candidate"] = result["unit_gross_profit"] < 0
    for column in ["expected_revenue", "unit_gross_profit", "candidate_margin_pct", "expected_gross_profit"]:
        values = pd.to_numeric(result[column], errors="coerce").to_numpy(float)
        if not np.isfinite(values).all():
            raise ValueError(f"NONFINITE_{column.upper()}")
    return result


__all__ = ["score_economics"]
