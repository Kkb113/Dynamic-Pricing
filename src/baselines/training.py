from __future__ import annotations

import time
from typing import Any, Callable

import pandas as pd

from validation.compute import thread_limited


def fit_pipeline(pipeline: Any, frame: pd.DataFrame, target: pd.Series, environment: dict[str, Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    with thread_limited(environment):
        pipeline.fit(frame, target)
    return pipeline, time.perf_counter() - started


def predict_probabilities(pipeline: Any, frame: pd.DataFrame, environment: dict[str, Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    with thread_limited(environment):
        values = pipeline.predict_proba(frame)[:, 1]
    return values, time.perf_counter() - started


def predict_values(pipeline: Any, frame: pd.DataFrame, environment: dict[str, Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    with thread_limited(environment):
        values = pipeline.predict(frame)
    return values, time.perf_counter() - started
