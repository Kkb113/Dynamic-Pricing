from __future__ import annotations

from typing import Any

from sklearn.dummy import DummyRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline

from features.feature_contract import model_feature_columns
from validation.preprocessing import make_preprocessor


def purchased_population(frame, *, target_column: str = "PurchasedFlag"):
    """Return the conditional quantity population without making the flag a feature."""
    if target_column not in frame.columns:
        raise ValueError(f"Missing quantity population selector: {target_column}")
    population = frame.loc[frame[target_column] == 1].copy()
    if population.empty:
        raise ValueError("Quantity training population contains no purchased rows")
    return population


def make_quantity_pipeline(contract: dict[str, Any], model_name: str) -> tuple[Pipeline, list[str]]:
    if model_name not in {"quantity_dummy_mean", "quantity_poisson_core"}:
        raise ValueError(f"Unknown quantity baseline: {model_name}")
    feature_names = model_feature_columns(contract, population="quantity")
    preprocessor, _, _ = make_preprocessor(contract, feature_names)
    if model_name == "quantity_dummy_mean":
        estimator = DummyRegressor(strategy="mean")
    else:
        estimator = PoissonRegressor(alpha=1.0, max_iter=1000)
    return Pipeline([("preprocess", preprocessor), ("model", estimator)]), feature_names
