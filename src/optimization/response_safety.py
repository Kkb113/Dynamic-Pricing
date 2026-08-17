from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def apply_response_safety(
    surface: pd.DataFrame,
    *,
    decision_key: str = "PricingDecisionID",
    price_key: str = "CandidatePrice",
    raw_key: str = "raw_expected_units",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply the frozen low-to-high cumulative-minimum demand guard."""

    result = surface.copy()
    result["safe_expected_units"] = np.nan
    result["response_guard_adjusted_flag"] = False
    result["raw_demand_non_monotonic_flag"] = False
    result["number_of_adjusted_candidates"] = 0
    result["maximum_expected_units_adjustment"] = 0.0
    result["mean_expected_units_adjustment"] = 0.0
    decision_rows: list[dict[str, Any]] = []
    for decision_id, indices in result.groupby(decision_key, sort=False).groups.items():
        ordered = result.loc[indices].sort_values([price_key, "candidate_rank_by_price"], kind="mergesort")
        raw = ordered[raw_key].to_numpy(dtype=float)
        if not np.isfinite(raw).all() or np.any(raw < 0):
            raise ValueError("INVALID_RAW_EXPECTED_UNITS")
        safe = np.minimum.accumulate(raw)
        adjustment = raw - safe
        non_monotonic = bool(np.any(np.diff(raw) > 1e-12))
        adjusted = adjustment > 1e-12
        result.loc[ordered.index, "safe_expected_units"] = safe
        result.loc[ordered.index, "response_guard_adjusted_flag"] = adjusted
        result.loc[ordered.index, "raw_demand_non_monotonic_flag"] = non_monotonic
        result.loc[ordered.index, "number_of_adjusted_candidates"] = int(adjusted.sum())
        result.loc[ordered.index, "maximum_expected_units_adjustment"] = float(adjustment.max(initial=0.0))
        result.loc[ordered.index, "mean_expected_units_adjustment"] = float(adjustment.mean())
        decision_rows.append({
            decision_key: decision_id,
            "raw_demand_non_monotonic_flag": non_monotonic,
            "response_guard_adjusted_flag": bool(adjusted.any()),
            "number_of_adjusted_candidates": int(adjusted.sum()),
            "maximum_expected_units_adjustment": float(adjustment.max(initial=0.0)),
            "mean_expected_units_adjustment": float(adjustment.mean()),
        })
        if len(safe) > 1 and np.any(np.diff(safe) > 1e-12):
            raise ValueError("OPTIMIZER_SAFE_DEMAND_MONOTONICITY_FAILURE")
        if np.any(safe - raw > 1e-12):
            raise ValueError("RESPONSE_SAFETY_INCREASED_DEMAND")
    decisions = pd.DataFrame(decision_rows)
    decision_count = len(decisions)
    adjusted_candidates = int(result["response_guard_adjusted_flag"].sum())
    adjustments = (result[raw_key] - result["safe_expected_units"]).clip(lower=0.0)
    summary = {
        "decision_count": int(decision_count),
        "candidate_count": int(len(result)),
        "raw_non_monotonic_decision_count": int(decisions["raw_demand_non_monotonic_flag"].sum()) if decision_count else 0,
        "raw_non_monotonic_decision_rate": float(decisions["raw_demand_non_monotonic_flag"].mean()) if decision_count else 0.0,
        "adjusted_decision_count": int(decisions["response_guard_adjusted_flag"].sum()) if decision_count else 0,
        "adjusted_decision_rate": float(decisions["response_guard_adjusted_flag"].mean()) if decision_count else 0.0,
        "candidate_adjustment_count": adjusted_candidates,
        "candidate_adjustment_rate": float(adjusted_candidates / len(result)) if len(result) else 0.0,
        "mean_adjustment": float(adjustments.mean()) if len(adjustments) else 0.0,
        "median_adjustment": float(adjustments.median()) if len(adjustments) else 0.0,
        "p95_adjustment": float(adjustments.quantile(0.95)) if len(adjustments) else 0.0,
        "max_adjustment": float(adjustments.max()) if len(adjustments) else 0.0,
        "safe_monotonic_violations": 0,
    }
    return result, {"summary": summary, "decision_diagnostics": decisions}


__all__ = ["apply_response_safety"]
