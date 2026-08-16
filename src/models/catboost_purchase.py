from __future__ import annotations

from typing import Any

from catboost import CatBoostClassifier


def catboost_parameters(
    hyperparameters: dict[str, Any],
    *,
    thread_count: int,
    iterations: int = 3000,
    random_seed: int = 42,
    early_stopping_rounds: int | None = 150,
    use_best_model: bool = True,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "iterations": int(iterations),
        "learning_rate": float(hyperparameters.get("learning_rate", 0.05)),
        "depth": int(hyperparameters.get("depth", 6)),
        "l2_leaf_reg": float(hyperparameters.get("l2_leaf_reg", 5.0)),
        "random_strength": float(hyperparameters.get("random_strength", 1.0)),
        "bootstrap_type": "Bayesian",
        "bagging_temperature": float(hyperparameters.get("bagging_temperature", 1.0)),
        "border_count": int(hyperparameters.get("border_count", 128)),
        "loss_function": "Logloss",
        "eval_metric": "Logloss",
        "random_seed": int(random_seed),
        "thread_count": int(thread_count),
        "task_type": "CPU",
        "class_weights": None,
        "auto_class_weights": None,
        "allow_writing_files": False,
        "verbose": False,
        "use_best_model": bool(use_best_model),
    }
    if early_stopping_rounds is not None:
        params["early_stopping_rounds"] = int(early_stopping_rounds)
    return params


def make_catboost_classifier(
    hyperparameters: dict[str, Any] | None = None,
    *,
    thread_count: int,
    iterations: int = 3000,
    random_seed: int = 42,
    early_stopping_rounds: int | None = 150,
    use_best_model: bool = True,
) -> CatBoostClassifier:
    return CatBoostClassifier(**catboost_parameters(
        hyperparameters or {},
        thread_count=thread_count,
        iterations=iterations,
        random_seed=random_seed,
        early_stopping_rounds=early_stopping_rounds,
        use_best_model=use_best_model,
    ))


