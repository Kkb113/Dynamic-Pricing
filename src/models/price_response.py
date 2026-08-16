from __future__ import annotations

from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from models.catboost_data import build_purchase_model_features_for_candidate_price


PRICE_MULTIPLIERS = (0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20)


def candidate_price_predictions(
    model: Any,
    frame: pd.DataFrame,
    contract: dict[str, Any],
    feature_names: Iterable[str],
    multipliers: Iterable[float] = PRICE_MULTIPLIERS,
    predict: Callable[[Any, Any], np.ndarray] | None = None,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Predict a fixed set of candidate prices without changing context."""
    multipliers = tuple(float(value) for value in multipliers)
    predictor = predict or (lambda fitted, prepared: fitted.predict_proba(prepared)[:, 1])
    current = pd.to_numeric(frame["CurrentPrice"], errors="coerce").to_numpy(dtype=float)
    rows: list[pd.DataFrame] = []
    predictions: list[np.ndarray] = []
    for multiplier in multipliers:
        candidate = current * multiplier
        prepared = build_purchase_model_features_for_candidate_price(frame, candidate, contract, feature_names)
        probabilities = np.asarray(predictor(model, prepared), dtype=float)
        predictions.append(probabilities)
        rows.append(pd.DataFrame({
            "PricingDecisionID": frame["PricingDecisionID"].to_numpy(),
            "multiplier": multiplier,
            "candidate_price": candidate,
            "predicted_probability": probabilities,
        }))
    return pd.concat(rows, ignore_index=True), np.vstack(predictions).T


def summarize_price_response(
    predictions: np.ndarray,
    multipliers: Iterable[float] = PRICE_MULTIPLIERS,
) -> dict[str, Any]:
    probabilities = np.asarray(predictions, dtype=float)
    multipliers = tuple(float(value) for value in multipliers)
    if probabilities.ndim != 2 or probabilities.shape[1] != len(multipliers):
        raise ValueError("Price response matrix shape does not match multipliers")
    differences = np.diff(probabilities, axis=1)
    ranges = probabilities.max(axis=1) - probabilities.min(axis=1)
    current_index = min(range(len(multipliers)), key=lambda index: abs(multipliers[index] - 1.0))
    minus_index = min(range(len(multipliers)), key=lambda index: abs(multipliers[index] - 0.9))
    plus_index = min(range(len(multipliers)), key=lambda index: abs(multipliers[index] - 1.1))
    summary = {
        "row_count": int(probabilities.shape[0]),
        "multipliers": list(multipliers),
        "median_predicted_probability_by_multiplier": {
            str(multiplier): float(np.median(probabilities[:, index]))
            for index, multiplier in enumerate(multipliers)
        },
        "median_probability_change_minus_10pct_to_current": float(np.median(probabilities[:, current_index] - probabilities[:, minus_index])),
        "median_probability_change_current_to_plus_10pct": float(np.median(probabilities[:, plus_index] - probabilities[:, current_index])),
        "mean_probability_range": float(np.mean(ranges)),
        "median_probability_range": float(np.median(ranges)),
        "flat_response_rate": float(np.mean(ranges < 0.005)),
        "non_monotonic_sequence_rate": float(np.mean((differences > 1e-9).any(axis=1))),
        "significant_upward_violation_rate": float(np.mean((differences > 0.01).any(axis=1))),
        "causal_interpretation": "model-implied predictive price response only; not a causal elasticity estimate",
    }
    return summary

