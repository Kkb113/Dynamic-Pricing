"""TRAIN-only quantity screening, HPO, and pre-declared adoption gates."""

from __future__ import annotations

import json
import time
from typing import Any, Iterable

import numpy as np
import optuna
import pandas as pd

from models.quantity_catboost import (
    SCREENING_PARAMETERS,
    fit_quantity_regressor,
    make_quantity_regressor,
    model_best_iteration,
    predict_quantity_raw,
    project_quantity,
    quantity_metrics,
)
from models.quantity_data import QuantityFeatureFamily, make_quantity_pool


LOSSES = ("RMSE", "POISSON")
NEAR_TIE_RMSE = 0.003
CUSTOMER_RMSE_BAR = 0.005
ADOPTION_RMSE_IMPROVEMENT = 0.003
ADOPTION_POISSON_IMPROVEMENT = 0.002
ADOPTION_RMSE_DAMAGE = 0.003
ADOPTION_POISSON_DAMAGE = 0.002
ADOPTION_MAE_DAMAGE = 0.010


def _purchased(part: pd.DataFrame) -> pd.DataFrame:
    if "PurchasedFlag" not in part or "QuantityPurchased" not in part:
        raise ValueError("Quantity fitting requires population and target columns")
    return part.loc[part["PurchasedFlag"].astype(int) == 1].copy()


def _aggregate(fold_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (family, loss), group in fold_frame.groupby(["family", "loss"], sort=False):
        row: dict[str, Any] = {
            "row_type": "aggregate",
            "family": family,
            "loss": loss,
            "feature_count": int(group["feature_count"].iloc[0]),
            "groups": group["groups"].iloc[0],
            "fold_count": int(len(group)),
        }
        for column in ["row_count", "mae", "rmse", "r2", "mean_poisson_deviance", "mean_prediction", "mean_actual", "bias", "raw_predictions_below_minimum_count", "raw_predictions_below_minimum_rate", "best_iteration", "fit_seconds", "prediction_seconds"]:
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            row[f"{column}_mean"] = float(values.mean()) if len(values) else None
            row[f"{column}_std"] = float(values.std(ddof=0)) if len(values) else None
            row[f"{column}_min"] = float(values.min()) if len(values) else None
            row[f"{column}_max"] = float(values.max()) if len(values) else None
        rows.append(row)
    return pd.DataFrame(rows)


def screen_quantity_feature_families(
    development: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
    contract: dict[str, Any],
    families: dict[str, QuantityFeatureFamily],
    *,
    thread_count: int,
    iterations: int = 1500,
    minimum: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Screen every family under RMSE and Poisson on purchased TRAIN folds."""

    rows: list[dict[str, Any]] = []
    for family in families.values():
        for loss in LOSSES:
            for fold_number, (train_indices, validation_indices) in enumerate(folds, start=1):
                train = _purchased(development.iloc[train_indices])
                validation = _purchased(development.iloc[validation_indices])
                model, best_iteration, fit_seconds, _ = fit_quantity_regressor(
                    train,
                    validation,
                    contract,
                    family.feature_names,
                    loss=loss,
                    hyperparameters=SCREENING_PARAMETERS,
                    thread_count=thread_count,
                    iterations=iterations,
                    random_seed=42,
                    early_stopping_rounds=150,
                    use_best_model=True,
                )
                validation_pool = make_quantity_pool(validation, contract, family.feature_names, validation["QuantityPurchased"])
                started = time.perf_counter()
                raw = predict_quantity_raw(model, validation_pool)
                prediction_seconds = time.perf_counter() - started
                projected = project_quantity(raw, minimum)
                metrics = quantity_metrics(validation["QuantityPurchased"], projected, raw=raw, minimum=minimum)
                rows.append(
                    {
                        "row_type": "fold",
                        "family": family.name,
                        "loss": loss,
                        "groups": "+".join(family.groups) if family.groups else "CORE",
                        "feature_count": len(family.feature_names),
                        "fold": int(fold_number),
                        "train_row_count": int(len(train)),
                        "validation_row_count": int(len(validation)),
                        "best_iteration": int(best_iteration),
                        "fit_seconds": float(fit_seconds),
                        "prediction_seconds": float(prediction_seconds),
                        **metrics,
                    }
                )
    fold_frame = pd.DataFrame(rows)
    return fold_frame, _aggregate(fold_frame)


def _simplest(candidates: list[str], aggregate: pd.DataFrame, families: dict[str, QuantityFeatureFamily]) -> str:
    if not candidates:
        raise ValueError("No quantity candidates available")
    indexed = aggregate.set_index(["family", "loss"])
    # Caller provides one loss at a time; the helper is intentionally small.
    return sorted(candidates, key=lambda name: (len(families[name].feature_names), name))[0]


def select_quantity_feature_loss(
    fold_metrics: pd.DataFrame,
    summary: pd.DataFrame,
    families: dict[str, QuantityFeatureFamily],
) -> dict[str, Any]:
    """Select family/loss using RMSE, Poisson, MAE, stability, and simplicity."""

    aggregate = summary[summary["row_type"] == "aggregate"].copy()
    if aggregate.empty:
        raise ValueError("Quantity screening summary is empty")
    candidates = aggregate.to_dict("records")
    best_rmse = min(float(row["rmse_mean"]) for row in candidates)
    near = [row for row in candidates if float(row["rmse_mean"]) - best_rmse < NEAR_TIE_RMSE]
    # Customer-context family rows must first pass the stronger predeclared bar.
    non_customer = [row for row in near if not families[row["family"]].customer_context]
    customer_eligible: list[str] = []
    base_non_customer_rmse = min(float(row["rmse_mean"]) for row in non_customer) if non_customer else best_rmse
    for row in candidates:
        family = families[row["family"]]
        if not family.customer_context:
            continue
        base = aggregate[aggregate["family"].isin([r["family"] for r in non_customer]) & (aggregate["loss"] == row["loss"])]
        if base.empty:
            continue
        best_base = base.sort_values("rmse_mean").iloc[0]
        candidate_folds = fold_metrics[(fold_metrics["family"] == row["family"]) & (fold_metrics["loss"] == row["loss"])].sort_values("fold")
        base_folds = fold_metrics[(fold_metrics["family"] == best_base["family"]) & (fold_metrics["loss"] == row["loss"])].sort_values("fold")
        if len(candidate_folds) != 3 or len(base_folds) != 3:
            continue
        improvements = base_folds["rmse"].to_numpy(float) - candidate_folds["rmse"].to_numpy(float)
        if float(best_base["rmse_mean"]) - float(row["rmse_mean"]) >= CUSTOMER_RMSE_BAR and float(row["mean_poisson_deviance_mean"]) <= float(best_base["mean_poisson_deviance_mean"]) and int((improvements > 0).sum()) >= 2:
            customer_eligible.append(f"{row['family']}|{row['loss']}")
    allowed = [row for row in candidates if (not families[row["family"]].customer_context) or f"{row['family']}|{row['loss']}" in customer_eligible]
    best_rmse = min(float(row["rmse_mean"]) for row in allowed)
    near = [row for row in allowed if float(row["rmse_mean"]) - best_rmse < NEAR_TIE_RMSE]
    near.sort(key=lambda row: (float(row["mean_poisson_deviance_mean"]), float(row["mae_mean"]), float(row["rmse_std"]), len(families[row["family"]].feature_names), row["family"], row["loss"]))
    selected = near[0]
    return {
        "selected_feature_family": selected["family"],
        "selected_loss": selected["loss"],
        "selected_feature_count": len(families[selected["family"]].feature_names),
        "selected_groups": list(families[selected["family"]].groups),
        "best_rmse_mean": float(best_rmse),
        "customer_context_eligible": customer_eligible,
        "customer_context_selected": families[selected["family"]].customer_context,
        "phase4_reference_family": "F3_CORE_BEHAVIOR",
        "selection_policy": {
            "primary": "mean temporal-fold RMSE",
            "near_tie_rmse": NEAR_TIE_RMSE,
            "secondary": "mean Poisson deviance",
            "then": ["mean MAE", "RMSE fold std", "feature count", "depth", "loss/family name"],
            "customer_rmse_improvement": CUSTOMER_RMSE_BAR,
            "customer_poisson_must_not_worsen": True,
            "customer_minimum_improved_folds": 2,
        },
        "family_feature_counts": {name: len(family.feature_names) for name, family in families.items()},
        "selected_screening_metrics": selected,
    }


def _trial_params(trial: optuna.Trial, max_iterations: int) -> dict[str, Any]:
    low_iterations = min(200, int(max_iterations))
    return {
        "iterations": trial.suggest_int("iterations", low_iterations, int(max_iterations)),
        "learning_rate": trial.suggest_float("learning_rate", 0.015, 0.15, log=True),
        "depth": trial.suggest_int("depth", 3, 8),
        "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 50.0, log=True),
        "random_strength": trial.suggest_float("random_strength", 0.0, 3.0),
        "bagging_temperature": trial.suggest_float("bagging_temperature", 0.0, 5.0),
        "border_count": trial.suggest_categorical("border_count", [64, 128, 254]),
    }


def run_quantity_hpo(
    development: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
    contract: dict[str, Any],
    feature_names: Iterable[str],
    *,
    loss: str,
    thread_count: int,
    n_trials: int = 60,
    seed: int = 42,
    max_iterations: int = 2500,
    minimum: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    names = tuple(feature_names)
    records: dict[int, dict[str, Any]] = {}

    def objective(trial: optuna.Trial) -> float:
        params = _trial_params(trial, max_iterations)
        started = time.perf_counter()
        fold_rows: list[dict[str, Any]] = []
        try:
            for fold_number, (train_indices, validation_indices) in enumerate(folds, start=1):
                train = _purchased(development.iloc[train_indices])
                validation = _purchased(development.iloc[validation_indices])
                model, best_iteration, _, _ = fit_quantity_regressor(
                    train,
                    validation,
                    contract,
                    names,
                    loss=loss,
                    hyperparameters=params,
                    thread_count=thread_count,
                    iterations=int(params["iterations"]),
                    random_seed=seed,
                    early_stopping_rounds=150,
                    use_best_model=True,
                )
                pool = make_quantity_pool(validation, contract, names, validation["QuantityPurchased"])
                raw = predict_quantity_raw(model, pool)
                projected = project_quantity(raw, minimum)
                metrics = quantity_metrics(validation["QuantityPurchased"], projected, raw=raw, minimum=minimum)
                fold_rows.append({"fold": fold_number, "best_iteration": best_iteration, **metrics})
                trial.report(float(metrics["rmse"]), step=fold_number)
            mean_rmse = float(np.mean([row["rmse"] for row in fold_rows]))
            record: dict[str, Any] = {
                "trial_number": int(trial.number),
                "trial": int(trial.number),
                "parameters": json.dumps({**params, "loss_function": loss, "bootstrap_type": "Bayesian"}, sort_keys=True),
                "loss": loss,
                "fold_1_rmse": fold_rows[0]["rmse"], "fold_2_rmse": fold_rows[1]["rmse"], "fold_3_rmse": fold_rows[2]["rmse"],
                "fold_1_mae": fold_rows[0]["mae"], "fold_2_mae": fold_rows[1]["mae"], "fold_3_mae": fold_rows[2]["mae"],
                "fold_1_poisson_deviance": fold_rows[0]["mean_poisson_deviance"], "fold_2_poisson_deviance": fold_rows[1]["mean_poisson_deviance"], "fold_3_poisson_deviance": fold_rows[2]["mean_poisson_deviance"],
                "fold_1_r2": fold_rows[0]["r2"], "fold_2_r2": fold_rows[1]["r2"], "fold_3_r2": fold_rows[2]["r2"],
                "mean_rmse": mean_rmse,
                "std_rmse": float(np.std([row["rmse"] for row in fold_rows], ddof=0)),
                "mean_mae": float(np.mean([row["mae"] for row in fold_rows])),
                "mean_poisson_deviance": float(np.mean([row["mean_poisson_deviance"] for row in fold_rows if row["mean_poisson_deviance"] is not None])),
                "mean_r2": float(np.mean([row["r2"] for row in fold_rows if row["r2"] is not None])),
                "best_iteration_fold_1": fold_rows[0]["best_iteration"], "best_iteration_fold_2": fold_rows[1]["best_iteration"], "best_iteration_fold_3": fold_rows[2]["best_iteration"],
                "mean_effective_trees": float(np.mean([row["best_iteration"] + 1 for row in fold_rows])),
                "depth": int(params["depth"]),
                "duration_seconds": float(time.perf_counter() - started),
                "state": "COMPLETE",
            }
            records[int(trial.number)] = record
            return mean_rmse
        except Exception:
            records[int(trial.number)] = {"trial_number": int(trial.number), "trial": int(trial.number), "parameters": json.dumps(params, sort_keys=True), "loss": loss, "duration_seconds": float(time.perf_counter() - started), "state": "FAIL"}
            raise

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed), pruner=optuna.pruners.NopPruner())
    study.optimize(objective, n_trials=int(n_trials), n_jobs=1, show_progress_bar=False, gc_after_trial=True)
    frame = pd.DataFrame([records[number] for number in sorted(records)])
    completed = frame[frame["state"] == "COMPLETE"].copy()
    if completed.empty:
        raise RuntimeError("Quantity HPO produced no completed trials")
    best = float(completed["mean_rmse"].min())
    eligible = completed[completed["mean_rmse"] <= best + 0.002].copy()
    eligible = eligible.sort_values(["std_rmse", "mean_poisson_deviance", "mean_mae", "depth", "mean_effective_trees", "trial_number"], kind="mergesort")
    chosen = eligible.iloc[0]
    selected = json.loads(str(chosen["parameters"]))
    selected.pop("loss_function", None)
    selected.pop("bootstrap_type", None)
    summary = {
        "requested_trials": int(n_trials),
        "completed_trials": int((frame["state"] == "COMPLETE").sum()),
        "failed_trials": int((frame["state"] == "FAIL").sum()),
        "pruned_trials": int((frame["state"] == "PRUNED").sum()) if "state" in frame else 0,
        "loss": loss,
        "best_mean_rmse": best,
        "stability_tolerance": 0.002,
        "eligible_trial_numbers": [int(value) for value in eligible["trial_number"].tolist()],
        "selected_trial_number": int(chosen["trial_number"]),
        "selected_mean_rmse": float(chosen["mean_rmse"]),
        "selected_std_rmse": float(chosen["std_rmse"]),
        "selection_tie_break": "within 0.002 of best: lower RMSE fold std, lower Poisson deviance, lower MAE, shallower depth, fewer effective trees, trial number",
    }
    return frame, summary, {"parameters": selected, "trial": int(chosen["trial_number"])}


def adoption_gate(baseline: dict[str, Any], advanced: dict[str, Any]) -> dict[str, Any]:
    """Apply the predeclared validation materiality thresholds exactly."""

    rmse_delta = float(baseline["rmse"]) - float(advanced["rmse"])
    poisson_delta = float(baseline["mean_poisson_deviance"]) - float(advanced["mean_poisson_deviance"])
    mae_delta = float(baseline["mae"]) - float(advanced["mae"])
    damage = (
        rmse_delta < -ADOPTION_RMSE_DAMAGE
        or poisson_delta < -ADOPTION_POISSON_DAMAGE
        or mae_delta < -ADOPTION_MAE_DAMAGE
    )
    material_improvement = rmse_delta >= ADOPTION_RMSE_IMPROVEMENT or poisson_delta >= ADOPTION_POISSON_IMPROVEMENT
    eligible = bool(material_improvement and not damage)
    return {
        "eligible": eligible,
        "rmse_improvement": rmse_delta,
        "poisson_deviance_improvement": poisson_delta,
        "mae_improvement": mae_delta,
        "material_improvement": material_improvement,
        "material_damage": damage,
        "thresholds": {
            "rmse_improvement": ADOPTION_RMSE_IMPROVEMENT,
            "poisson_improvement": ADOPTION_POISSON_IMPROVEMENT,
            "rmse_damage": ADOPTION_RMSE_DAMAGE,
            "poisson_damage": ADOPTION_POISSON_DAMAGE,
            "mae_damage": ADOPTION_MAE_DAMAGE,
        },
        "decision": "CATBOOST" if eligible else "CONSTANT_MEAN",
    }


def integrated_safety_gate(mean_metrics: dict[str, Any], advanced_metrics: dict[str, Any]) -> dict[str, Any]:
    rmse_worse = float(advanced_metrics["rmse"]) - float(mean_metrics["rmse"])
    poisson_worse = float(advanced_metrics["mean_poisson_deviance"]) - float(mean_metrics["mean_poisson_deviance"])
    triggered = rmse_worse > 0.002 and poisson_worse > 0.002
    return {"triggered": bool(triggered), "rmse_worse": rmse_worse, "poisson_worse": poisson_worse, "threshold": 0.002, "decision": "CONSTANT_MEAN" if triggered else "UNCHANGED"}


__all__ = [
    "LOSSES",
    "screen_quantity_feature_families",
    "select_quantity_feature_loss",
    "run_quantity_hpo",
    "adoption_gate",
    "integrated_safety_gate",
]
