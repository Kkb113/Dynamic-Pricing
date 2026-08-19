"""Deterministic bootstrap intervals for factual and scenario metrics."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd


def _error_pct(sample: pd.DataFrame, actual: str, predicted: str) -> float:
    observed = float(pd.to_numeric(sample[actual], errors="coerce").sum())
    estimate = float(pd.to_numeric(sample[predicted], errors="coerce").sum())
    return float((estimate - observed) / observed) if observed else 0.0


def bootstrap_intervals(
    frame: pd.DataFrame,
    *,
    samples: int = 1000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict[str, Any]:
    if frame.empty:
        return {"seed": seed, "bootstrap_samples": samples, "confidence": confidence, "intervals": {}, "status": "PASS"}
    rng = np.random.default_rng(seed)
    n = len(frame)
    index = np.arange(n)
    if "S3_PHASE7_FINAL_AUTOMATIC_price" in frame.columns:
        automatic_frame = frame.loc[pd.to_numeric(frame["S3_PHASE7_FINAL_AUTOMATIC_price"], errors="coerce").notna()].copy()
    else:
        automatic_frame = frame.loc[pd.to_numeric(frame["S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit"], errors="coerce").notna()].copy()
    automatic_index = np.arange(len(automatic_frame))
    values = {"aggregate_units_error_pct": [], "aggregate_revenue_error_pct": [], "aggregate_gp_error_pct": [], "phase7_model_implied_gp_delta_pct": []}
    for _ in range(samples):
        sampled = frame.iloc[rng.choice(index, size=n, replace=True)]
        values["aggregate_units_error_pct"].append(_error_pct(sampled, "QuantityPurchased", "historical_expected_units"))
        values["aggregate_revenue_error_pct"].append(_error_pct(sampled, "ActualRevenue", "historical_expected_revenue"))
        values["aggregate_gp_error_pct"].append(_error_pct(sampled, "ObservedGrossProfit", "historical_expected_gross_profit"))
        # Keep the Phase 7 GP delta on the identical automatic-only cohort.
        # Manual-review S3 rows have no recommendation and must not be treated
        # as zero while the S0 denominator still includes them.
        # Resample the fixed automatic cohort independently for the scenario
        # delta; manual-review IDs can never enter its denominator.
        automatic = automatic_frame.iloc[rng.choice(automatic_index, size=len(automatic_frame), replace=True)] if len(automatic_frame) else automatic_frame
        historical_gp = float(pd.to_numeric(automatic["S0_HISTORICAL_APPLIED_expected_gross_profit"], errors="coerce").sum())
        phase7_gp = float(pd.to_numeric(automatic["S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit"], errors="coerce").sum())
        values["phase7_model_implied_gp_delta_pct"].append((phase7_gp - historical_gp) / historical_gp if historical_gp else 0.0)
    intervals = {
        key: {"lower_2_5_pct": float(np.quantile(value, 0.025)), "upper_97_5_pct": float(np.quantile(value, 0.975)), "mean": float(np.mean(value))}
        for key, value in values.items()
    }
    return {"seed": seed, "bootstrap_samples": samples, "confidence": confidence, "intervals": intervals, "interpretation": "Sample uncertainty only; intervals do not make counterfactual comparisons causal.", "status": "PASS"}


__all__ = ["bootstrap_intervals"]
