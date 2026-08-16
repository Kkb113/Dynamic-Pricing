"""CatBoost regression adapter and quantity metrics for Phase 5."""

from __future__ import annotations

import time
from typing import Any, Iterable

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, __version__ as catboost_version
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance, r2_score

from models.quantity_data import make_quantity_pool


SCREENING_PARAMETERS: dict[str, Any] = {
    "learning_rate": 0.05,
    "depth": 5,
    "l2_leaf_reg": 5.0,
    "random_strength": 1.0,
    "bagging_temperature": 1.0,
    "border_count": 128,
}


def quantity_parameters(
    hyperparameters: dict[str, Any] | None = None,
    *,
    loss: str,
    thread_count: int,
    iterations: int = 1500,
    random_seed: int = 42,
    early_stopping_rounds: int | None = 150,
    use_best_model: bool = True,
) -> dict[str, Any]:
    loss_key = str(loss).upper()
    if loss_key not in {"RMSE", "POISSON"}:
        raise ValueError(f"Unsupported quantity loss: {loss}")
    # CatBoost's CPU parser accepts the canonical mixed-case objective names;
    # the public Phase 5 contract uses uppercase labels for reporting.
    loss_name = "Poisson" if loss_key == "POISSON" else "RMSE"
    hp = {**SCREENING_PARAMETERS, **(hyperparameters or {})}
    params: dict[str, Any] = {
        "iterations": int(iterations),
        "learning_rate": float(hp.get("learning_rate", 0.05)),
        "depth": int(hp.get("depth", 5)),
        "l2_leaf_reg": float(hp.get("l2_leaf_reg", 5.0)),
        "random_strength": float(hp.get("random_strength", 1.0)),
        "bootstrap_type": "Bayesian",
        "bagging_temperature": float(hp.get("bagging_temperature", 1.0)),
        "border_count": int(hp.get("border_count", 128)),
        "loss_function": loss_name,
        "eval_metric": loss_name,
        "random_seed": int(random_seed),
        "thread_count": int(thread_count),
        "task_type": "CPU",
        "allow_writing_files": False,
        "verbose": False,
        "use_best_model": bool(use_best_model),
    }
    if early_stopping_rounds is not None:
        params["early_stopping_rounds"] = int(early_stopping_rounds)
    return params


def make_quantity_regressor(
    hyperparameters: dict[str, Any] | None = None,
    *,
    loss: str,
    thread_count: int,
    iterations: int = 1500,
    random_seed: int = 42,
    early_stopping_rounds: int | None = 150,
    use_best_model: bool = True,
) -> CatBoostRegressor:
    return CatBoostRegressor(
        **quantity_parameters(
            hyperparameters,
            loss=loss,
            thread_count=thread_count,
            iterations=iterations,
            random_seed=random_seed,
            early_stopping_rounds=early_stopping_rounds,
            use_best_model=use_best_model,
        )
    )


def fit_quantity_regressor(
    train: pd.DataFrame,
    validation: pd.DataFrame | None,
    contract: dict[str, Any],
    feature_names: Iterable[str],
    *,
    loss: str,
    hyperparameters: dict[str, Any] | None = None,
    thread_count: int,
    iterations: int = 1500,
    random_seed: int = 42,
    early_stopping_rounds: int | None = 150,
    use_best_model: bool = True,
) -> tuple[CatBoostRegressor, int, float, float]:
    """Fit one model and return model, selected iteration, fit and prediction setup time."""

    train_pool = make_quantity_pool(train, contract, feature_names, train["QuantityPurchased"])
    validation_pool = None
    if validation is not None and len(validation):
        validation_pool = make_quantity_pool(validation, contract, feature_names, validation["QuantityPurchased"])
    model = make_quantity_regressor(
        hyperparameters,
        loss=loss,
        thread_count=thread_count,
        iterations=iterations,
        random_seed=random_seed,
        early_stopping_rounds=early_stopping_rounds if validation_pool is not None else None,
        use_best_model=use_best_model if validation_pool is not None else False,
    )
    started = time.perf_counter()
    model.fit(train_pool, eval_set=validation_pool)
    fit_seconds = time.perf_counter() - started
    best = model.get_best_iteration()
    if best is None or best < 0:
        best = model.tree_count_ - 1
    return model, int(best), float(fit_seconds), float(model.tree_count_)


def predict_quantity_raw(model: CatBoostRegressor, pool_or_frame: Any) -> np.ndarray:
    """Return CatBoost's native regression output before the declared floor."""

    # CatBoost 1.2.x returns exponentiated predictions for Poisson by default;
    # RMSE returns raw regression values.  This is the model output that the
    # domain projection intentionally audits and floors.
    return np.asarray(model.predict(pool_or_frame), dtype=float).reshape(-1)


def project_quantity(raw_prediction: Iterable[float], minimum: float = 1.0) -> np.ndarray:
    raw = np.asarray(list(raw_prediction), dtype=float)
    if not np.isfinite(raw).all():
        raise ValueError("Non-finite conditional quantity predictions")
    projected = np.maximum(raw, float(minimum))
    if not np.isfinite(projected).all() or np.any(projected < float(minimum)):
        raise ValueError("Invalid projected conditional quantity predictions")
    return projected


def quantity_metrics(
    actual: Iterable[float],
    projected: Iterable[float],
    *,
    raw: Iterable[float] | None = None,
    minimum: float = 1.0,
) -> dict[str, Any]:
    y = np.asarray(list(actual), dtype=float)
    pred = np.asarray(list(projected), dtype=float)
    if len(y) != len(pred):
        raise ValueError("Quantity actual/prediction length mismatch")
    if len(y) == 0:
        raise ValueError("Quantity metrics require at least one row")
    if not np.isfinite(y).all() or not np.isfinite(pred).all():
        raise ValueError("Non-finite quantity metric inputs")
    raw_values = pred if raw is None else np.asarray(list(raw), dtype=float)
    below = raw_values < float(minimum)
    poisson = None
    if np.all(y >= 0) and np.all(pred > 0):
        poisson = float(mean_poisson_deviance(y, pred))
    return {
        "row_count": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "r2": float(r2_score(y, pred)) if len(y) > 1 and np.unique(y).size > 1 else None,
        "mean_poisson_deviance": poisson,
        "mean_prediction": float(pred.mean()),
        "mean_actual": float(y.mean()),
        "bias": float(np.mean(pred - y)),
        "raw_predictions_below_minimum_count": int(below.sum()),
        "raw_predictions_below_minimum_rate": float(below.mean()),
        "negative_prediction_count": int((pred < 0).sum()),
        "conditional_quantity_minimum": float(minimum),
    }


def model_best_iteration(model: CatBoostRegressor) -> int:
    best = model.get_best_iteration()
    return int(model.tree_count_ - 1 if best is None or best < 0 else best)


__all__ = [
    "CatBoostRegressor",
    "catboost_version",
    "SCREENING_PARAMETERS",
    "quantity_parameters",
    "make_quantity_regressor",
    "fit_quantity_regressor",
    "predict_quantity_raw",
    "project_quantity",
    "quantity_metrics",
    "model_best_iteration",
]
