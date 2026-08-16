from __future__ import annotations

import json
import time
from typing import Any, Iterable

import numpy as np
import optuna
import pandas as pd
from catboost import CatBoostClassifier

from models.catboost_data import FeatureFamily, make_catboost_pool
from models.catboost_purchase import catboost_parameters
from validation.metrics import purchase_metrics


SCREENING_PARAMETERS = {
    "learning_rate": 0.05,
    "depth": 6,
    "l2_leaf_reg": 5.0,
    "random_strength": 1.0,
    "bagging_temperature": 1.0,
    "border_count": 128,
}


def _metric_row(family: FeatureFamily, fold: int, metrics: dict[str, Any], best_iteration: int, fit_seconds: float, prediction_seconds: float) -> dict[str, Any]:
    return {
        "row_type": "fold",
        "family": family.name,
        "groups": "+".join(family.groups) if family.groups else "CORE",
        "feature_count": len(family.feature_names),
        "fold": int(fold),
        "roc_auc": metrics.get("roc_auc"),
        "average_precision": metrics.get("average_precision"),
        "log_loss": metrics.get("log_loss"),
        "brier_score": metrics.get("brier_score"),
        "ece": metrics.get("ece"),
        "top_decile_lift": metrics.get("top_decile_lift"),
        "best_iteration": int(best_iteration),
        "fit_seconds": float(fit_seconds),
        "prediction_seconds": float(prediction_seconds),
    }


def screen_feature_families(
    development: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
    contract: dict[str, Any],
    families: dict[str, FeatureFamily],
    *,
    thread_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for family in families.values():
        for fold_number, (train_indices, validation_indices) in enumerate(folds, start=1):
            train = development.iloc[train_indices]
            validation = development.iloc[validation_indices]
            train_pool = make_catboost_pool(train, contract, family.feature_names, train["PurchasedFlag"])
            validation_pool = make_catboost_pool(validation, contract, family.feature_names, validation["PurchasedFlag"])
            params = catboost_parameters(
                SCREENING_PARAMETERS,
                thread_count=thread_count,
                iterations=1500,
                random_seed=42,
                early_stopping_rounds=150,
                use_best_model=True,
            )
            model = CatBoostClassifier(**params)
            started = time.perf_counter()
            model.fit(train_pool, eval_set=validation_pool)
            fit_seconds = time.perf_counter() - started
            started = time.perf_counter()
            probabilities = model.predict_proba(validation_pool)[:, 1]
            prediction_seconds = time.perf_counter() - started
            metrics = purchase_metrics(validation["PurchasedFlag"], probabilities)
            best_iteration = model.get_best_iteration()
            if best_iteration is None or best_iteration < 0:
                best_iteration = model.tree_count_ - 1
            rows.append(_metric_row(family, fold_number, metrics, best_iteration, fit_seconds, prediction_seconds))
    fold_frame = pd.DataFrame(rows)
    summary_rows: list[dict[str, Any]] = []
    for family_name, group in fold_frame.groupby("family", sort=False):
        family = families[family_name]
        row: dict[str, Any] = {
            "row_type": "aggregate",
            "family": family_name,
            "groups": "+".join(family.groups) if family.groups else "CORE",
            "feature_count": len(family.feature_names),
            "fold": None,
        }
        for metric in ["roc_auc", "average_precision", "log_loss", "brier_score", "ece", "top_decile_lift", "best_iteration", "fit_seconds", "prediction_seconds"]:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            row[f"{metric}_mean"] = float(values.mean()) if len(values) else None
            row[f"{metric}_std"] = float(values.std(ddof=0)) if len(values) else None
            row[f"{metric}_min"] = float(values.min()) if len(values) else None
            row[f"{metric}_max"] = float(values.max()) if len(values) else None
        summary_rows.append(row)
    return fold_frame, pd.DataFrame(summary_rows)


def select_feature_family(
    fold_metrics: pd.DataFrame,
    summary: pd.DataFrame,
    families: dict[str, FeatureFamily],
) -> dict[str, Any]:
    aggregate = summary.set_index("family")
    non_customer = [name for name, family in families.items() if not family.customer_context]
    customer = [name for name, family in families.items() if family.customer_context]

    def simplest(candidates: list[str]) -> str:
        # The primary metric is mean Log Loss.  Near ties use the prescribed
        # Brier threshold, then feature count and family name deterministically.
        best_loss = min(float(aggregate.loc[name, "log_loss_mean"]) for name in candidates)
        loss_tied = [name for name in candidates if float(aggregate.loc[name, "log_loss_mean"]) - best_loss < 0.001]
        best_brier = min(float(aggregate.loc[name, "brier_score_mean"]) for name in loss_tied)
        brier_tied = [name for name in loss_tied if float(aggregate.loc[name, "brier_score_mean"]) - best_brier < 0.0005]
        return sorted(brier_tied, key=lambda name: (len(families[name].feature_names), name))[0]

    best_non_customer = simplest(non_customer)
    baseline_loss = float(aggregate.loc[best_non_customer, "log_loss_mean"])
    baseline_brier = float(aggregate.loc[best_non_customer, "brier_score_mean"])
    customer_eligible: list[str] = []
    for name in customer:
        candidate_loss = float(aggregate.loc[name, "log_loss_mean"])
        candidate_brier = float(aggregate.loc[name, "brier_score_mean"])
        fold = fold_metrics[fold_metrics["family"] == name].sort_values("fold")
        base_fold = fold_metrics[fold_metrics["family"] == best_non_customer].sort_values("fold")
        improvements = (
            base_fold["log_loss"].to_numpy(dtype=float) - fold["log_loss"].to_numpy(dtype=float)
        )
        if candidate_loss <= baseline_loss - 0.002 and candidate_brier <= baseline_brier and int((improvements > 0).sum()) >= 2:
            customer_eligible.append(name)
    candidates = [best_non_customer] + customer_eligible
    selected = simplest(candidates)
    return {
        "selected_feature_family": selected,
        "selected_groups": list(families[selected].groups),
        "selected_feature_count": len(families[selected].feature_names),
        "core_reference_family": "F0_CORE",
        "best_non_customer_family": best_non_customer,
        "customer_context_selected": families[selected].customer_context,
        "customer_context_eligible_families": customer_eligible,
        "selection_policy": {
            "primary_metric": "mean temporal-fold Log Loss",
            "secondary_metric": "mean temporal-fold Brier Score",
            "near_tie_log_loss": 0.001,
            "near_tie_brier": 0.0005,
            "customer_minimum_log_loss_improvement": 0.002,
            "customer_brier_must_not_worsen": True,
            "customer_minimum_improved_folds": 2,
            "tie_break": "prefer lower Brier, then fewer features, then family name",
        },
        "family_feature_counts": {name: len(family.feature_names) for name, family in families.items()},
        "baseline_non_customer_log_loss": baseline_loss,
        "baseline_non_customer_brier": baseline_brier,
    }


def _trial_params(trial: optuna.Trial) -> dict[str, Any]:
    return {
        "learning_rate": trial.suggest_float("learning_rate", 0.015, 0.15, log=True),
        "depth": trial.suggest_int("depth", 4, 10),
        "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 30.0, log=True),
        "random_strength": trial.suggest_float("random_strength", 0.0, 3.0),
        "bagging_temperature": trial.suggest_float("bagging_temperature", 0.0, 5.0),
        "border_count": trial.suggest_categorical("border_count", [64, 128, 254]),
    }


def run_hpo(
    development: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
    contract: dict[str, Any],
    feature_names: Iterable[str],
    *,
    thread_count: int,
    n_trials: int = 60,
    seed: int = 42,
    iterations: int = 3000,
    early_stopping_rounds: int = 150,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    feature_names = tuple(feature_names)
    records: dict[int, dict[str, Any]] = {}

    def objective(trial: optuna.Trial) -> float:
        params = _trial_params(trial)
        started = time.perf_counter()
        fold_rows: list[dict[str, Any]] = []
        try:
            for fold_number, (train_indices, validation_indices) in enumerate(folds, start=1):
                train = development.iloc[train_indices]
                validation = development.iloc[validation_indices]
                train_pool = make_catboost_pool(train, contract, feature_names, train["PurchasedFlag"])
                validation_pool = make_catboost_pool(validation, contract, feature_names, validation["PurchasedFlag"])
                model = CatBoostClassifier(**catboost_parameters(
                    params,
                    thread_count=thread_count,
                    iterations=iterations,
                    random_seed=seed,
                    early_stopping_rounds=early_stopping_rounds,
                    use_best_model=True,
                ))
                model.fit(train_pool, eval_set=validation_pool)
                probabilities = model.predict_proba(validation_pool)[:, 1]
                metrics = purchase_metrics(validation["PurchasedFlag"], probabilities)
                best_iteration = model.get_best_iteration()
                if best_iteration is None or best_iteration < 0:
                    best_iteration = model.tree_count_ - 1
                fold_rows.append({"fold": fold_number, **metrics, "best_iteration": int(best_iteration)})
                trial.report(float(metrics["log_loss"]), step=fold_number)
            log_losses = [float(row["log_loss"]) for row in fold_rows]
            briers = [float(row["brier_score"]) for row in fold_rows]
            aps = [float(row["average_precision"]) for row in fold_rows]
            aucs = [float(row["roc_auc"]) for row in fold_rows]
            record = {
                "trial_number": int(trial.number),
                "parameters": json.dumps({**params, "iterations": iterations, "bootstrap_type": "Bayesian", "loss_function": "Logloss"}, sort_keys=True),
                "fold_1_log_loss": log_losses[0], "fold_2_log_loss": log_losses[1], "fold_3_log_loss": log_losses[2],
                "mean_log_loss": float(np.mean(log_losses)), "std_log_loss": float(np.std(log_losses)),
                "mean_brier": float(np.mean(briers)), "mean_average_precision": float(np.mean(aps)), "mean_roc_auc": float(np.mean(aucs)),
                "best_iteration_fold_1": fold_rows[0]["best_iteration"], "best_iteration_fold_2": fold_rows[1]["best_iteration"], "best_iteration_fold_3": fold_rows[2]["best_iteration"],
                "duration_seconds": float(time.perf_counter() - started), "state": "COMPLETE",
            }
            record["depth"] = int(params["depth"])
            records[int(trial.number)] = record
            trial.set_user_attr("mean_log_loss", record["mean_log_loss"])
            return record["mean_log_loss"]
        except Exception:
            records[int(trial.number)] = {
                "trial_number": int(trial.number),
                "parameters": json.dumps(params, sort_keys=True),
                "duration_seconds": float(time.perf_counter() - started),
                "state": "FAIL",
            }
            raise

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler, pruner=optuna.pruners.NopPruner())
    study.optimize(objective, n_trials=int(n_trials), n_jobs=1, show_progress_bar=False, gc_after_trial=True)
    rows = [records[number] for number in sorted(records)]
    frame = pd.DataFrame(rows)
    completed = frame[frame["state"] == "COMPLETE"].copy() if len(frame) else frame
    if completed.empty:
        raise RuntimeError("HPO produced no completed trials")
    best_loss = float(completed["mean_log_loss"].min())
    eligible = completed[completed["mean_log_loss"] <= best_loss + 0.0005].copy()
    eligible["mean_effective_trees"] = eligible[["best_iteration_fold_1", "best_iteration_fold_2", "best_iteration_fold_3"]].astype(float).add(1).mean(axis=1)
    if "depth" not in eligible:
        eligible["depth"] = eligible["parameters"].map(lambda value: int(json.loads(value).get("depth", 99)))
    eligible = eligible.sort_values(["std_log_loss", "mean_brier", "depth", "mean_effective_trees", "trial_number"], kind="mergesort")
    # Parameters are persisted as JSON, so the deterministic stability choice
    # does not depend on Optuna's internal best-trial ordering.
    chosen = eligible.iloc[0]
    best_parameters = json.loads(str(chosen["parameters"]))
    best_parameters.pop("iterations", None)
    best_parameters.pop("bootstrap_type", None)
    best_parameters.pop("loss_function", None)
    summary = {
        "requested_trials": int(n_trials),
        "completed_trials": int((frame["state"] == "COMPLETE").sum()),
        "failed_trials": int((frame["state"] == "FAIL").sum()),
        "pruned_trials": int((frame["state"] == "PRUNED").sum()) if "state" in frame else 0,
        "best_mean_log_loss": best_loss,
        "stability_tolerance": 0.0005,
        "eligible_trial_numbers": [int(value) for value in eligible["trial_number"].tolist()],
        "selected_trial_number": int(chosen["trial_number"]),
        "selected_mean_log_loss": float(chosen["mean_log_loss"]),
        "selected_std_log_loss": float(chosen["std_log_loss"]),
        "selection_tie_break": "within 0.0005 of best: lower fold std, lower mean Brier, simpler depth, fewer effective trees, trial number",
    }
    return frame, summary, {"parameters": best_parameters, "trial": int(chosen["trial_number"])}

