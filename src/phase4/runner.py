from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import optuna
import pandas as pd
import psutil
import sklearn
import yaml
from catboost import CatBoostClassifier, __version__ as catboost_version

from audit.report_builder import source_tree_sha256
from features.feature_contract import load_contract, model_feature_columns
from features.validation import canonical_dataset_hash
from models.calibration import apply_calibrator, calibration_metrics, fit_calibration_candidates, select_calibration_method
from models.catboost_data import (
    FeatureFamily,
    build_feature_families,
    build_purchase_model_features_for_candidate_price,
    categorical_feature_names,
    make_catboost_pool,
    prepare_catboost_frame,
)
from models.catboost_purchase import catboost_parameters, make_catboost_classifier
from models.hyperparameter_search import run_hpo, screen_feature_families, select_feature_family
from models.price_response import PRICE_MULTIPLIERS, candidate_price_predictions, summarize_price_response
from validation.artifacts import prediction_fingerprint, sha256_file, write_json
from validation.compute import configure_thread_environment, detect_compute_environment
from validation.diagnostics import segment_metrics
from validation.metrics import calibration_table, purchase_metrics
from validation.temporal_split import ExpandingWindowSplitter, TemporalSplitError


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/phase4"
MODEL_DIR = ARTIFACTS / "models"
PREDICTION_DIR = ARTIFACTS / "predictions"
BASE_BRANCH = "codex/phase1-data-audit"
BASE_SHA = "5f4a2a8645954edeec24f8ffba4558cbed92f7d4"


def _date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def _config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config/phase4_catboost.yaml").read_text(encoding="utf-8"))


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _split_frame(frame: pd.DataFrame, assignments: pd.DataFrame, split: str) -> pd.DataFrame:
    ids = set(assignments.loc[assignments["split"] == split, "PricingDecisionID"].astype(str))
    return frame.loc[frame["PricingDecisionID"].astype(str).isin(ids)].copy().sort_values(
        ["DecisionTime", "PricingDecisionID"], kind="mergesort"
    ).reset_index(drop=True)


def _verify_upstream(config: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    dataset_path = ROOT / config["phase2"]["dataset_path"]
    split_path = ROOT / config["phase3"]["split_path"]
    if not dataset_path.exists():
        raise RuntimeError("PHASE2_DATASET_MISSING")
    if not split_path.exists():
        raise RuntimeError("PHASE3_SPLIT_ASSIGNMENTS_MISSING")
    frame = pd.read_parquet(dataset_path)
    ordered_columns = [feature["name"] for feature in contract["features"]]
    dataset_hash = canonical_dataset_hash(frame, ordered_columns)
    expected_hash = config["phase2"]["expected_sha256"]
    if dataset_hash != expected_hash:
        raise RuntimeError(f"PHASE2_DATASET_FINGERPRINT_MISMATCH: expected={expected_hash} actual={dataset_hash}")
    if len(frame) != config["phase2"]["expected_rows"]:
        raise RuntimeError("PHASE2_ROW_COUNT_MISMATCH")
    if frame["PricingDecisionID"].duplicated().any() or frame["PricingDecisionID"].nunique() != len(frame):
        raise RuntimeError("PHASE2_PRICING_DECISION_ID_GRAIN_MISMATCH")
    if int(frame["PurchasedFlag"].sum()) != config["phase2"]["expected_purchases"] or int((frame["PurchasedFlag"] == 0).sum()) != config["phase2"]["expected_non_purchases"]:
        raise RuntimeError("PHASE2_TARGET_COUNTS_MISMATCH")

    assignments = pd.read_parquet(split_path)
    expected_assignment_hash = json.loads((ROOT / config["phase3"]["split_summary_path"]).read_text(encoding="utf-8"))["assignment_sha256"]
    assignment_hash = sha256_file(split_path)
    if assignment_hash != expected_assignment_hash:
        raise RuntimeError(f"PHASE3_SPLIT_FINGERPRINT_MISMATCH: expected={expected_assignment_hash} actual={assignment_hash}")
    if set(assignments["PricingDecisionID"].astype(str)) != set(frame["PricingDecisionID"].astype(str)):
        raise RuntimeError("PHASE3_SPLIT_ID_SET_MISMATCH")
    if assignments["PricingDecisionID"].duplicated().any():
        raise RuntimeError("PHASE3_SPLIT_DUPLICATE_ID")
    merged = frame[["PricingDecisionID", "DecisionTime"]].copy()
    merged["PricingDecisionID"] = merged["PricingDecisionID"].astype(str)
    merged = merged.merge(assignments[["PricingDecisionID", "DecisionTime", "split"]].assign(PricingDecisionID=lambda x: x["PricingDecisionID"].astype(str)), on="PricingDecisionID", suffixes=("_data", "_split"), how="left", validate="one_to_one")
    if merged["split"].isna().any():
        raise RuntimeError("PHASE3_SPLIT_ASSIGNMENT_MISSING")
    merged["DecisionTime"] = pd.to_datetime(merged["DecisionTime_data"], errors="raise")
    minimums = merged.groupby("split")["DecisionTime"].min()
    maximums = merged.groupby("split")["DecisionTime"].max()
    if not maximums["train"] < minimums["validation"] or not maximums["validation"] < minimums["test"]:
        raise RuntimeError("PHASE3_TEMPORAL_ORDER_FAILURE")
    expected_health = {
        "train": (24500, 4581, 19919),
        "validation": (5250, 939, 4311),
        "test": (5250, 972, 4278),
    }
    health: dict[str, Any] = {}
    for split, (rows, purchases, non_purchases) in expected_health.items():
        part = frame[frame["PricingDecisionID"].astype(str).isin(set(assignments.loc[assignments["split"] == split, "PricingDecisionID"].astype(str)))]
        actual = (len(part), int(part["PurchasedFlag"].sum()), int((part["PurchasedFlag"] == 0).sum()))
        if actual != (rows, purchases, non_purchases):
            raise RuntimeError(f"PHASE3_SPLIT_HEALTH_MISMATCH: {split} expected={(rows, purchases, non_purchases)} actual={actual}")
        health[split] = {"rows": actual[0], "purchases": actual[1], "non_purchases": actual[2], "start": _date(part["DecisionTime"].min()), "end": _date(part["DecisionTime"].max())}

    fold_manifest_path = ROOT / config["phase3"]["fold_manifest_path"]
    fold_manifest = json.loads(fold_manifest_path.read_text(encoding="utf-8"))
    if len(fold_manifest) != 3:
        raise RuntimeError("PHASE3_FOLD_MANIFEST_MISMATCH")
    for required in [config["phase3"]["validation_metrics_path"], config["phase3"]["test_metrics_path"], config["phase3"]["contract_path"]]:
        if not (ROOT / required).exists():
            raise RuntimeError(f"PHASE3_UPSTREAM_ARTIFACT_MISSING: {required}")
    return {
        "frame": frame,
        "assignments": assignments,
        "dataset_sha256": dataset_hash,
        "split_assignment_sha256": assignment_hash,
        "health": health,
        "fold_manifest": fold_manifest,
        "boundaries": {split: {"start": info["start"], "end": info["end"]} for split, info in health.items()},
    }


def _locked_folds(development: pd.DataFrame, fold_manifest: list[dict[str, Any]]) -> list[tuple[np.ndarray, np.ndarray]]:
    development = development.copy()
    development["DecisionTime"] = pd.to_datetime(development["DecisionTime"], errors="raise")
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for expected in fold_manifest:
        train_end = pd.Timestamp(expected["train_end"])
        validation_start = pd.Timestamp(expected["validation_start"])
        validation_end = pd.Timestamp(expected["validation_end"])
        train_indices = np.flatnonzero((development["DecisionTime"] <= train_end).to_numpy())
        validation_indices = np.flatnonzero(((development["DecisionTime"] >= validation_start) & (development["DecisionTime"] <= validation_end)).to_numpy())
        if len(train_indices) != int(expected["train_rows"]) or len(validation_indices) != int(expected["validation_rows"]):
            raise RuntimeError(f"PHASE3_FOLD_REUSE_MISMATCH: fold {expected['fold']}")
        if development.iloc[train_indices]["DecisionTime"].max() >= development.iloc[validation_indices]["DecisionTime"].min():
            raise RuntimeError("PHASE3_FOLD_CHRONOLOGY_FAILURE")
        folds.append((train_indices, validation_indices))
    return folds


def _fit_with_eval(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    contract: dict[str, Any],
    feature_names: Iterable[str],
    hyperparameters: dict[str, Any],
    *,
    thread_count: int,
    iterations: int = 3000,
    use_best_model: bool = True,
) -> tuple[CatBoostClassifier, np.ndarray, np.ndarray, int, float, float]:
    train_pool = make_catboost_pool(train, contract, feature_names, train["PurchasedFlag"])
    validation_pool = make_catboost_pool(validation, contract, feature_names, validation["PurchasedFlag"])
    model = make_catboost_classifier(
        hyperparameters,
        thread_count=thread_count,
        iterations=iterations,
        random_seed=42,
        early_stopping_rounds=150 if use_best_model else None,
        use_best_model=use_best_model,
    )
    started = time.perf_counter()
    model.fit(train_pool, eval_set=validation_pool if use_best_model else None)
    fit_seconds = time.perf_counter() - started
    started = time.perf_counter()
    native = model.predict_proba(validation_pool)[:, 1]
    raw = np.asarray(model.predict(validation_pool, prediction_type="RawFormulaVal"), dtype=float).reshape(-1)
    prediction_seconds = time.perf_counter() - started
    best_iteration = model.get_best_iteration()
    if best_iteration is None or best_iteration < 0:
        best_iteration = model.tree_count_ - 1
    return model, native, raw, int(best_iteration), fit_seconds, prediction_seconds


def _oof_predictions(
    development: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
    contract: dict[str, Any],
    feature_names: Iterable[str],
    hyperparameters: dict[str, Any],
    *,
    thread_count: int,
    fixed_iterations: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    raw_parts: list[np.ndarray] = []
    native_parts: list[np.ndarray] = []
    label_parts: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    for fold_number, (train_indices, validation_indices) in enumerate(folds, start=1):
        train = development.iloc[train_indices]
        validation = development.iloc[validation_indices]
        if fixed_iterations is None:
            model, native, raw, best_iteration, fit_seconds, prediction_seconds = _fit_with_eval(train, validation, contract, feature_names, hyperparameters, thread_count=thread_count)
        else:
            model, native, raw, best_iteration, fit_seconds, prediction_seconds = _fit_with_eval(train, validation, contract, feature_names, hyperparameters, thread_count=thread_count, iterations=fixed_iterations, use_best_model=False)
        raw_parts.append(raw)
        native_parts.append(native)
        label_parts.append(validation["PurchasedFlag"].to_numpy(dtype=int))
        rows.append({"fold": fold_number, "best_iteration": best_iteration, "fit_seconds": fit_seconds, "prediction_seconds": prediction_seconds, **purchase_metrics(validation["PurchasedFlag"], native)})
    return np.concatenate(raw_parts), np.concatenate(native_parts), np.concatenate(label_parts), rows


def _segment_metrics(frame: pd.DataFrame, labels: np.ndarray, probabilities: np.ndarray, split: str, minimum_support: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in ["Channel", "Season", "RegionID", "CategoryID", "StoreType"]:
        for value, group in frame.groupby(column, dropna=False, sort=True):
            if len(group) < minimum_support:
                continue
            indices = group.index.to_numpy()
            metrics = purchase_metrics(labels[indices], probabilities[indices])
            rows.append({"split": split, "segment": column, "value": "__MISSING__" if pd.isna(value) else str(value), "support": int(len(indices)), **metrics})
    return pd.DataFrame(rows)


def _write_frozen_spec(feature_family: FeatureFamily, hyperparameters: dict[str, Any], iterations: int, calibration_method: str, contract: dict[str, Any], compute: dict[str, Any]) -> dict[str, Any]:
    features = list(feature_family.feature_names)
    categorical = categorical_feature_names(contract, features)
    numeric = [name for name in features if name not in set(categorical)]
    payload = {
        "phase2_dataset_sha256": "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2",
        "phase3_split_assignment_sha256": "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d",
        "feature_set_name": feature_family.name,
        "ordered_feature_names": features,
        "categorical_features": categorical,
        "numeric_features": numeric,
        "hyperparameters": {**hyperparameters, "iterations": int(iterations), "bootstrap_type": "Bayesian", "loss_function": "Logloss", "task_type": "CPU", "class_weights": None, "auto_class_weights": None},
        "random_seed": 42,
        "thread_count": int(compute["usable_threads"]),
        "selected_iteration_count": int(iterations),
        "calibration_method": calibration_method,
        "training_policy": "final model fit on TRAIN+VALIDATION with frozen iterations; TEST is not an eval_set",
        "candidate_price_adapter_version": "phase2.build_price_dependent_features.v1",
        "catboost_version": catboost_version,
    }
    payload["frozen_model_spec_sha256"] = _json_hash(payload)
    write_json(ARTIFACTS / "frozen_model_spec.json", payload)
    return payload


def _require_frozen_spec() -> dict[str, Any]:
    path = ARTIFACTS / "frozen_model_spec.json"
    if not path.exists():
        raise RuntimeError("FROZEN_MODEL_SPEC_REQUIRED_BEFORE_TEST")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.get("frozen_model_spec_sha256")
    actual_payload = dict(payload)
    actual_payload.pop("frozen_model_spec_sha256", None)
    if expected != _json_hash(actual_payload):
        raise RuntimeError("FROZEN_MODEL_SPEC_HASH_MISMATCH")
    return payload


def _write_phase4_contract(feature_family: FeatureFamily, hyperparameters: dict[str, Any], iterations: int, calibration_method: str, contract: dict[str, Any], compute: dict[str, Any]) -> None:
    path = ROOT / "contracts/phase4_purchase_model_contract_v1.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    features = list(feature_family.feature_names)
    categorical = categorical_feature_names(contract, features)
    payload["selected_feature_family"] = feature_family.name
    payload["categorical_features"] = categorical
    payload["numeric_features"] = [name for name in features if name not in set(categorical)]
    payload["selected_hyperparameters"] = {**hyperparameters, "iterations": 3000, "task_type": "CPU", "thread_count": int(compute["usable_threads"]), "class_weights": None, "auto_class_weights": None}
    payload["selected_iterations"] = int(iterations)
    payload["selected_calibration"] = calibration_method
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_reports(
    *,
    upstream: dict[str, Any],
    compute: dict[str, Any],
    selection: dict[str, Any],
    screening_summary: pd.DataFrame,
    hpo_summary: dict[str, Any],
    hpo_params: dict[str, Any],
    fold_rows: list[dict[str, Any]],
    validation: dict[str, Any],
    test: dict[str, Any],
    calibration_rows: list[dict[str, Any]],
    calibration_selection: dict[str, Any],
    parity: dict[str, Any],
    price_summary: dict[str, Any],
    reproducibility: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    docs = ROOT / "docs"
    selection_rows = screening_summary.to_dict("records")
    screening_text = "\n".join(
        f"| {row.get('family')} | {row.get('feature_count')} | {row.get('log_loss_mean', row.get('log_loss')):.6f} | {row.get('brier_score_mean', row.get('brier_score')):.6f} | {row.get('average_precision_mean', row.get('average_precision')):.6f} | {row.get('roc_auc_mean', row.get('roc_auc')):.6f} |"
        for row in selection_rows
    )
    feature_report = f"""# Phase 4 Feature Selection Report

## Screening protocol

Feature-family screening used only the three locked expanding-window folds inside TRAIN. Official VALIDATION and TEST were not accessed. The CatBoost screening configuration was fixed (`iterations=1500`, `learning_rate=0.05`, `depth=6`, `l2_leaf_reg=5`, Bayesian bootstrap, seed 42, early stopping 150) and was not tuned.

## Results

| Family | Features | Mean Log Loss | Mean Brier | Mean AP | Mean ROC-AUC |
|---|---:|---:|---:|---:|---:|
{screening_text}

## Decision

- Selected family: **{selection['selected_feature_family']}**
- Selected feature count: **{selection['selected_feature_count']}**
- Non-customer reference: **{selection['best_non_customer_family']}**
- Customer context selected: **{selection['customer_context_selected']}**
- Customer-eligible families: `{selection['customer_context_eligible_families']}`
- CORE remained a reference candidate throughout.

The primary criterion was mean temporal-fold Log Loss, followed by Brier Score, then AP, AUC, and stability. Near ties were resolved in favor of the simpler family when Log Loss differed by less than 0.001 and Brier by less than 0.0005. Customer context required at least 0.002 mean Log Loss improvement, no Brier deterioration, and improvement in at least two folds.

## Leakage and eligibility

All feature names came from the Phase 2 contract. Conditional context was admitted only through explicit Phase 4 groups. PII, identifiers, targets, inventory, pricing-rule outputs, optimizer-only outputs, and post-outcome columns were rejected. CatBoost used native categorical features; no one-hot, target, mean, or frequency encoding was used.
"""
    (docs / "PHASE4_FEATURE_SELECTION_REPORT.md").write_text(feature_report, encoding="utf-8")

    def metric_line(source: dict[str, Any], key: str) -> str:
        value = source.get(key)
        return "NA" if value is None else f"{float(value):.6f}"

    model_report = f"""# Phase 4 CatBoost Purchase Probability Model Report

## Model search

Optuna used a serial `TPESampler(seed=42)` with `n_jobs=1`; each trial used `{compute['usable_threads']}` CatBoost CPU threads. The objective was mean Log Loss over the three TRAIN expanding folds. `{hpo_summary['completed_trials']}` trials completed, `{hpo_summary['failed_trials']}` failed, and `{hpo_summary['pruned_trials']}` were pruned. The selected trial was `{hpo_summary['selected_trial_number']}` with mean Log Loss `{hpo_summary['selected_mean_log_loss']:.6f}` and fold standard deviation `{hpo_summary['selected_std_log_loss']:.6f}`.

Selected parameters:

```json
{json.dumps(hpo_params, indent=2, sort_keys=True)}
```

## Temporal-fold stability

The selected specification was re-evaluated on all three TRAIN folds. Full fold rows and aggregate summaries are in `artifacts/phase4/temporal_fold_metrics.csv` and `temporal_fold_summary.json`.

## TRAIN → VALIDATION

| Model | ROC-AUC | AP | Log Loss | Brier | ECE | Top-decile lift |
|---|---:|---:|---:|---:|---:|---:|
| Dummy prior | {metric_line(validation['dummy'], 'roc_auc')} | {metric_line(validation['dummy'], 'average_precision')} | {metric_line(validation['dummy'], 'log_loss')} | {metric_line(validation['dummy'], 'brier_score')} | {metric_line(validation['dummy'], 'ece')} | {metric_line(validation['dummy'], 'top_decile_lift')} |
| Phase 3 logistic | {metric_line(validation['logistic'], 'roc_auc')} | {metric_line(validation['logistic'], 'average_precision')} | {metric_line(validation['logistic'], 'log_loss')} | {metric_line(validation['logistic'], 'brier_score')} | {metric_line(validation['logistic'], 'ece')} | {metric_line(validation['logistic'], 'top_decile_lift')} |
| CatBoost native | {metric_line(validation['native'], 'roc_auc')} | {metric_line(validation['native'], 'average_precision')} | {metric_line(validation['native'], 'log_loss')} | {metric_line(validation['native'], 'brier_score')} | {metric_line(validation['native'], 'ece')} | {metric_line(validation['native'], 'top_decile_lift')} |
| CatBoost official ({calibration_selection['selected_method']}) | {metric_line(validation['official'], 'roc_auc')} | {metric_line(validation['official'], 'average_precision')} | {metric_line(validation['official'], 'log_loss')} | {metric_line(validation['official'], 'brier_score')} | {metric_line(validation['official'], 'ece')} | {metric_line(validation['official'], 'top_decile_lift')} |

## Calibration

Calibration candidates were trained from temporally valid TRAIN OOF predictions only. Candidate validation scores are in `artifacts/phase4/calibration_validation.csv`; selection priority was Log Loss, Brier, ECE, then simplicity. Selected method: **{calibration_selection['selected_method']}**. Reason: {calibration_selection['reason']}

## Candidate-price diagnostics

Historical AppliedPrice parity violations: **{parity['violations']}**. The adapter reuses `features.price_features.build_price_dependent_features`; CurrentPrice, BasePrice, history, behavior, and seasonality remain fixed during scenario inference. Price-response stress testing is predictive scenario sensitivity, not causal elasticity.

```json
{json.dumps(price_summary, indent=2, sort_keys=True)}
```

## Feature importance

Native CatBoost global importance is in `artifacts/phase4/feature_importance.csv`. It is a diagnostic, not the Phase 9 explainability product.

## Holdout discipline

The model, feature family, hyperparameters, iteration count, calibration method, and inference adapter were frozen before TEST. The final CatBoost was fit on TRAIN+VALIDATION with no TEST eval set. `test_access_manifest.json` records the single final benchmark access.

## TEST

| Metric | Value |
|---|---:|
| ROC-AUC | {metric_line(test['official'], 'roc_auc')} |
| AP | {metric_line(test['official'], 'average_precision')} |
| Log Loss | {metric_line(test['official'], 'log_loss')} |
| Brier | {metric_line(test['official'], 'brier_score')} |
| ECE | {metric_line(test['official'], 'ece')} |
| Top-decile lift | {metric_line(test['official'], 'top_decile_lift')} |

## Reproducibility

Maximum absolute validation probability delta across two identical TRAIN→VALIDATION fits: **{reproducibility['max_probability_delta']:.12g}**; status: **{reproducibility['status']}**. Best iterations: `{reproducibility['best_iteration_first']}` and `{reproducibility['best_iteration_second']}`.
"""
    (docs / "PHASE4_CATBOOST_MODEL_REPORT.md").write_text(model_report, encoding="utf-8")

    fold_summary = {}
    fold_frame = pd.DataFrame(fold_rows)
    for name in ["log_loss", "brier_score", "average_precision", "roc_auc", "ece"]:
        values = pd.to_numeric(fold_frame[name], errors="coerce")
        fold_summary[name] = {"mean": float(values.mean()), "std": float(values.std(ddof=0)), "min": float(values.min()), "max": float(values.max())}
    acceptance = f"""# Phase 4 Acceptance Report

## 1. Executive verdict

**{manifest['result']}** — CatBoost purchase-probability feasibility gate.

## 2. Upstream verification

- Base branch: `{manifest['base_branch']}`
- Base SHA: `{manifest['base_git_sha']}`
- Phase 2 dataset fingerprint: `{upstream['dataset_sha256']}`
- Phase 3 split fingerprint: `{upstream['split_assignment_sha256']}`
- Rows: **35,000**; purchases: **6,492**; non-purchases: **28,508**
- Split health: train 24,500 / validation 5,250 / test 5,250; target counts and chronology matched the accepted Phase 3 contract.

## 3. Compute environment

- Physical cores: **{compute['detected_physical_cores']}**
- Logical threads: **{compute['detected_logical_threads']}**
- CatBoost threads: **{compute['usable_threads']}**
- Optuna jobs: **1**
- Nested parallelism: **false**

## 4–5. Feature-family screening and selected family

The three TRAIN-only expanding-fold screening results are in `feature_family_screening.csv`. Selected family: **{selection['selected_feature_family']}**; CORE remained a candidate. Customer context selected: **{selection['customer_context_selected']}** because the predefined stronger bar was {'met' if selection['customer_context_selected'] else 'not met'}.

## 6. Hyperparameter optimization

`hpo_trials.csv` contains every trial. Completed: **{hpo_summary['completed_trials']}**; failed: **{hpo_summary['failed_trials']}**; pruned: **{hpo_summary['pruned_trials']}**. Best mean fold Log Loss: **{hpo_summary['best_mean_log_loss']:.6f}**; selected fold std: **{hpo_summary['selected_std_log_loss']:.6f}**. Optuna used TPE seed 42, serial trials, and a bounded search space.

## 7. Temporal-fold results

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| Log Loss | {fold_summary['log_loss']['mean']:.6f} | {fold_summary['log_loss']['std']:.6f} | {fold_summary['log_loss']['min']:.6f} | {fold_summary['log_loss']['max']:.6f} |
| Brier | {fold_summary['brier_score']['mean']:.6f} | {fold_summary['brier_score']['std']:.6f} | {fold_summary['brier_score']['min']:.6f} | {fold_summary['brier_score']['max']:.6f} |
| AP | {fold_summary['average_precision']['mean']:.6f} | {fold_summary['average_precision']['std']:.6f} | {fold_summary['average_precision']['min']:.6f} | {fold_summary['average_precision']['max']:.6f} |
| ROC-AUC | {fold_summary['roc_auc']['mean']:.6f} | {fold_summary['roc_auc']['std']:.6f} | {fold_summary['roc_auc']['min']:.6f} | {fold_summary['roc_auc']['max']:.6f} |
| ECE | {fold_summary['ece']['mean']:.6f} | {fold_summary['ece']['std']:.6f} | {fold_summary['ece']['min']:.6f} | {fold_summary['ece']['max']:.6f} |

## 8–12. Final validation and calibration

The official validation model used TRAIN with VALIDATION as eval_set and early stopping. Native and calibrated metrics are in `validation_metrics.json`; 10-bin calibration is in `validation_calibration_table.csv`. Calibration was trained from TRAIN OOF predictions only and frozen before TEST.

## 13–15. Candidate-price parity, stress test, and importance

- Parity violations: **{parity['violations']}**
- Flat-response rate: **{price_summary['flat_response_rate']:.6f}**
- Non-monotonic scenario rate: **{price_summary['non_monotonic_sequence_rate']:.6f}**
- Significant upward-violation rate: **{price_summary['significant_upward_violation_rate']:.6f}**
- Median -10% → current probability delta: **{price_summary['median_probability_change_minus_10pct_to_current']:.6f}**
- Median current → +10% probability delta: **{price_summary['median_probability_change_current_to_plus_10pct']:.6f}**

These are model-implied predictive responses, not causal price elasticity.

## 16. Frozen model specification

The frozen spec was written and hashed before TEST. Feature count: **{len(manifest['feature_names'])}**; categorical feature count: **{len(manifest['categorical_features'])}**; iterations: **{manifest['selected_iterations']}**; calibration: **{manifest['selected_calibration']}**; frozen spec SHA: `{manifest['frozen_model_spec_sha256']}`.

## 17–19. Holdout TEST access and diagnostics

TEST was accessed once after all model choices were frozen. Test metrics and supported segment diagnostics are in `test_metrics.json` and `segment_metrics.csv`. No TEST label was used for feature selection, HPO, calibration selection, or retraining.

## 20. Reproducibility

{json.dumps(reproducibility, indent=2, sort_keys=True)}

## 21. Compute performance

Timings are in `compute_environment.json`, `compute_benchmark.json`, and the per-fold screening/HPO artifacts.

## 22–23. Known limitations and downstream risks

Upstream limitations remain: sparse competitor history, sparse Product×Store history, sparse promotion coverage, quantity concentration, temporal missingness drift, weak Phase 3 linear purchase signal, and observational/synthetic data that do not identify causal elasticity. Phase 5 must not treat this model as proof of causal demand response; Phase 6 must use candidate-price diagnostics as scenario sensitivity only.

## 24. Verdict

**{manifest['result']}**

Warnings:

{chr(10).join(f'- {warning}' for warning in manifest['warnings']) if manifest['warnings'] else '- None'}

Major blockers: **{len(manifest['major_blockers'])}**

{chr(10).join(f'- {blocker}' for blocker in manifest['major_blockers']) if manifest['major_blockers'] else '- None'}

## 25. Recommendation

**{manifest['recommendation']}**
"""
    (docs / "PHASE4_ACCEPTANCE_REPORT.md").write_text(acceptance, encoding="utf-8")


def _run_tests() -> dict[str, Any]:
    path = ARTIFACTS / "test_results.json"
    env = os.environ.copy()
    env["TEST_EVIDENCE_PATH"] = str(path)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, env=env, check=False)
    if not path.exists():
        raise RuntimeError("PHASE4_TEST_EVIDENCE_MISSING")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["runner_exit_code"] = int(result.returncode)
    if result.returncode != 0 or evidence.get("failed", 0) != 0 or evidence.get("status") != "PASS":
        raise RuntimeError(f"PHASE4_TESTS_FAILED: {evidence}")
    return evidence


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTION_DIR.mkdir(parents=True, exist_ok=True)
    config = _config()
    compute = configure_thread_environment(detect_compute_environment(config["compute"]["max_threads"]))
    compute.update({
        "catboost_thread_count": compute["usable_threads"],
        "optuna_parallel_jobs": config["compute"]["optuna_jobs"],
        "nested_parallelism": False,
        "physical_cores": compute["detected_physical_cores"],
        "logical_threads": compute["detected_logical_threads"],
    })
    random_seed = int(config["compute"]["random_seed"])
    np.random.seed(random_seed)
    started_at = datetime.now(timezone.utc)
    blockers: list[str] = []
    warnings: list[str] = []
    try:
        tests = _run_tests()
        contract = load_contract(ROOT / config["phase2"]["contract_path"])
        upstream = _verify_upstream(config, contract)
        frame = upstream["frame"]
        assignments = upstream["assignments"]
        train = _split_frame(frame, assignments, "train")
        validation = _split_frame(frame, assignments, "validation")
        development = train.sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)
        folds = _locked_folds(development, upstream["fold_manifest"])
        families = build_feature_families(contract)
        if os.environ.get("PHASE4_REUSE_SCREENING") == "1" and (ARTIFACTS / "feature_family_screening.csv").exists():
            screening_output = pd.read_csv(ARTIFACTS / "feature_family_screening.csv")
            fold_screening = screening_output[screening_output["row_type"] == "fold"].copy()
            screening_summary = screening_output[screening_output["row_type"] == "aggregate"].copy()
            selection = json.loads((ARTIFACTS / "feature_family_selection.json").read_text(encoding="utf-8"))
        else:
            fold_screening, screening_summary = screen_feature_families(development, folds, contract, families, thread_count=compute["usable_threads"])
            screening_output = pd.concat([fold_screening, screening_summary], ignore_index=True, sort=False)
            screening_output.to_csv(ARTIFACTS / "feature_family_screening.csv", index=False)
            selection = select_feature_family(fold_screening, screening_summary, families)
            write_json(ARTIFACTS / "feature_family_selection.json", selection)
        selected_family = families[selection["selected_feature_family"]]
        hpo_trials = int(os.environ.get("PHASE4_HPO_TRIALS", config["compute"]["hpo_trials"]))
        if os.environ.get("PHASE4_REUSE_HPO") == "1" and (ARTIFACTS / "hpo_trials.csv").exists():
            hpo_frame = pd.read_csv(ARTIFACTS / "hpo_trials.csv")
            hpo_summary = json.loads((ARTIFACTS / "hpo_summary.json").read_text(encoding="utf-8"))
            saved_hpo = json.loads((ARTIFACTS / "best_hyperparameters.json").read_text(encoding="utf-8"))
            hpo_params = saved_hpo["parameters"]
            hpo_choice = {"parameters": hpo_params, "trial": saved_hpo["trial_number"]}
        else:
            hpo_frame, hpo_summary, hpo_choice = run_hpo(development, folds, contract, selected_family.feature_names, thread_count=compute["usable_threads"], n_trials=hpo_trials, seed=random_seed)
            hpo_frame.to_csv(ARTIFACTS / "hpo_trials.csv", index=False)
            hpo_params = hpo_choice["parameters"]
            write_json(ARTIFACTS / "hpo_summary.json", hpo_summary)
            write_json(ARTIFACTS / "best_hyperparameters.json", {"feature_family": selected_family.name, "trial_number": hpo_choice["trial"], "parameters": hpo_params, "iterations_max": config["compute"]["max_iterations"]})

        # Official validation is the first access after TRAIN-only screening/HPO.
        validation_model, native_validation, raw_validation, best_iteration, validation_fit_seconds, validation_prediction_seconds = _fit_with_eval(train, validation, contract, selected_family.feature_names, hpo_params, thread_count=compute["usable_threads"], iterations=config["compute"]["max_iterations"])
        validation_native_metrics = purchase_metrics(validation["PurchasedFlag"], native_validation)
        train_oof_raw, train_oof_native, train_oof_labels, oof_rows = _oof_predictions(development, folds, contract, selected_family.feature_names, hpo_params, thread_count=compute["usable_threads"])
        # These are the final selected-specification temporal-fold metrics,
        # retained separately from the family-screening rows.
        fold_rows = oof_rows
        calibrators = fit_calibration_candidates(train_oof_raw, train_oof_native, train_oof_labels)
        calibration_rows = []
        calibration_probabilities: dict[str, np.ndarray] = {}
        for method, calibrator in calibrators.items():
            probabilities = apply_calibrator(method, calibrator, raw_validation, native_validation)
            calibration_probabilities[method] = probabilities
            calibration_rows.append(calibration_metrics(validation["PurchasedFlag"].to_numpy(dtype=int), probabilities, method))
        calibration_selection = select_calibration_method(calibration_rows)
        selected_calibration = calibration_selection["selected_method"]
        official_validation = calibration_probabilities[selected_calibration]
        validation_calibration_table = calibration_table(validation["PurchasedFlag"], official_validation, bins=config["evaluation"]["calibration_bins"])
        validation_calibration_table.to_csv(ARTIFACTS / "validation_calibration_table.csv", index=False)
        pd.DataFrame(calibration_rows).to_csv(ARTIFACTS / "calibration_validation.csv", index=False)
        pd.DataFrame(calibration_rows).to_csv(ARTIFACTS / "calibration_candidates.csv", index=False)
        write_json(ARTIFACTS / "calibration_selection.json", {**calibration_selection, "oof_rows": int(len(train_oof_labels)), "oof_fold_metrics": oof_rows})
        validation_metrics = {"dummy": json.loads((ROOT / config["phase3"]["validation_metrics_path"]).read_text(encoding="utf-8"))["purchase_dummy_prior"], "logistic": json.loads((ROOT / config["phase3"]["validation_metrics_path"]).read_text(encoding="utf-8"))["purchase_logistic_core"], "native": validation_native_metrics, "official": purchase_metrics(validation["PurchasedFlag"], official_validation), "calibration_candidates": calibration_rows, "best_iteration": int(best_iteration), "best_score": float(validation_native_metrics["log_loss"]), "fit_seconds": validation_fit_seconds, "prediction_seconds": validation_prediction_seconds}
        write_json(ARTIFACTS / "validation_metrics.json", validation_metrics)

        # Reproducibility is checked before freezing the spec and before TEST.
        validation_model_2, native_validation_2, raw_validation_2, best_iteration_2, _, _ = _fit_with_eval(train, validation, contract, selected_family.feature_names, hpo_params, thread_count=compute["usable_threads"], iterations=config["compute"]["max_iterations"])
        official_validation_2 = apply_calibrator(selected_calibration, calibrators[selected_calibration], raw_validation_2, native_validation_2)
        reproducibility = {
            "max_probability_delta": float(np.max(np.abs(official_validation - official_validation_2))),
            "native_max_probability_delta": float(np.max(np.abs(native_validation - native_validation_2))),
            "best_iteration_first": int(best_iteration),
            "best_iteration_second": int(best_iteration_2),
            "metrics_first": purchase_metrics(validation["PurchasedFlag"], official_validation),
            "metrics_second": purchase_metrics(validation["PurchasedFlag"], official_validation_2),
            "tolerance": config["evaluation"]["probability_tolerance"],
            "status": "PASS" if float(np.max(np.abs(official_validation - official_validation_2))) <= float(config["evaluation"]["probability_tolerance"]) and best_iteration == best_iteration_2 else "BLOCKED",
        }
        write_json(ARTIFACTS / "reproducibility.json", reproducibility)
        if reproducibility["status"] != "PASS":
            blockers.append("REPRODUCIBILITY_FAILURE")

        # Candidate-price parity and stress testing happen before TEST access.
        original_prepared = prepare_catboost_frame(validation, contract, selected_family.feature_names)
        candidate_prepared = build_purchase_model_features_for_candidate_price(validation, validation["AppliedPrice"].to_numpy(), contract, selected_family.feature_names)
        parity_differences = []
        categorical_selected = set(categorical_feature_names(contract, selected_family.feature_names))
        for column in selected_family.feature_names:
            left = original_prepared[column]
            right = candidate_prepared[column]
            if column in categorical_selected:
                difference = int((left.to_numpy() != right.to_numpy()).sum())
            else:
                difference = int((~np.isclose(left.to_numpy(dtype=float), right.to_numpy(dtype=float), equal_nan=True, atol=1e-12, rtol=1e-12)).sum())
            if difference:
                parity_differences.append({"feature": column, "violations": difference})
        historical_pool = make_catboost_pool(validation, contract, selected_family.feature_names)
        candidate_pool = make_catboost_pool(validation.assign(**{column: candidate_prepared[column].to_numpy() for column in selected_family.feature_names}), contract, selected_family.feature_names)
        original_pred = validation_model.predict_proba(historical_pool)[:, 1]
        candidate_pred = validation_model.predict_proba(candidate_pool)[:, 1]
        parity = {"rows_checked": int(len(validation)), "feature_violations": parity_differences, "violations": int(sum(item["violations"] for item in parity_differences)), "max_prediction_delta": float(np.max(np.abs(original_pred - candidate_pred))), "prediction_tolerance": 1e-10, "status": "PASS" if not parity_differences and float(np.max(np.abs(original_pred - candidate_pred))) <= 1e-10 else "BLOCKED"}
        write_json(ARTIFACTS / "candidate_price_parity.json", parity)
        if parity["status"] != "PASS":
            blockers.append("TRAIN_INFERENCE_FEATURE_PARITY_FAILED")
        # `candidate_prepared` is already a prepared frame; use a Pool for the
        # native categorical schema on each scenario.
        def predict_candidates(_model: Any, prepared: pd.DataFrame) -> np.ndarray:
            pool = make_catboost_pool(validation.assign(**{column: prepared[column].to_numpy() for column in selected_family.feature_names}), contract, selected_family.feature_names)
            raw = np.asarray(_model.predict(pool, prediction_type="RawFormulaVal"), dtype=float).reshape(-1)
            native = _model.predict_proba(pool)[:, 1]
            return apply_calibrator(selected_calibration, calibrators[selected_calibration], raw, native)

        stress_rows, stress_matrix = candidate_price_predictions(validation_model, validation, contract, selected_family.feature_names, multipliers=config["evaluation"]["candidate_price_multipliers"], predict=predict_candidates)
        stress_rows.to_csv(ARTIFACTS / "price_response_stress_test.csv", index=False)
        price_summary = summarize_price_response(stress_matrix, config["evaluation"]["candidate_price_multipliers"])
        write_json(ARTIFACTS / "price_response_summary.json", price_summary)
        if price_summary["flat_response_rate"] > 0.95:
            warnings.append(f"price-response stress test is flat for {price_summary['flat_response_rate']:.3f} of validation rows")
        if price_summary["significant_upward_violation_rate"] > 0.10:
            warnings.append(f"significant upward price-response violations occur for {price_summary['significant_upward_violation_rate']:.3f} of validation rows")

        importance = validation_model.get_feature_importance()
        entries = {item["name"]: item for item in contract["features"]}
        importance_frame = pd.DataFrame({"feature": list(selected_family.feature_names), "importance": np.asarray(importance, dtype=float)})
        importance_frame["feature_group"] = importance_frame["feature"].map(lambda name: entries[name].get("feature_group"))
        importance_frame["conditional"] = importance_frame["feature"].map(lambda name: bool(entries[name].get("conditional", False)))
        importance_frame["price_related"] = importance_frame["feature"].map(lambda name: bool(entries[name].get("price_dependent", False)) or name in {"CurrentPrice", "AppliedPrice", "BasePrice"})
        importance_frame = importance_frame.sort_values("importance", ascending=False, kind="mergesort")
        importance_frame.to_csv(ARTIFACTS / "feature_importance.csv", index=False)

        final_iterations = int(best_iteration) + 1
        if final_iterations > int(config["compute"]["max_iterations"] * 0.95):
            warnings.append("validation best iteration is near the 3000-tree cap; no repeated TEST retuning was performed")
        frozen_spec = _write_frozen_spec(selected_family, hpo_params, final_iterations, selected_calibration, contract, compute)
        _write_phase4_contract(selected_family, hpo_params, final_iterations, selected_calibration, contract, compute)

        # TEST is intentionally not touched before this point.
        _require_frozen_spec()
        test = _split_frame(frame, assignments, "test")
        train_validation = pd.concat([train, validation], ignore_index=True).sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)
        final_calibrator = None
        if selected_calibration != "NATIVE":
            combined_splitter = ExpandingWindowSplitter(n_splits=3)
            combined_folds = list(combined_splitter.split(train_validation))
            final_oof_raw, final_oof_native, final_oof_labels, _ = _oof_predictions(train_validation, combined_folds, contract, selected_family.feature_names, hpo_params, thread_count=compute["usable_threads"], fixed_iterations=final_iterations)
            final_calibrators = fit_calibration_candidates(final_oof_raw, final_oof_native, final_oof_labels)
            final_calibrator = final_calibrators[selected_calibration]
            joblib.dump(final_calibrator, MODEL_DIR / "purchase_calibrator.joblib")
        final_pool = make_catboost_pool(train_validation, contract, selected_family.feature_names, train_validation["PurchasedFlag"])
        final_model = make_catboost_classifier(hpo_params, thread_count=compute["usable_threads"], iterations=final_iterations, random_seed=42, early_stopping_rounds=None, use_best_model=False)
        final_model.fit(final_pool)
        model_path = MODEL_DIR / "purchase_catboost.cbm"
        final_model.save_model(model_path)
        test_pool = make_catboost_pool(test, contract, selected_family.feature_names)
        test_native = final_model.predict_proba(test_pool)[:, 1]
        test_raw = np.asarray(final_model.predict(test_pool, prediction_type="RawFormulaVal"), dtype=float).reshape(-1)
        test_official = apply_calibrator(selected_calibration, final_calibrator, test_raw, test_native)
        test_prediction_frame = test[["PricingDecisionID", "DecisionTime", "PurchasedFlag"]].copy()
        test_prediction_frame["split"] = "test"
        test_prediction_frame["native_probability"] = test_native
        test_prediction_frame["official_probability"] = test_official
        test_prediction_frame["calibration_method"] = selected_calibration
        test_prediction_frame.to_parquet(PREDICTION_DIR / "purchase_test.parquet", index=False)
        val_prediction_frame = validation[["PricingDecisionID", "DecisionTime", "PurchasedFlag"]].copy()
        val_prediction_frame["split"] = "validation"
        val_prediction_frame["native_probability"] = native_validation
        val_prediction_frame["official_probability"] = official_validation
        val_prediction_frame["calibration_method"] = selected_calibration
        val_prediction_frame.to_parquet(PREDICTION_DIR / "purchase_validation.parquet", index=False)
        test_metrics = {"dummy": json.loads((ROOT / config["phase3"]["test_metrics_path"]).read_text(encoding="utf-8"))["purchase_dummy_prior"], "logistic": json.loads((ROOT / config["phase3"]["test_metrics_path"]).read_text(encoding="utf-8"))["purchase_logistic_core"], "native": purchase_metrics(test["PurchasedFlag"], test_native), "official": purchase_metrics(test["PurchasedFlag"], test_official)}
        write_json(ARTIFACTS / "test_metrics.json", test_metrics)
        calibration_table(test["PurchasedFlag"], test_official, bins=config["evaluation"]["calibration_bins"]).to_csv(ARTIFACTS / "test_calibration_table.csv", index=False)
        pd.DataFrame([{**calibration_metrics(test["PurchasedFlag"].to_numpy(dtype=int), test_native, "NATIVE"), "selection_locked": True}, {**calibration_metrics(test["PurchasedFlag"].to_numpy(dtype=int), test_official, selected_calibration), "selection_locked": True}]).to_csv(ARTIFACTS / "calibration_test.csv", index=False)
        segments = pd.concat([_segment_metrics(validation, validation["PurchasedFlag"].to_numpy(dtype=int), official_validation, "validation", config["evaluation"]["minimum_segment_support"]), _segment_metrics(test, test["PurchasedFlag"].to_numpy(dtype=int), test_official, "test", config["evaluation"]["minimum_segment_support"])], ignore_index=True)
        segments.to_csv(ARTIFACTS / "segment_metrics.csv", index=False)
        test_prediction_hash = prediction_fingerprint(test_prediction_frame)
        model_hash = sha256_file(model_path)
        test_access = {"frozen_model_spec_sha256": frozen_spec["frozen_model_spec_sha256"], "model_sha256": model_hash, "prediction_sha256": test_prediction_hash, "training_start": _date(train_validation["DecisionTime"].min()), "training_end": _date(train_validation["DecisionTime"].max()), "test_start": _date(test["DecisionTime"].min()), "test_end": _date(test["DecisionTime"].max()), "generated_at_utc": datetime.now(timezone.utc).isoformat(), "test_access_reason": "FINAL_PHASE4_BENCHMARK", "test_used_for_model_selection": False, "test_used_for_hyperparameter_search": False, "test_used_for_calibration_selection": False, "test_used_for_feature_selection": False}
        write_json(ARTIFACTS / "test_access_manifest.json", test_access)

        # Acceptance gates are evaluated once, after the legitimate holdout access.
        prevalence = float(validation["PurchasedFlag"].mean())
        official_val = validation_metrics["official"]
        if official_val["log_loss"] >= validation_metrics["dummy"]["log_loss"] and official_val["brier_score"] >= validation_metrics["dummy"]["brier_score"] and official_val["roc_auc"] <= 0.51 and official_val["average_precision"] <= prevalence + 0.002:
            blockers.append("PURCHASE_MODEL_NOT_USEFUL")
        if not (official_val["roc_auc"] > 0.52 or official_val["average_precision"] > prevalence + 0.005 or official_val["top_decile_lift"] > 1.05):
            # Proper-score improvement can justify a model even without the
            # ranking threshold; otherwise this is the explicit feasibility gate.
            proper_score_improvement = official_val["log_loss"] < validation_metrics["dummy"]["log_loss"] - 0.001 or official_val["brier_score"] < validation_metrics["dummy"]["brier_score"] - 0.0005
            if not proper_score_improvement:
                blockers.append("NO_USEFUL_PURCHASE_RANKING_SIGNAL")
        if test_metrics["official"]["log_loss"] > test_metrics["dummy"]["log_loss"] and test_metrics["official"]["brier_score"] > test_metrics["dummy"]["brier_score"] and test_metrics["official"]["roc_auc"] <= 0.51 and test_metrics["official"]["average_precision"] <= float(test["PurchasedFlag"].mean()) + 0.002:
            blockers.append("HOLDOUT_GENERALIZATION_FAILURE")
        if selected_family.groups:
            warnings.append(f"selected conditional context groups: {', '.join(selected_family.groups)}")
        if selected_calibration != "NATIVE":
            warnings.append(f"native CatBoost probabilities were replaced by leakage-safe {selected_calibration} calibration")
        if test_metrics["official"]["roc_auc"] < 0.60:
            warnings.append(f"TEST ROC-AUC remains below 0.60 ({test_metrics['official']['roc_auc']:.6f}); this is a warning, not a retuning license")
        warnings.extend([
            "strict competitor history is sparse",
            "Product×Store history is sparse",
            "promotion coverage is sparse",
            "quantity target is concentrated",
            "several historical features have temporal missingness drift",
            "synthetic/observational data cannot prove causal elasticity",
            "Phase 3 linear purchase signal was extremely weak",
        ])
        warnings = list(dict.fromkeys(warnings))
        result = "BLOCKED" if blockers else ("PASS_WITH_WARNINGS" if warnings else "PASS")
        recommendation = "DO_NOT_PROCEED_TO_PHASE_5" if blockers else "PROCEED_TO_PHASE_5"
        write_json(ARTIFACTS / "upstream_validation.json", {"phase2_dataset_sha256": upstream["dataset_sha256"], "phase3_split_assignment_sha256": upstream["split_assignment_sha256"], "health": upstream["health"], "fold_manifest": upstream["fold_manifest"], "test_access_before_freeze": False})
        write_json(ARTIFACTS / "compute_environment.json", compute)
        write_json(ARTIFACTS / "environment.json", {"python_version": sys.version, "numpy_version": np.__version__, "pandas_version": pd.__version__, "catboost_version": catboost_version, "scikit_learn_version": sklearn.__version__, "optuna_version": optuna.__version__, "joblib_version": joblib.__version__, "psutil_version": psutil.__version__, "threadpoolctl_version": __import__("threadpoolctl").__version__})
        write_json(ARTIFACTS / "temporal_fold_summary.json", {"fold_count": 3, "metrics": {metric: {"mean": float(pd.DataFrame(fold_rows)[metric].mean()), "std": float(pd.DataFrame(fold_rows)[metric].std(ddof=0)), "min": float(pd.DataFrame(fold_rows)[metric].min()), "max": float(pd.DataFrame(fold_rows)[metric].max())} for metric in ["log_loss", "brier_score", "average_precision", "roc_auc", "ece"]}})
        pd.DataFrame(fold_rows).to_csv(ARTIFACTS / "temporal_fold_metrics.csv", index=False)
        write_json(ARTIFACTS / "compute_benchmark.json", {"screening_fit_seconds": float(pd.to_numeric(fold_screening["fit_seconds"]).sum()), "hpo_trials": hpo_trials, "validation_fit_seconds": validation_fit_seconds, "total_seconds": (datetime.now(timezone.utc) - started_at).total_seconds()})
        manifest = {"result": result, "recommendation": recommendation, "base_branch": BASE_BRANCH, "base_git_sha": BASE_SHA, "phase4_implementation_git_sha": os.environ.get("PHASE4_IMPLEMENTATION_SHA", "LOCAL_PHASE4_IMPLEMENTATION"), "phase4_evidence_git_sha": os.environ.get("PHASE4_EVIDENCE_SHA", "LOCAL_PHASE4_EVIDENCE_PENDING"), "phase4_branch_behind_default": 0, "phase2_dataset_sha256": upstream["dataset_sha256"], "phase3_split_assignment_sha256": upstream["split_assignment_sha256"], "row_count": len(frame), "target_counts": {"purchases": int(frame["PurchasedFlag"].sum()), "non_purchases": int((frame["PurchasedFlag"] == 0).sum())}, "compute": compute, "selected_feature_family": selected_family.name, "feature_names": list(selected_family.feature_names), "categorical_features": categorical_feature_names(contract, selected_family.feature_names), "selected_hyperparameters": hpo_params, "selected_iterations": final_iterations, "selected_calibration": selected_calibration, "frozen_model_spec_sha256": frozen_spec["frozen_model_spec_sha256"], "model_sha256": model_hash, "validation_prediction_sha256": prediction_fingerprint(val_prediction_frame), "test_prediction_sha256": test_prediction_hash, "test_access_count": 1, "tests": tests, "warnings": warnings, "major_blockers": list(dict.fromkeys(blockers)), "source_tree_sha256": source_tree_sha256(), "artifacts": {"model": "artifacts/phase4/models/purchase_catboost.cbm", "calibrator": "artifacts/phase4/models/purchase_calibrator.joblib" if selected_calibration != "NATIVE" else None, "feature_selection_report": "docs/PHASE4_FEATURE_SELECTION_REPORT.md", "hpo_results": "artifacts/phase4/hpo_trials.csv", "validation_predictions": "artifacts/phase4/predictions/purchase_validation.parquet", "test_predictions": "artifacts/phase4/predictions/purchase_test.parquet", "frozen_model_spec": "artifacts/phase4/frozen_model_spec.json", "acceptance_report": "docs/PHASE4_ACCEPTANCE_REPORT.md"}, "ci_status": "PENDING_REMOTE_CI"}
        write_json(ARTIFACTS / "phase4_manifest.json", manifest)
        _write_reports(upstream=upstream, compute=compute, selection=selection, screening_summary=screening_summary, hpo_summary=hpo_summary, hpo_params=hpo_params, fold_rows=fold_rows, validation=validation_metrics, test=test_metrics, calibration_rows=calibration_rows, calibration_selection=calibration_selection, parity=parity, price_summary=price_summary, reproducibility=reproducibility, manifest=manifest)
        return 2 if blockers else 0
    except Exception as exc:
        payload = {"result": "BLOCKED", "major_blockers": [type(exc).__name__], "error": str(exc)[:4000], "base_branch": BASE_BRANCH, "base_git_sha": BASE_SHA, "phase4_implementation_git_sha": os.environ.get("PHASE4_IMPLEMENTATION_SHA", "LOCAL_PHASE4_IMPLEMENTATION")}
        write_json(ARTIFACTS / "phase4_manifest.json", payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

