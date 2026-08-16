from __future__ import annotations

import numpy as np

from validation.compute import detect_compute_environment
from validation.metrics import calibration_table, expected_calibration_error, purchase_metrics, quantity_metrics


def test_metrics_and_calibration_are_deterministic():
    y = np.array([0, 1, 0, 1, 1, 0])
    p = np.array([0.10, 0.80, 0.20, 0.90, 0.60, 0.30])
    first = purchase_metrics(y, p)
    second = purchase_metrics(y, p)
    assert first == second
    table = calibration_table(y, p, bins=10)
    assert int(table["prediction_count"].sum()) == len(y)
    assert expected_calibration_error(y, p) == first["ece"]
    quantity = quantity_metrics([1, 2, 3], [1.0, 2.0, 2.5])
    assert quantity["negative_prediction_count"] == 0
    assert quantity["mae"] == 1 / 6
    assert quantity["mean_poisson_deviance"] is not None


def test_compute_policy_never_exceeds_machine_or_phase_limit():
    environment = detect_compute_environment(max_threads=22)
    assert environment["configured_thread_limit"] <= 22
    assert environment["usable_threads"] <= environment["detected_logical_threads"]
    assert environment["nested_parallelism"] is False
