from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from validation.metrics import purchase_metrics


def fit_calibration_candidates(
    raw_scores: np.ndarray,
    native_probabilities: np.ndarray,
    labels: np.ndarray,
) -> dict[str, Any]:
    if np.unique(labels).size < 2:
        raise ValueError("Calibration OOF labels must contain both classes")
    sigmoid = LogisticRegression(solver="lbfgs", C=1.0, max_iter=1000, random_state=42)
    sigmoid.fit(np.asarray(raw_scores, dtype=float).reshape(-1, 1), labels)
    isotonic = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    isotonic.fit(np.asarray(native_probabilities, dtype=float), labels)
    return {"NATIVE": None, "SIGMOID": sigmoid, "ISOTONIC": isotonic}


def apply_calibrator(
    method: str,
    calibrator: Any,
    raw_scores: np.ndarray,
    native_probabilities: np.ndarray,
) -> np.ndarray:
    method = method.upper()
    if method == "NATIVE":
        probabilities = np.asarray(native_probabilities, dtype=float)
    elif method == "SIGMOID":
        probabilities = calibrator.predict_proba(np.asarray(raw_scores, dtype=float).reshape(-1, 1))[:, 1]
    elif method == "ISOTONIC":
        probabilities = calibrator.predict(np.asarray(native_probabilities, dtype=float))
    else:
        raise ValueError(f"Unknown calibration method: {method}")
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Calibration produced a non-finite or out-of-range probability")
    return np.clip(probabilities, 0.0, 1.0)


def calibration_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    method: str,
) -> dict[str, Any]:
    return {"method": method, **purchase_metrics(labels, probabilities)}


def select_calibration_method(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_method = {row["method"]: row for row in rows}
    native = by_method["NATIVE"]
    material = [
        row for row in rows
        if row["method"] != "NATIVE"
        and (
            native["log_loss"] - row["log_loss"] >= 0.001
            or native["brier_score"] - row["brier_score"] >= 0.0005
        )
    ]
    if not material:
        return {
            "selected_method": "NATIVE",
            "reason": "No sigmoid or isotonic candidate met the predefined log-loss/Brier materiality threshold.",
            "materiality_log_loss": 0.001,
            "materiality_brier": 0.0005,
        }
    priority = {"NATIVE": 0, "SIGMOID": 1, "ISOTONIC": 2}
    selected = sorted(material, key=lambda row: (
        float(row["log_loss"]), float(row["brier_score"]), float(row["ece"]), priority[row["method"]]
    ))[0]
    return {
        "selected_method": selected["method"],
        "reason": "Selected by validation Log Loss, then Brier, then ECE among candidates meeting materiality.",
        "materiality_log_loss": 0.001,
        "materiality_brier": 0.0005,
    }


