"""Supported TEST segment economics and warning aggregation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


SEGMENT_COLUMNS = ("Channel", "Season", "RegionID", "CategoryID", "StoreType")


def segment_metrics(frame: pd.DataFrame, *, minimum_rows: int = 100) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    total_revenue = float(pd.to_numeric(frame["ActualRevenue"], errors="coerce").sum())
    for column in SEGMENT_COLUMNS:
        if column not in frame.columns:
            continue
        for value, group in frame.groupby(column, dropna=False, sort=True):
            if len(group) < minimum_rows:
                continue
            actual_units = float(pd.to_numeric(group["QuantityPurchased"], errors="coerce").sum())
            predicted_units = float(pd.to_numeric(group["historical_expected_units"], errors="coerce").sum())
            actual_revenue = float(pd.to_numeric(group["ActualRevenue"], errors="coerce").sum())
            predicted_revenue = float(pd.to_numeric(group["historical_expected_revenue"], errors="coerce").sum())
            actual_gp = float(pd.to_numeric(group["ObservedGrossProfit"], errors="coerce").sum())
            predicted_gp = float(pd.to_numeric(group["historical_expected_gross_profit"], errors="coerce").sum())
            if "S3_PHASE7_FINAL_AUTOMATIC_price" in group:
                automatic = pd.to_numeric(group["S3_PHASE7_FINAL_AUTOMATIC_price"], errors="coerce").notna()
            else:
                automatic = pd.to_numeric(group["S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit"], errors="coerce").notna()
            # Compare S0 and S3 on the same automatic decision IDs.  Summing
            # S0 over all rows while S3 skips manual rows creates an artificial
            # segment-level GP loss.
            automatic_group = group.loc[automatic]
            phase7_gp = float(pd.to_numeric(automatic_group["S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit"], errors="coerce").sum())
            historical_gp = float(pd.to_numeric(automatic_group["S0_HISTORICAL_APPLIED_expected_gross_profit"], errors="coerce").sum())
            revenue_error = (predicted_revenue - actual_revenue) / actual_revenue if actual_revenue else 0.0
            gp_error = (predicted_gp - actual_gp) / actual_gp if actual_gp else 0.0
            gp_delta = (phase7_gp - historical_gp) / historical_gp if historical_gp else 0.0
            auto = group["FinalRecommendedPrice"].notna() if "FinalRecommendedPrice" in group else pd.Series(False, index=group.index)
            price_change = pd.to_numeric(group.get("FinalRecommendedPrice"), errors="coerce") - pd.to_numeric(group.get("AppliedPrice"), errors="coerce") if "FinalRecommendedPrice" in group else pd.Series(dtype=float)
            rows.append({
                "segment_dimension": column,
                "segment_value": None if pd.isna(value) else str(value),
                "row_count": int(len(group)),
                "observed_units": actual_units,
                "predicted_historical_units": predicted_units,
                "units_error_pct": (predicted_units - actual_units) / actual_units if actual_units else 0.0,
                "observed_revenue": actual_revenue,
                "predicted_historical_revenue": predicted_revenue,
                "revenue_error_pct": revenue_error,
                "observed_gp": actual_gp,
                "predicted_historical_gp": predicted_gp,
                "gp_error_pct": gp_error,
                "phase7_model_implied_gp_delta_pct": gp_delta,
                "phase7_automatic_cohort_rows": int(len(automatic_group)),
                "automatic_recommendation_coverage": float(auto.mean()),
                "manual_review_rate": float((~auto).mean()),
                "price_increase_rate": float((price_change > 0.005).mean()) if len(price_change) else 0.0,
                "actual_upper_grid_boundary_rate": float(group.get("phase7_upper_boundary", pd.Series(False, index=group.index)).mean()),
            })
            if abs(revenue_error) > 0.20:
                warnings.append({"code": "SEGMENT_REVENUE_CALIBRATION_WARNING", "dimension": column, "value": str(value), "error_pct": revenue_error})
            if abs(gp_error) > 0.25:
                warnings.append({"code": "SEGMENT_GP_CALIBRATION_WARNING", "dimension": column, "value": str(value), "error_pct": gp_error})
    table = pd.DataFrame(rows)
    major = table.loc[table["observed_revenue"] >= 0.20 * total_revenue] if not table.empty else table
    major_failure = bool(not major.empty and (major["gp_error_pct"].abs() > 0.30).any())
    return table, {
        "minimum_rows": minimum_rows,
        "supported_segments": int(len(table)),
        "warnings": warnings,
        "revenue_warning_count": int(sum(item["code"] == "SEGMENT_REVENUE_CALIBRATION_WARNING" for item in warnings)),
        "gp_warning_count": int(sum(item["code"] == "SEGMENT_GP_CALIBRATION_WARNING" for item in warnings)),
        "major_segment_economic_calibration_failure": major_failure,
        "blockers": ["MAJOR_SEGMENT_ECONOMIC_CALIBRATION_FAILURE"] if major_failure else [],
    }


__all__ = ["SEGMENT_COLUMNS", "segment_metrics"]
