from __future__ import annotations

import time
from typing import Any

import pandas as pd

from .candidate_simulator import simulate_candidate_prices
from .price_selector import select_model_optimal_prices


def optimize_prices(context_frame: pd.DataFrame, **kwargs: Any) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Run simulation and selection as separate, reusable stages."""

    started = time.perf_counter()
    surface, timings = simulate_candidate_prices(context_frame, **kwargs)
    simulation_seconds = time.perf_counter() - started
    started = time.perf_counter()
    recommendations = select_model_optimal_prices(surface)
    selection_seconds = time.perf_counter() - started
    timings["economic_scoring_seconds"] = float(0.0)
    timings["optimizer_selection_seconds"] = float(selection_seconds)
    timings["total_seconds"] = float(simulation_seconds)
    timings["candidate_rows_per_second"] = float(len(surface) / simulation_seconds) if simulation_seconds else None
    return surface, recommendations, timings


__all__ = ["optimize_prices"]
