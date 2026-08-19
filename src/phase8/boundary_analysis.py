"""Phase 8 grid-boundary, neighbor-fragility, and exact-boundary diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def actual_boundary_rates(surface: pd.DataFrame, recommendations: pd.DataFrame, decisions: pd.DataFrame, tolerance: float = 0.005) -> dict[str, Any]:
    grid = surface.groupby("PricingDecisionID", sort=False)["CandidatePrice"].agg(grid_min_price="min", grid_max_price="max").reset_index()
    rec = recommendations[["PricingDecisionID", "ModelOptimalCandidatePrice"]].rename(columns={"ModelOptimalCandidatePrice": "phase6_price"})
    final = decisions[["PricingDecisionID", "FinalRecommendedPrice"]].rename(columns={"FinalRecommendedPrice": "phase7_price"})
    frame = grid.merge(rec, on="PricingDecisionID", how="left", validate="one_to_one").merge(final, on="PricingDecisionID", how="left", validate="one_to_one")
    frame["phase6_upper_boundary"] = (frame["phase6_price"] - frame["grid_max_price"]).abs() <= tolerance
    frame["phase6_lower_boundary"] = (frame["phase6_price"] - frame["grid_min_price"]).abs() <= tolerance
    frame["phase7_upper_boundary"] = frame["phase7_price"].notna() & ((frame["phase7_price"] - frame["grid_max_price"]).abs() <= tolerance)
    frame["phase7_lower_boundary"] = frame["phase7_price"].notna() & ((frame["phase7_price"] - frame["grid_min_price"]).abs() <= tolerance)
    eligible_phase7 = frame["phase7_price"].notna()
    denominator = max(int(eligible_phase7.sum()), 1)
    return {
        "tolerance": tolerance,
        "rows": int(len(frame)),
        "phase6_upper_grid_boundary_rate": float(frame["phase6_upper_boundary"].mean()) if len(frame) else 0.0,
        "phase6_lower_grid_boundary_rate": float(frame["phase6_lower_boundary"].mean()) if len(frame) else 0.0,
        "phase7_upper_grid_boundary_rate": float(frame.loc[eligible_phase7, "phase7_upper_boundary"].sum() / denominator),
        "phase7_lower_grid_boundary_rate": float(frame.loc[eligible_phase7, "phase7_lower_boundary"].sum() / denominator),
        "phase7_any_grid_boundary_rate": float((frame.loc[eligible_phase7, "phase7_upper_boundary"] | frame.loc[eligible_phase7, "phase7_lower_boundary"]).sum() / denominator),
        "phase7_automatic_rows": int(eligible_phase7.sum()),
        "diagnostic_frame": frame,
    }


def neighbor_fragility(surface: pd.DataFrame, decisions: pd.DataFrame, boundary_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    phase7 = decisions[["PricingDecisionID", "FinalRecommendedPrice"]].copy()
    phase7 = phase7.merge(boundary_frame[["PricingDecisionID", "phase7_upper_boundary"]], on="PricingDecisionID", how="left")
    rows: list[dict[str, Any]] = []
    for decision_id, group in surface.groupby("PricingDecisionID", sort=False):
        final_row = phase7.loc[phase7["PricingDecisionID"].eq(decision_id)]
        if final_row.empty or not bool(final_row.iloc[0]["phase7_upper_boundary"]):
            continue
        final_price = final_row.iloc[0]["FinalRecommendedPrice"]
        if pd.isna(final_price):
            continue
        candidates = group.loc[pd.to_numeric(group["CandidatePrice"], errors="coerce") < float(final_price) - 0.005].sort_values("CandidatePrice")
        if candidates.empty:
            continue
        neighbor = candidates.iloc[-1]
        final_gp = float(group.loc[(group["CandidatePrice"] - float(final_price)).abs() <= 0.005, "expected_gross_profit"].iloc[0]) if ((group["CandidatePrice"] - float(final_price)).abs() <= 0.005).any() else np.nan
        neighbor_gp = float(neighbor.get("expected_gross_profit", np.nan))
        advantage = final_gp - neighbor_gp
        relative = advantage / abs(neighbor_gp) if neighbor_gp else np.nan
        rows.append({"PricingDecisionID": decision_id, "FinalRecommendedPrice": float(final_price), "next_lower_candidate_price": float(neighbor["CandidatePrice"]), "final_expected_gross_profit": final_gp, "next_lower_expected_gross_profit": neighbor_gp, "gp_advantage": advantage, "relative_gp_advantage": relative})
    result = pd.DataFrame(rows)
    if result.empty:
        stats = {"rows": 0, "warning_codes": []}
    else:
        relative = pd.to_numeric(result["relative_gp_advantage"], errors="coerce").dropna()
        stats = {
            "rows": int(len(result)),
            "mean_gp_advantage": float(result["gp_advantage"].mean()),
            "median_gp_advantage": float(result["gp_advantage"].median()),
            "p05_gp_advantage": float(result["gp_advantage"].quantile(0.05)),
            "p25_gp_advantage": float(result["gp_advantage"].quantile(0.25)),
            "p75_gp_advantage": float(result["gp_advantage"].quantile(0.75)),
            "p95_gp_advantage": float(result["gp_advantage"].quantile(0.95)),
            "mean_relative_gp_advantage": float(relative.mean()) if len(relative) else None,
            "median_relative_gp_advantage": float(relative.median()) if len(relative) else None,
            "share_relative_below_0_1pct": float((relative < 0.001).mean()) if len(relative) else 0.0,
            "share_relative_below_0_5pct": float((relative < 0.005).mean()) if len(relative) else 0.0,
            "share_relative_at_least_1pct": float((relative >= 0.01).mean()) if len(relative) else 0.0,
            "warning_codes": [],
        }
        if stats["median_relative_gp_advantage"] is not None and stats["median_relative_gp_advantage"] < 0.005:
            stats["warning_codes"].append("BOUNDARY_OPTIMUM_FRAGILE")
        if stats["share_relative_below_0_1pct"] > 0.50:
            stats["warning_codes"].append("BOUNDARY_RECOMMENDATIONS_NEAR_TIED")
    return result, stats


def exact_boundary_candidates(surface: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """List in-support rule boundaries not already represented on the grid."""

    columns = ["PricingDecisionID", "effective_price_floor", "effective_price_ceiling"]
    bounds = decisions[[column for column in columns if column in decisions.columns]].drop_duplicates("PricingDecisionID")
    grid = surface.groupby("PricingDecisionID", sort=False)["CandidatePrice"].agg(grid_min_price="min", grid_max_price="max").reset_index()
    merged = bounds.merge(grid, on="PricingDecisionID", how="left", validate="one_to_one")
    rows: list[dict[str, Any]] = []
    for row in merged.to_dict("records"):
        for name in ("effective_price_floor", "effective_price_ceiling"):
            value = row.get(name)
            if value is None or pd.isna(value):
                continue
            exact = round(float(value), 2)
            if exact < float(row["grid_min_price"]) - 0.005 or exact > float(row["grid_max_price"]) + 0.005:
                continue
            existing = surface.loc[surface["PricingDecisionID"].astype(str).eq(str(row["PricingDecisionID"])), "CandidatePrice"]
            if not existing.empty and (pd.to_numeric(existing, errors="coerce") - exact).abs().le(0.005).any():
                continue
            rows.append({"PricingDecisionID": row["PricingDecisionID"], "boundary_type": "RULE_FLOOR" if name.endswith("floor") else "RULE_CEILING", "boundary_price": exact, "grid_min_price": row["grid_min_price"], "grid_max_price": row["grid_max_price"]})
    return pd.DataFrame(rows)


def boundary_augmentation_summary(candidates: pd.DataFrame, scored: pd.DataFrame, decisions: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if candidates.empty:
        return scored, {"in_support_unsimulated_boundaries": 0, "boundaries_scored": 0, "decisions_where_augmented_optimum_differs": 0, "change_rate": 0.0, "aggregate_model_implied_gp_delta": 0.0, "relative_aggregate_gp_delta": 0.0, "mean_price_delta": 0.0, "warning_codes": []}
    merged = scored.merge(decisions[["PricingDecisionID", "FinalRecommendedPrice"]], on="PricingDecisionID", how="left", validate="many_to_one")
    merged["gp_delta_vs_phase7"] = merged["expected_gross_profit"] - merged.get("phase7_expected_gross_profit", merged["expected_gross_profit"])
    # The runner supplies phase7_expected_gross_profit and augmented optimum.
    changes = merged.get("augmented_optimum_differs", pd.Series(False, index=merged.index)).astype(bool)
    aggregate = float(merged.get("gp_delta_vs_phase7", pd.Series(dtype=float)).sum())
    baseline = float(pd.to_numeric(merged.get("phase7_expected_gross_profit", pd.Series(dtype=float)), errors="coerce").sum())
    relative = aggregate / baseline if baseline else 0.0
    warnings: list[str] = []
    if relative > 0.005:
        warnings.append("COARSE_GRID_VALUE_WARNING")
    blockers = ["MATERIAL_GRID_GRANULARITY_GAP"] if relative > 0.02 else []
    return merged, {
        "in_support_unsimulated_boundaries": int(len(candidates)),
        "boundaries_scored": int(len(scored)),
        "decisions_where_augmented_optimum_differs": int(changes.sum()),
        "change_rate": float(changes.mean()) if len(changes) else 0.0,
        "aggregate_model_implied_gp_delta": aggregate,
        "relative_aggregate_gp_delta": relative,
        "mean_price_delta": float(pd.to_numeric(merged.get("augmented_optimum_price", pd.Series(dtype=float)), errors="coerce").sub(pd.to_numeric(merged.get("FinalRecommendedPrice", pd.Series(dtype=float)), errors="coerce")).mean()) if len(merged) else 0.0,
        "warning_codes": warnings,
        "blockers": blockers,
    }


__all__ = ["actual_boundary_rates", "boundary_augmentation_summary", "exact_boundary_candidates", "neighbor_fragility"]
