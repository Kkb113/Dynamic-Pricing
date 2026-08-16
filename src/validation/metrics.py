from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_poisson_deviance,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def calibration_table(y_true: Iterable, probabilities: Iterable, bins: int = 10) -> pd.DataFrame:
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(probabilities), dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    bucket = np.digitize(np.clip(p, 0.0, 1.0), edges[1:-1], right=False)
    rows = []
    for index in range(bins):
        mask = bucket == index
        count = int(mask.sum())
        mean_probability = float(p[mask].mean()) if count else None
        observed = float(y[mask].mean()) if count else None
        gap = abs(mean_probability - observed) if count else None
        rows.append({
            "bin": index,
            "bin_lower": float(edges[index]),
            "bin_upper": float(edges[index + 1]),
            "prediction_count": count,
            "mean_predicted_probability": mean_probability,
            "observed_purchase_rate": observed,
            "absolute_calibration_gap": gap,
        })
    return pd.DataFrame(rows)


def expected_calibration_error(y_true: Iterable, probabilities: Iterable, bins: int = 10) -> float | None:
    table = calibration_table(y_true, probabilities, bins=bins)
    total = int(table["prediction_count"].sum())
    if not total:
        return None
    weighted = table["prediction_count"] * table["absolute_calibration_gap"].fillna(0.0)
    return float(weighted.sum() / total)


def _tie_aware_top_decile(y: np.ndarray, probabilities: np.ndarray) -> tuple[float | None, float | None]:
    """Estimate top-decile rate with fractional inclusion at a tied cutoff."""
    if not len(y):
        return None, None
    top_count = max(1, int(np.ceil(len(y) * 0.10)))
    order = np.argsort(-probabilities, kind="mergesort")
    cutoff = probabilities[order[top_count - 1]]
    above = probabilities > cutoff
    tied = probabilities == cutoff
    remaining = top_count - int(above.sum())
    tied_count = int(tied.sum())
    expected_positive = float(y[above].sum())
    if remaining and tied_count:
        expected_positive += (remaining / tied_count) * float(y[tied].sum())
    top_rate = expected_positive / top_count
    overall = float(y.mean())
    if not overall:
        lift = None
    elif np.isclose(top_rate, overall, rtol=0.0, atol=1e-12):
        lift = 1.0
    else:
        lift = top_rate / overall
    return float(top_rate), _float_or_none(lift)


def purchase_metrics(y_true: Iterable, probabilities: Iterable, threshold: float = 0.5) -> dict[str, Any]:
    y = np.asarray(list(y_true), dtype=int)
    p = np.asarray(list(probabilities), dtype=float)
    labels = (p >= threshold).astype(int)
    both_classes = np.unique(y).size == 2
    p_safe = np.clip(p, 1e-15, 1 - 1e-15)
    result = {
        "row_count": int(len(y)),
        "purchase_count": int(y.sum()),
        "non_purchase_count": int((y == 0).sum()),
        "purchase_rate": float(y.mean()) if len(y) else None,
        "roc_auc": _float_or_none(roc_auc_score(y, p) if both_classes else None),
        "average_precision": _float_or_none(average_precision_score(y, p) if both_classes else None),
        "log_loss": _float_or_none(log_loss(y, p_safe, labels=[0, 1])),
        "brier_score": _float_or_none(brier_score_loss(y, p)),
        "precision_at_0_5": _float_or_none(precision_score(y, labels, zero_division=0)),
        "recall_at_0_5": _float_or_none(recall_score(y, labels, zero_division=0)),
        "f1_at_0_5": _float_or_none(f1_score(y, labels, zero_division=0)),
        "ece": expected_calibration_error(y, p),
    }
    top_rate, top_lift = _tie_aware_top_decile(y, p)
    result["top_decile_purchase_rate"] = top_rate
    result["top_decile_lift"] = top_lift
    result["top_decile_tie_policy"] = "fractional inclusion at score cutoff"
    return result


def quantity_metrics(y_true: Iterable, predictions: Iterable) -> dict[str, Any]:
    y = np.asarray(list(y_true), dtype=float)
    pred = np.asarray(list(predictions), dtype=float)
    negative = int((pred < 0).sum())
    result: dict[str, Any] = {
        "row_count": int(len(y)),
        "mae": _float_or_none(mean_absolute_error(y, pred)),
        "rmse": _float_or_none(np.sqrt(np.mean((y - pred) ** 2))),
        "r2": _float_or_none(r2_score(y, pred) if len(y) > 1 and np.unique(y).size > 1 else None),
        "negative_prediction_count": negative,
        "mean_poisson_deviance": None,
    }
    if np.all(y >= 0) and np.all(pred > 0):
        result["mean_poisson_deviance"] = _float_or_none(mean_poisson_deviance(y, pred))
    return result


def aggregate_fold_metrics(rows: list[dict[str, Any]], metric_names: Iterable[str]) -> dict[str, dict[str, float | None]]:
    summary: dict[str, dict[str, float | None]] = {}
    for name in metric_names:
        values = np.asarray([row[name] for row in rows if row.get(name) is not None], dtype=float)
        summary[name] = {
            "mean": _float_or_none(values.mean()) if values.size else None,
            "std": _float_or_none(values.std(ddof=0)) if values.size else None,
            "min": _float_or_none(values.min()) if values.size else None,
            "max": _float_or_none(values.max()) if values.size else None,
        }
    return summary
