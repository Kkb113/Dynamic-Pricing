"""Pure functions for expected-unit integration and diagnostics."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance, r2_score


def compute_expected_units(purchase_probability: Iterable[float], conditional_quantity: Iterable[float], *, minimum: float = 0.0) -> np.ndarray:
    probability = np.asarray(list(purchase_probability), dtype=float)
    quantity = np.asarray(list(conditional_quantity), dtype=float)
    if len(probability) != len(quantity):
        raise ValueError("Purchase-probability and conditional-quantity length mismatch")
    if not np.isfinite(probability).all() or not np.isfinite(quantity).all():
        raise ValueError("Expected-unit inputs must be finite")
    if np.any(probability < 0) or np.any(probability > 1):
        raise ValueError("Purchase probabilities must be in [0, 1]")
    if np.any(quantity < float(minimum)):
        raise ValueError("Conditional quantity violates declared minimum")
    expected = probability * quantity
    if not np.isfinite(expected).all() or np.any(expected < 0):
        raise ValueError("Expected units are invalid")
    return expected


def observed_units(purchased_flag: Iterable[int], quantity_purchased: Iterable[float]) -> np.ndarray:
    flag = np.asarray(list(purchased_flag), dtype=int)
    quantity = np.asarray(list(quantity_purchased), dtype=float)
    if len(flag) != len(quantity):
        raise ValueError("Observed-unit input length mismatch")
    if not np.isfinite(quantity).all():
        raise ValueError("Quantity target contains non-finite values")
    result = np.where(flag == 1, quantity, 0.0)
    if np.any(result < 0):
        raise ValueError("Observed units cannot be negative")
    return result


def expected_units_metrics(actual_units: Iterable[float], predicted_units: Iterable[float]) -> dict[str, float | int | None]:
    actual = np.asarray(list(actual_units), dtype=float)
    predicted = np.asarray(list(predicted_units), dtype=float)
    if len(actual) != len(predicted) or not len(actual):
        raise ValueError("Expected-unit metrics require equal non-empty arrays")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all() or np.any(predicted <= 0):
        raise ValueError("Expected-unit metric inputs must be finite and positive predictions")
    actual_sum = float(actual.sum())
    predicted_sum = float(predicted.sum())
    error = predicted_sum - actual_sum
    return {
        "row_count": int(len(actual)),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(np.mean((actual - predicted) ** 2))),
        "mean_poisson_deviance": float(mean_poisson_deviance(actual, predicted)),
        "mean_bias": float(np.mean(predicted - actual)),
        "aggregate_actual_units": actual_sum,
        "aggregate_predicted_units": predicted_sum,
        "aggregate_units_error": error,
        "aggregate_units_error_pct": float(error / actual_sum * 100.0) if actual_sum else None,
        "mean_actual_units": float(actual.mean()),
        "mean_predicted_units": float(predicted.mean()),
        "r2": float(r2_score(actual, predicted)) if len(actual) > 1 and np.unique(actual).size > 1 else None,
    }


def expected_units_calibration(actual_units: Iterable[float], predicted_units: Iterable[float], bins: int = 10) -> pd.DataFrame:
    actual = np.asarray(list(actual_units), dtype=float)
    predicted = np.asarray(list(predicted_units), dtype=float)
    if len(actual) != len(predicted):
        raise ValueError("Calibration input length mismatch")
    if not len(actual):
        return pd.DataFrame(columns=["decile", "row_count", "mean_predicted_units", "mean_observed_units", "absolute_gap", "sum_predicted_units", "sum_observed_units"])
    # Rank-based deciles are deterministic even when many predictions tie.
    order = np.argsort(predicted, kind="mergesort")
    labels = np.empty(len(predicted), dtype=int)
    labels[order] = np.minimum((np.arange(len(predicted)) * bins) // len(predicted), bins - 1)
    rows: list[dict[str, float | int]] = []
    for decile in range(bins):
        mask = labels == decile
        if not mask.any():
            continue
        rows.append({
            "decile": int(decile + 1),
            "row_count": int(mask.sum()),
            "mean_predicted_units": float(predicted[mask].mean()),
            "mean_observed_units": float(actual[mask].mean()),
            "absolute_gap": float(abs(predicted[mask].mean() - actual[mask].mean())),
            "sum_predicted_units": float(predicted[mask].sum()),
            "sum_observed_units": float(actual[mask].sum()),
        })
    return pd.DataFrame(rows)


__all__ = ["compute_expected_units", "observed_units", "expected_units_metrics", "expected_units_calibration"]

