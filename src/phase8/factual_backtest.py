"""Factual historical-price backtesting metrics.

All functions in this module compare predictions at the actually observed
AppliedPrice with observed outcomes.  Counterfactual scenario language is
kept out of the factual metrics and reports.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, log_loss, mean_absolute_error, mean_poisson_deviance, mean_squared_error, roc_auc_score


def _wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    denominator = float(np.abs(actual).sum())
    return float(np.abs(actual - predicted).sum() / denominator) if denominator else 0.0


def _bias(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(predicted - actual)) if len(actual) else 0.0


def _aggregate_error(actual: np.ndarray, predicted: np.ndarray, *, include_poisson_deviance: bool = False) -> dict[str, float]:
    observed = float(actual.sum())
    estimate = float(predicted.sum())
    delta = estimate - observed
    result = {
        "aggregate_observed": observed,
        "aggregate_predicted": estimate,
        "aggregate_delta": float(delta),
        "aggregate_error_pct": float(delta / observed) if observed else 0.0,
        "mae": float(mean_absolute_error(actual, predicted)) if len(actual) else 0.0,
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))) if len(actual) else 0.0,
        "wape": _wape(actual, predicted),
        "mean_bias": _bias(actual, predicted),
    }
    if include_poisson_deviance:
        result["poisson_deviance"] = float(mean_poisson_deviance(actual, np.clip(predicted, 1e-15, None))) if len(actual) else 0.0
    return result


def purchase_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    actual = pd.to_numeric(frame["PurchasedFlag"], errors="coerce").astype(int).to_numpy()
    probability = pd.to_numeric(frame["historical_purchase_probability"], errors="coerce").astype(float).to_numpy()
    metrics: dict[str, Any] = {
        "rows": int(len(frame)),
        "positive_rate": float(actual.mean()) if len(actual) else 0.0,
        "roc_auc": float(roc_auc_score(actual, probability)) if len(np.unique(actual)) > 1 else None,
        "average_precision": float(average_precision_score(actual, probability)) if len(np.unique(actual)) > 1 else None,
        "log_loss": float(log_loss(actual, np.clip(probability, 1e-15, 1 - 1e-15), labels=[0, 1])) if len(actual) else None,
        "brier_score": float(np.mean((probability - actual) ** 2)) if len(actual) else 0.0,
    }
    order = np.argsort(-probability, kind="mergesort")
    top_n = max(1, int(np.ceil(len(frame) * 0.10)))
    overall = float(actual.mean()) if len(actual) else 0.0
    top_rate = float(actual[order[:top_n]].mean()) if len(actual) else 0.0
    metrics["top_decile_lift"] = float(top_rate / overall) if overall else None
    bins = np.linspace(0, 1, 11)
    bucket = np.clip(np.digitize(probability, bins, right=True) - 1, 0, 9)
    ece = 0.0
    calibration_rows: list[dict[str, Any]] = []
    for decile in range(10):
        mask = bucket == decile
        count = int(mask.sum())
        if not count:
            continue
        mean_probability = float(probability[mask].mean())
        observed_rate = float(actual[mask].mean())
        ece += count / max(len(frame), 1) * abs(mean_probability - observed_rate)
        calibration_rows.append({"decile": decile + 1, "decision_count": count, "mean_predicted_probability": mean_probability, "observed_purchase_rate": observed_rate})
    metrics["ece"] = float(ece)
    metrics["calibration_rows"] = calibration_rows
    return metrics


def factual_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    result = {
        "purchase": purchase_metrics(frame),
        "demand": _aggregate_error(
            pd.to_numeric(frame["QuantityPurchased"], errors="coerce").to_numpy(float),
            pd.to_numeric(frame["historical_expected_units"], errors="coerce").to_numpy(float),
            include_poisson_deviance=True,
        ),
        "revenue": _aggregate_error(
            pd.to_numeric(frame["ActualRevenue"], errors="coerce").to_numpy(float),
            pd.to_numeric(frame["historical_expected_revenue"], errors="coerce").to_numpy(float),
        ),
        "gross_profit": _aggregate_error(
            pd.to_numeric(frame["ObservedGrossProfit"], errors="coerce").to_numpy(float),
            pd.to_numeric(frame["historical_expected_gross_profit"], errors="coerce").to_numpy(float),
        ),
    }
    observed_revenue = result["revenue"]["aggregate_observed"]
    observed_gp = result["gross_profit"]["aggregate_observed"]
    predicted_revenue = result["revenue"]["aggregate_predicted"]
    predicted_gp = result["gross_profit"]["aggregate_predicted"]
    result["observed_gross_margin_rate"] = float(observed_gp / observed_revenue) if observed_revenue else 0.0
    result["predicted_historical_gross_margin_rate"] = float(predicted_gp / predicted_revenue) if predicted_revenue else 0.0
    result["aggregate_units_error_pct"] = result["demand"]["aggregate_error_pct"]
    result["aggregate_revenue_error_pct"] = result["revenue"]["aggregate_error_pct"]
    result["aggregate_gross_profit_error_pct"] = result["gross_profit"]["aggregate_error_pct"]
    return result


def probability_deciles(frame: pd.DataFrame) -> pd.DataFrame:
    """Produce the required ten probability groups with factual outcomes."""

    result = frame.copy()
    probability = pd.to_numeric(result["historical_purchase_probability"], errors="coerce")
    result["probability_decile"] = pd.qcut(probability.rank(method="first"), 10, labels=False, duplicates="drop") + 1
    grouped = result.groupby("probability_decile", dropna=False, sort=True)
    table = grouped.agg(
        decision_count=("PricingDecisionID", "size"),
        mean_predicted_purchase_probability=("historical_purchase_probability", "mean"),
        observed_purchase_rate=("PurchasedFlag", "mean"),
        predicted_units=("historical_expected_units", "sum"),
        observed_units=("QuantityPurchased", "sum"),
        predicted_revenue=("historical_expected_revenue", "sum"),
        observed_revenue=("ActualRevenue", "sum"),
    ).reset_index()
    return table


def gate_status(error_pct: float, strong: float, warning: float, blocker: str) -> tuple[str, str | None]:
    absolute = abs(float(error_pct))
    if absolute <= strong:
        return "STRONG", None
    if absolute <= warning:
        return "WARNING", None
    return "BLOCKED", blocker


def factual_gate_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    demand_status, demand_blocker = gate_status(metrics["aggregate_units_error_pct"], 0.05, 0.10, "DEMAND_BACKTEST_FAILURE")
    revenue_status, revenue_blocker = gate_status(metrics["aggregate_revenue_error_pct"], 0.075, 0.15, "REVENUE_BACKTEST_FAILURE")
    gp_status, gp_blocker = gate_status(metrics["aggregate_gross_profit_error_pct"], 0.10, 0.20, "GROSS_PROFIT_BACKTEST_FAILURE")
    blockers = [value for value in [demand_blocker, revenue_blocker, gp_blocker] if value]
    return {
        "demand": demand_status,
        "revenue": revenue_status,
        "gross_profit": gp_status,
        "blockers": blockers,
        "status": "BLOCKED" if blockers else "PASS_WITH_WARNINGS" if "WARNING" in [demand_status, revenue_status, gp_status] else "PASS",
    }


__all__ = ["factual_gate_metrics", "factual_metrics", "gate_status", "probability_deciles", "purchase_metrics"]
