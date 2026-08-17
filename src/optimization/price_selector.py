from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


TIE_ABSOLUTE = 1e-8
TIE_RELATIVE = 0.001
MINIMUM_RELATIVE_PROFIT_UPLIFT = 0.005


def _stable_argmax(group: pd.DataFrame, objective: str) -> pd.Series:
    ordered = group.sort_values(["CandidatePrice", "candidate_rank_by_price"], kind="mergesort")
    values = ordered[objective].to_numpy(dtype=float)
    best = float(np.max(values))
    band = max(TIE_ABSOLUTE, abs(best) * TIE_RELATIVE)
    near = ordered.loc[(best - ordered[objective].to_numpy(dtype=float)) <= band].copy()
    current = float(ordered["CurrentPrice"].iloc[0])
    near["_distance"] = (near["CandidatePrice"] / current - 1.0).abs()
    near = near.sort_values(["_distance", "CandidatePrice", "candidate_rank_by_price"], kind="mergesort")
    return near.iloc[0]


def select_model_optimal_prices(surface: pd.DataFrame) -> pd.DataFrame:
    """Select safe expected-gross-profit candidates with frozen stability gates."""

    rows: list[dict[str, Any]] = []
    for decision_id, group in surface.groupby("PricingDecisionID", sort=False):
        group = group.sort_values(["CandidatePrice", "candidate_rank_by_price"], kind="mergesort")
        current_rows = group[group["is_current_price_candidate"]]
        if len(current_rows) != 1:
            raise ValueError("NO_CHANGE_CANDIDATE")
        current = current_rows.iloc[0]
        raw_best = _stable_argmax(group, "raw_expected_gross_profit")
        safe_best = _stable_argmax(group, "expected_gross_profit")
        revenue_best = _stable_argmax(group, "expected_revenue")
        current_gp = float(current["expected_gross_profit"])
        best_gp = float(safe_best["expected_gross_profit"])
        absolute = best_gp - current_gp
        relative = absolute / max(abs(current_gp), 1e-8)
        material = absolute > 0 and relative >= MINIMUM_RELATIVE_PROFIT_UPLIFT
        chosen = safe_best if material else current
        status = "CHANGE_CANDIDATE" if material else "KEEP_CURRENT_NO_MATERIAL_UPLIFT"
        chosen_is_boundary = bool(chosen["is_support_lower_boundary"] or chosen["is_support_upper_boundary"])
        rows.append({
            "PricingDecisionID": decision_id,
            "DecisionTime": current["DecisionTime"],
            "ProductID": current["ProductID"],
            "StoreID": current["StoreID"],
            "Channel": current["Channel"],
            "CurrentPrice": float(current["CurrentPrice"]),
            "HistoricalAppliedPrice": float(current["AppliedPrice"]),
            "RawModelOptimalPrice": float(raw_best["CandidatePrice"]),
            "SafeModelOptimalPrice": float(safe_best["CandidatePrice"]),
            "RevenueOptimalCandidatePrice": float(revenue_best["CandidatePrice"]),
            "GrossProfitOptimalCandidatePrice": float(safe_best["CandidatePrice"]),
            "ModelOptimalCandidatePrice": float(chosen["CandidatePrice"]),
            "candidate_multiplier": float(chosen["candidate_multiplier"]),
            "current_expected_units": float(current["safe_expected_units"]),
            "recommended_expected_units": float(chosen["safe_expected_units"]),
            "current_expected_revenue": float(current["expected_revenue"]),
            "recommended_expected_revenue": float(chosen["expected_revenue"]),
            "current_expected_gross_profit": current_gp,
            "recommended_expected_gross_profit": float(chosen["expected_gross_profit"]),
            "absolute_expected_profit_uplift": float(max(0.0, float(chosen["expected_gross_profit"]) - current_gp)) if material else 0.0,
            "relative_expected_profit_uplift": float(relative) if material else 0.0,
            "current_margin_pct": float(current["candidate_margin_pct"]),
            "candidate_margin_pct": float(chosen["candidate_margin_pct"]),
            "price_change_amount": float(chosen["CandidatePrice"] - current["CurrentPrice"]),
            "price_change_pct": float(chosen["CandidatePrice"] / current["CurrentPrice"] - 1.0),
            "decision_status": status,
            "raw_vs_safe_optimum_changed": bool(float(raw_best["CandidatePrice"]) != float(safe_best["CandidatePrice"])),
            "support_boundary_flag": chosen_is_boundary,
            "raw_expected_profit_optimum": float(raw_best["raw_expected_gross_profit"]),
            "safe_expected_profit_optimum": float(safe_best["expected_gross_profit"]),
            "raw_revenue_optimum": float(revenue_best["expected_revenue"]),
            "current_negative_margin": bool(current["negative_unit_margin_candidate"]),
            "NOT_FINAL_BUSINESS_RECOMMENDATION": True,
        })
    return pd.DataFrame(rows)


__all__ = ["TIE_ABSOLUTE", "TIE_RELATIVE", "MINIMUM_RELATIVE_PROFIT_UPLIFT", "select_model_optimal_prices"]
