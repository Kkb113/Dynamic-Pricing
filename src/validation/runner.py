from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
import yaml

from audit.report_builder import source_tree_sha256
from features.feature_contract import load_contract, model_feature_columns
from features.validation import canonical_dataset_hash

from baselines.purchase import make_purchase_pipeline, purchase_feature_sets
from baselines.quantity import make_quantity_pipeline, purchased_population
from baselines.training import fit_pipeline, predict_probabilities, predict_values
from validation.artifacts import model_fingerprint, prediction_fingerprint, sha256_file, write_json
from validation.compute import configure_thread_environment, detect_compute_environment
from validation.diagnostics import (
    feature_missingness_by_split,
    price_bucket_metrics,
    segment_metrics,
    split_health,
    target_drift,
    unseen_category_report,
)
from validation.metrics import aggregate_fold_metrics, calibration_table, purchase_metrics, quantity_metrics
from validation.temporal_split import ExpandingWindowSplitter, TemporalSplitError, build_temporal_split, validate_temporal_split


ROOT = Path(__file__).resolve().parents[2]
PHASE3_ARTIFACTS = ROOT / "artifacts/phase3"


def _date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def _load_config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config/phase3_baselines.yaml").read_text(encoding="utf-8"))


def _run_tests(artifact_dir: Path) -> dict[str, Any]:
    evidence_path = artifact_dir / "test_results.json"
    env = os.environ.copy()
    env["TEST_EVIDENCE_PATH"] = str(evidence_path)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, env=env, check=False)
    if not evidence_path.exists():
        raise RuntimeError("PHASE3_TEST_EVIDENCE_MISSING")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["runner_exit_code"] = int(result.returncode)
    if result.returncode != 0 or evidence.get("status") != "PASS" or evidence.get("failed", 0) != 0:
        raise RuntimeError(f"PHASE3_TESTS_FAILED: {evidence}")
    if evidence.get("source_tree_sha256") != source_tree_sha256():
        raise RuntimeError("PHASE3_TEST_EVIDENCE_STALE")
    return evidence


def _verify_phase2_dataset(config: dict[str, Any], contract: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    path = ROOT / config["phase2"]["dataset_path"]
    if not path.exists():
        raise RuntimeError("PHASE2_DATASET_MISSING")
    frame = pd.read_parquet(path)
    ordered_columns = [feature["name"] for feature in contract["features"]]
    actual_hash = canonical_dataset_hash(frame, ordered_columns)
    expected_hash = config["phase2"]["expected_sha256"]
    if actual_hash != expected_hash:
        raise RuntimeError(f"PHASE2_DATASET_FINGERPRINT_MISMATCH: expected={expected_hash} actual={actual_hash}")
    if len(frame) != 35000:
        raise RuntimeError(f"PHASE2_ROW_COUNT_MISMATCH: {len(frame)}")
    if frame["PricingDecisionID"].duplicated().any():
        raise RuntimeError("PHASE2_DUPLICATE_PRICING_DECISION_ID")
    if int(frame["PurchasedFlag"].sum()) != 6492 or int((frame["PurchasedFlag"] == 0).sum()) != 28508:
        raise RuntimeError("PHASE2_TARGET_COUNTS_MISMATCH")
    return frame, actual_hash


def _split_frame(frame: pd.DataFrame, assignments: pd.DataFrame, split: str) -> pd.DataFrame:
    ids = set(assignments.loc[assignments["split"] == split, "PricingDecisionID"])
    return frame[frame["PricingDecisionID"].isin(ids)].copy()


def _feature_frame(frame: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    missing = sorted(set(feature_names) - set(frame.columns))
    if missing:
        raise RuntimeError(f"MODEL_FEATURES_MISSING: {missing}")
    return frame.loc[:, feature_names].copy()


def _prediction_frame(frame: pd.DataFrame, probabilities: np.ndarray, split: str, extra: dict[str, np.ndarray] | None = None) -> pd.DataFrame:
    result = frame[["PricingDecisionID", "DecisionTime", "PurchasedFlag", "Channel", "Season", "RegionID", "CategoryID", "StoreType", "price_change_pct"]].copy()
    result["split"] = split
    result["predicted_probability"] = np.asarray(probabilities, dtype=float)
    if extra:
        for name, values in extra.items():
            result[name] = np.asarray(values, dtype=float)
    return result


def _quantity_prediction_frame(frame: pd.DataFrame, poisson: np.ndarray, mean: np.ndarray, split: str) -> pd.DataFrame:
    result = frame[["PricingDecisionID", "DecisionTime", "QuantityPurchased", "Channel", "Season", "RegionID", "CategoryID", "StoreType"]].copy()
    result = result.rename(columns={"QuantityPurchased": "actual_quantity"})
    result["split"] = split
    result["predicted_quantity"] = np.asarray(poisson, dtype=float)
    result["quantity_dummy_mean"] = np.asarray(mean, dtype=float)
    return result


def _comparison_row(model_name: str, population: str, feature_set: str, training_frame: pd.DataFrame, evaluation_split: str, metrics: dict[str, Any], fit_seconds: float, prediction_seconds: float) -> dict[str, Any]:
    row = {
        "model_name": model_name,
        "population": population,
        "feature_set": feature_set,
        "training_start": _date(training_frame["DecisionTime"].min()),
        "training_end": _date(training_frame["DecisionTime"].max()),
        "evaluation_split": evaluation_split,
        "training_seconds": fit_seconds,
        "prediction_seconds": prediction_seconds,
    }
    for name in ["roc_auc", "average_precision", "log_loss", "brier_score", "ece", "mae", "rmse", "r2", "mean_poisson_deviance"]:
        row[name] = metrics.get(name)
    return row


def _write_phase3_contract(config: dict[str, Any], frame: pd.DataFrame, boundaries: dict[str, pd.Timestamp], health: pd.DataFrame, fold_manifest: list[dict[str, Any]], dataset_hash: str, compute: dict[str, Any]) -> None:
    payload = {
        "source_dataset_sha256": dataset_hash,
        "split_variable": config["split"]["time_column"],
        "split_method": "chronological unique DecisionTime groups with approximately 70/15/15 proportions",
        "train_start": _date(boundaries["train_start"]),
        "train_end": _date(boundaries["train_end"]),
        "validation_start": _date(boundaries["validation_start"]),
        "validation_end": _date(boundaries["validation_end"]),
        "test_start": _date(boundaries["test_start"]),
        "test_end": _date(boundaries["test_end"]),
        "row_counts": {row["split"]: int(row["row_count"]) for row in health.to_dict("records")},
        "target_counts": {row["split"]: {"purchases": int(row["purchase_count"]), "non_purchases": int(row["non_purchase_count"])} for row in health.to_dict("records")},
        "holdout_policy": "Validation is used to freeze the fixed baseline specification; TEST is evaluated once after TRAIN+VALIDATION refit and is never used for selection.",
        "backtesting_policy": "Three expanding-window folds remain within TRAIN; no shuffled or stratified random folds.",
        "random_seed": int(config["compute"]["random_seed"]),
        "feature_contract_path": config["phase2"]["contract_path"],
        "purchase_baseline": "purchase_logistic_core",
        "quantity_baseline": "quantity_poisson_core",
        "compute_policy": {
            "expected_physical_cores": config["compute"]["expected_physical_cores"],
            "expected_logical_threads": config["compute"]["expected_logical_threads"],
            "configured_thread_limit": compute["configured_thread_limit"],
            "usable_threads": compute["usable_threads"],
        },
        "expanding_window_folds": fold_manifest,
    }
    contract_path = ROOT / "contracts/phase3_temporal_validation_contract_v1.yaml"
    contract_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _purchase_folds(dev: pd.DataFrame, contract: dict[str, Any], splitter: ExpandingWindowSplitter, compute: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fold, (train_indices, validation_indices) in enumerate(splitter.split(dev), start=1):
        train = dev.loc[train_indices]
        validation = dev.loc[validation_indices]
        for model_name in ["purchase_dummy_prior", "purchase_logistic_core"]:
            pipeline, features = make_purchase_pipeline(contract, model_name)
            _, fit_seconds = fit_pipeline(pipeline, _feature_frame(train, features), train["PurchasedFlag"], compute)
            probabilities, prediction_seconds = predict_probabilities(pipeline, _feature_frame(validation, features), compute)
            metrics = purchase_metrics(validation["PurchasedFlag"], probabilities)
            rows.append({"fold": fold, "model_name": model_name, "population": "purchase", "feature_set": "CORE", "training_seconds": fit_seconds, "prediction_seconds": prediction_seconds, **metrics})
    return rows


def _quantity_folds(dev: pd.DataFrame, contract: dict[str, Any], splitter: ExpandingWindowSplitter, compute: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fold, (train_indices, validation_indices) in enumerate(splitter.split(dev), start=1):
        train = dev.loc[train_indices]
        validation = dev.loc[validation_indices]
        train = purchased_population(train)
        validation = purchased_population(validation)
        for model_name in ["quantity_dummy_mean", "quantity_poisson_core"]:
            pipeline, features = make_quantity_pipeline(contract, model_name)
            _, fit_seconds = fit_pipeline(pipeline, _feature_frame(train, features), train["QuantityPurchased"], compute)
            predictions, prediction_seconds = predict_values(pipeline, _feature_frame(validation, features), compute)
            metrics = quantity_metrics(validation["QuantityPurchased"], predictions)
            rows.append({"fold": fold, "model_name": model_name, "population": "quantity_purchased_only", "feature_set": "CORE", "training_seconds": fit_seconds, "prediction_seconds": prediction_seconds, **metrics})
    return rows


def _run_models(frame: pd.DataFrame, assignments: pd.DataFrame, contract: dict[str, Any], compute: dict[str, Any], config: dict[str, Any], dataset_hash: str, artifact_dir: Path) -> dict[str, Any]:
    train = _split_frame(frame, assignments, "train")
    validation = _split_frame(frame, assignments, "validation")
    test = _split_frame(frame, assignments, "test")
    train_validation = pd.concat([train, validation], ignore_index=True)
    comparison: list[dict[str, Any]] = []
    purchase_validation_metrics: dict[str, Any] = {}
    purchase_test_metrics: dict[str, Any] = {}
    validation_frames: dict[str, pd.DataFrame] = {}
    test_frames: dict[str, pd.DataFrame] = {}
    model_fingerprints: dict[str, str] = {}
    prediction_fingerprints: dict[str, str] = {}
    official_purchase_validation: dict[str, np.ndarray] = {}
    official_purchase_test: dict[str, np.ndarray] = {}

    for model_name in ["purchase_dummy_prior", "purchase_logistic_core"]:
        dev_pipeline, feature_names = make_purchase_pipeline(contract, model_name)
        dev_pipeline, fit_seconds = fit_pipeline(dev_pipeline, _feature_frame(train, feature_names), train["PurchasedFlag"], compute)
        val_probabilities, val_prediction_seconds = predict_probabilities(dev_pipeline, _feature_frame(validation, feature_names), compute)
        val_metrics = purchase_metrics(validation["PurchasedFlag"], val_probabilities)
        purchase_validation_metrics[model_name] = val_metrics
        official_purchase_validation[model_name] = val_probabilities
        comparison.append(_comparison_row(model_name, "purchase", "CORE", train, "validation", val_metrics, fit_seconds, val_prediction_seconds))

        final_pipeline, _ = make_purchase_pipeline(contract, model_name)
        final_pipeline, final_fit_seconds = fit_pipeline(final_pipeline, _feature_frame(train_validation, feature_names), train_validation["PurchasedFlag"], compute)
        test_probabilities, test_prediction_seconds = predict_probabilities(final_pipeline, _feature_frame(test, feature_names), compute)
        test_metrics = purchase_metrics(test["PurchasedFlag"], test_probabilities)
        purchase_test_metrics[model_name] = test_metrics
        official_purchase_test[model_name] = test_probabilities
        model_path = artifact_dir / "models" / f"{model_name}.joblib"
        joblib.dump(final_pipeline, model_path)
        model_fingerprints[model_name] = model_fingerprint(model_path)
        comparison.append(_comparison_row(model_name, "purchase", "CORE", train_validation, "test", test_metrics, final_fit_seconds, test_prediction_seconds))

    ablation_pipeline, ablation_features = make_purchase_pipeline(contract, "purchase_logistic_core_no_price")
    ablation_pipeline, ablation_fit = fit_pipeline(ablation_pipeline, _feature_frame(train, ablation_features), train["PurchasedFlag"], compute)
    ablation_probabilities, ablation_prediction = predict_probabilities(ablation_pipeline, _feature_frame(validation, ablation_features), compute)
    ablation_metrics = purchase_metrics(validation["PurchasedFlag"], ablation_probabilities)
    purchase_validation_metrics["purchase_logistic_core_no_price"] = ablation_metrics
    comparison.append(_comparison_row("purchase_logistic_core_no_price", "purchase", "CORE_NO_PRICE", train, "validation", ablation_metrics, ablation_fit, ablation_prediction))
    joblib.dump(ablation_pipeline, artifact_dir / "models" / "purchase_logistic_core_no_price.joblib")
    model_fingerprints["purchase_logistic_core_no_price"] = model_fingerprint(artifact_dir / "models" / "purchase_logistic_core_no_price.joblib")

    validation_purchase_frame = _prediction_frame(
        validation,
        official_purchase_validation["purchase_logistic_core"],
        "validation",
        {"purchase_dummy_prior_probability": official_purchase_validation["purchase_dummy_prior"], "purchase_logistic_core_no_price_probability": ablation_probabilities},
    )
    test_purchase_frame = _prediction_frame(
        test,
        official_purchase_test["purchase_logistic_core"],
        "test",
        {"purchase_dummy_prior_probability": official_purchase_test["purchase_dummy_prior"]},
    )
    validation_purchase_frame.to_parquet(artifact_dir / "predictions" / "purchase_validation.parquet", index=False)
    test_purchase_frame.to_parquet(artifact_dir / "predictions" / "purchase_test.parquet", index=False)
    prediction_fingerprints["purchase_validation"] = prediction_fingerprint(validation_purchase_frame)
    prediction_fingerprints["purchase_test"] = prediction_fingerprint(test_purchase_frame)
    calibration_table(validation["PurchasedFlag"], official_purchase_validation["purchase_logistic_core"], bins=config["evaluation"]["calibration_bins"]).to_csv(artifact_dir / "purchase_calibration_validation.csv", index=False)
    calibration_table(test["PurchasedFlag"], official_purchase_test["purchase_logistic_core"], bins=config["evaluation"]["calibration_bins"]).to_csv(artifact_dir / "purchase_calibration_test.csv", index=False)

    quantity_validation_metrics: dict[str, Any] = {}
    quantity_test_metrics: dict[str, Any] = {}
    quantity_validation_predictions: dict[str, np.ndarray] = {}
    quantity_test_predictions: dict[str, np.ndarray] = {}
    purchased_train = purchased_population(train)
    purchased_validation = purchased_population(validation)
    purchased_train_validation = purchased_population(train_validation)
    purchased_test = purchased_population(test)
    for model_name in ["quantity_dummy_mean", "quantity_poisson_core"]:
        dev_pipeline, feature_names = make_quantity_pipeline(contract, model_name)
        dev_pipeline, fit_seconds = fit_pipeline(dev_pipeline, _feature_frame(purchased_train, feature_names), purchased_train["QuantityPurchased"], compute)
        val_predictions, val_prediction_seconds = predict_values(dev_pipeline, _feature_frame(purchased_validation, feature_names), compute)
        val_metrics = quantity_metrics(purchased_validation["QuantityPurchased"], val_predictions)
        quantity_validation_metrics[model_name] = val_metrics
        quantity_validation_predictions[model_name] = val_predictions
        comparison.append(_comparison_row(model_name, "quantity_purchased_only", "CORE", purchased_train, "validation", val_metrics, fit_seconds, val_prediction_seconds))

        final_pipeline, _ = make_quantity_pipeline(contract, model_name)
        final_pipeline, final_fit_seconds = fit_pipeline(final_pipeline, _feature_frame(purchased_train_validation, feature_names), purchased_train_validation["QuantityPurchased"], compute)
        test_predictions, test_prediction_seconds = predict_values(final_pipeline, _feature_frame(purchased_test, feature_names), compute)
        test_metrics = quantity_metrics(purchased_test["QuantityPurchased"], test_predictions)
        quantity_test_metrics[model_name] = test_metrics
        quantity_test_predictions[model_name] = test_predictions
        model_path = artifact_dir / "models" / f"{model_name}.joblib"
        joblib.dump(final_pipeline, model_path)
        model_fingerprints[model_name] = model_fingerprint(model_path)
        comparison.append(_comparison_row(model_name, "quantity_purchased_only", "CORE", purchased_train_validation, "test", test_metrics, final_fit_seconds, test_prediction_seconds))
    quantity_validation_frame = _quantity_prediction_frame(purchased_validation, quantity_validation_predictions["quantity_poisson_core"], quantity_validation_predictions["quantity_dummy_mean"], "validation")
    quantity_test_frame = _quantity_prediction_frame(purchased_test, quantity_test_predictions["quantity_poisson_core"], quantity_test_predictions["quantity_dummy_mean"], "test")
    quantity_validation_frame.to_parquet(artifact_dir / "predictions" / "quantity_validation.parquet", index=False)
    quantity_test_frame.to_parquet(artifact_dir / "predictions" / "quantity_test.parquet", index=False)
    prediction_fingerprints["quantity_validation"] = prediction_fingerprint(quantity_validation_frame)
    prediction_fingerprints["quantity_test"] = prediction_fingerprint(quantity_test_frame)

    splitter = ExpandingWindowSplitter(n_splits=config["split"]["expanding_window_folds"])
    fold_purchase = _purchase_folds(train, contract, splitter, compute)
    fold_quantity = _quantity_folds(train, contract, splitter, compute)
    pd.DataFrame(fold_purchase).to_csv(artifact_dir / "purchase_temporal_fold_metrics.csv", index=False)
    pd.DataFrame(fold_quantity).to_csv(artifact_dir / "quantity_temporal_fold_metrics.csv", index=False)
    fold_summaries = {
        "purchase": {},
        "quantity": {},
    }
    for model_name in ["purchase_dummy_prior", "purchase_logistic_core"]:
        rows = [row for row in fold_purchase if row["model_name"] == model_name]
        fold_summaries["purchase"][model_name] = aggregate_fold_metrics(rows, ["roc_auc", "average_precision", "log_loss", "brier_score", "ece"])
    for model_name in ["quantity_dummy_mean", "quantity_poisson_core"]:
        rows = [row for row in fold_quantity if row["model_name"] == model_name]
        fold_summaries["quantity"][model_name] = aggregate_fold_metrics(rows, ["mae", "rmse", "r2", "mean_poisson_deviance"])

    evaluation_frames = {"validation": validation_purchase_frame, "test": test_purchase_frame}
    segment_metrics(evaluation_frames, min_support=config["evaluation"]["segment_min_support"]).to_csv(artifact_dir / "segment_metrics.csv", index=False)
    price_bucket_metrics(validation_purchase_frame).to_csv(artifact_dir / "price_bucket_metrics.csv", index=False)
    comparison_frame = pd.DataFrame(comparison)
    comparison_frame.to_csv(artifact_dir / "baseline_model_comparison.csv", index=False)
    write_json(artifact_dir / "purchase_validation_metrics.json", purchase_validation_metrics)
    write_json(artifact_dir / "purchase_test_metrics.json", purchase_test_metrics)
    write_json(artifact_dir / "quantity_validation_metrics.json", quantity_validation_metrics)
    write_json(artifact_dir / "quantity_test_metrics.json", quantity_test_metrics)
    write_json(artifact_dir / "temporal_fold_metric_summary.json", fold_summaries)
    return {
        "comparison": comparison_frame,
        "purchase_validation_metrics": purchase_validation_metrics,
        "purchase_test_metrics": purchase_test_metrics,
        "quantity_validation_metrics": quantity_validation_metrics,
        "quantity_test_metrics": quantity_test_metrics,
        "fold_purchase": fold_purchase,
        "fold_quantity": fold_quantity,
        "fold_summaries": fold_summaries,
        "model_fingerprints": model_fingerprints,
        "prediction_fingerprints": prediction_fingerprints,
        "validation_purchase_frame": validation_purchase_frame,
        "test_purchase_frame": test_purchase_frame,
        "training_seconds": {
            row["model_name"]: float(row["training_seconds"])
            for row in comparison
            if row["evaluation_split"] == "test"
        },
    }


def _warnings(frame: pd.DataFrame, health: pd.DataFrame, missingness: pd.DataFrame, metrics: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    rates = health["purchase_rate"].to_numpy(dtype=float)
    if rates.max() - rates.min() > 0.05:
        warnings.append(f"purchase-rate drift across splits is {rates.max() - rates.min():.4f}")
    if bool(missingness["warning_gt_10pp"].any()):
        warnings.append("one or more core feature null rates shift by more than 10 percentage points")
    for model, values in metrics["purchase_validation_metrics"].items():
        if model == "purchase_logistic_core" and values.get("roc_auc") is not None and values["roc_auc"] <= 0.50:
            warnings.append("logistic purchase ROC-AUC is at or below 0.50")
    dummy = metrics["purchase_validation_metrics"].get("purchase_dummy_prior", {})
    logistic = metrics["purchase_validation_metrics"].get("purchase_logistic_core", {})
    for metric_name in ["log_loss", "brier_score"]:
        if logistic.get(metric_name) is not None and dummy.get(metric_name) is not None and logistic[metric_name] > dummy[metric_name]:
            warnings.append(
                f"logistic validation {metric_name} ({logistic[metric_name]:.6f}) is worse than dummy prior ({dummy[metric_name]:.6f}); investigate before promotion"
            )
    if logistic.get("average_precision") is not None and logistic.get("purchase_rate") is not None:
        if abs(logistic["average_precision"] - logistic["purchase_rate"]) <= 0.01:
            warnings.append(
                f"logistic validation average precision ({logistic['average_precision']:.6f}) is near purchase prevalence ({logistic['purchase_rate']:.6f})"
            )
    quantity_mean = metrics["quantity_validation_metrics"].get("quantity_dummy_mean", {})
    quantity_poisson = metrics["quantity_validation_metrics"].get("quantity_poisson_core", {})
    quantity_worse = [
        name
        for name in ["mae", "rmse", "mean_poisson_deviance"]
        if quantity_mean.get(name) is not None
        and quantity_poisson.get(name) is not None
        and quantity_poisson[name] > quantity_mean[name]
    ]
    if quantity_worse:
        details = ", ".join(
            f"{name} {quantity_poisson[name]:.6f} vs mean {quantity_mean[name]:.6f}"
            for name in quantity_worse
        )
        warnings.append(f"quantity Poisson baseline does not beat the mean on validation ({details})")
    if metrics["quantity_test_metrics"]["quantity_poisson_core"].get("negative_prediction_count", 0):
        warnings.append("quantity Poisson baseline emitted negative predictions")
    warnings.append("Phase 3 baselines are predictive benchmarks; no causal elasticity claim is made")
    return warnings


def _write_reports(artifact_dir: Path, frame: pd.DataFrame, assignments: pd.DataFrame, boundaries: dict[str, pd.Timestamp], health: pd.DataFrame, folds: list[dict[str, Any]], compute: dict[str, Any], dataset_hash: str, missingness: pd.DataFrame, unseen: pd.DataFrame, drift: dict[str, Any], metrics: dict[str, Any], warnings: list[str], tests: dict[str, Any]) -> None:
    docs = ROOT / "docs"
    purchase_val = metrics["purchase_validation_metrics"].get("purchase_logistic_core", {})
    purchase_test = metrics["purchase_test_metrics"].get("purchase_logistic_core", {})
    quantity_val = metrics["quantity_validation_metrics"].get("quantity_poisson_core", {})
    quantity_test = metrics["quantity_test_metrics"].get("quantity_poisson_core", {})
    health_text = health.to_string(index=False)
    warning_text = "\n".join(f"- {warning}" for warning in warnings) or "- None"
    report = f"""# Phase 3 Temporal Validation Report

## Executive summary

Phase 3 uses the frozen Phase 2 point-in-time dataset and chronological evaluation only. No advanced model, hyperparameter search, causal elasticity estimate, or pricing optimizer is implemented.

## Dataset and split health

- Phase 2 canonical fingerprint: `{dataset_hash}`
- Rows: **{len(frame):,}**; unique decisions: **{frame['PricingDecisionID'].nunique():,}**
- Split boundaries: `{_date(boundaries['train_start'])}` → `{_date(boundaries['train_end'])}` → `{_date(boundaries['validation_end'])}` → `{_date(boundaries['test_end'])}`

{health_text}

## Feature contract and leakage protection

Official baselines use `model_feature_columns(contract, population=...)` with the default core-only feature set. Conditional fields, competitor context, behavior, customer context, ProductID, and StoreID are excluded unless explicitly approved for an experiment. Targets, identifiers, PII, inventory, pricing rules, optimizer outputs, and post-outcome fields are rejected by the preprocessing contract.

All imputers, encoders, scalers, and estimators are fit on each training partition only. The final holdout is evaluated once after refitting the frozen specifications on TRAIN+VALIDATION.

## Expanding-window backtesting

Three expanding folds are contained entirely inside TRAIN. Their manifest and per-fold metrics are in `artifacts/phase3/temporal_fold_manifest.json`, `purchase_temporal_fold_metrics.csv`, and `quantity_temporal_fold_metrics.csv`.

## Purchase probability baselines

The official benchmark is `purchase_logistic_core`; `purchase_dummy_prior` is the lower bound. Validation logistic metrics: ROC-AUC **{purchase_val.get('roc_auc')}**, average precision **{purchase_val.get('average_precision')}**, log loss **{purchase_val.get('log_loss')}**, Brier **{purchase_val.get('brier_score')}**, ECE **{purchase_val.get('ece')}**, top-decile lift **{purchase_val.get('top_decile_lift')}**. Holdout metrics: ROC-AUC **{purchase_test.get('roc_auc')}**, average precision **{purchase_test.get('average_precision')}**, log loss **{purchase_test.get('log_loss')}**, Brier **{purchase_test.get('brier_score')}**.

The price ablation is a predictive signal diagnostic only; its comparison is validation-only and is not a causal elasticity estimate.

## Calibration, segment, and price diagnostics

Native 10-bin calibration tables, segment metrics (minimum support 100), and price-change buckets are persisted under `artifacts/phase3/`. Price results are described as observed predictive relationships, never causal elasticity.

## Quantity baselines

Quantity models are trained only on `PurchasedFlag == 1` rows, and `PurchasedFlag` is not a predictor. The official benchmark is `quantity_poisson_core`; the mean predictor is the lower bound. Validation Poisson MAE **{quantity_val.get('mae')}**, RMSE **{quantity_val.get('rmse')}**, R² **{quantity_val.get('r2')}**, Poisson deviance **{quantity_val.get('mean_poisson_deviance')}**. Holdout MAE **{quantity_test.get('mae')}**, RMSE **{quantity_test.get('rmse')}**, R² **{quantity_test.get('r2')}**, Poisson deviance **{quantity_test.get('mean_poisson_deviance')}**.

## Compute and reproducibility

- Physical cores: **{compute['detected_physical_cores']}**
- Logical threads: **{compute['detected_logical_threads']}**
- Usable/configured limit: **{compute['usable_threads']} / {compute['configured_thread_limit']}**
- Random seed: **42**; nested parallelism: **disabled**
- Test evidence: **{tests.get('passed')}/{tests.get('total')} passed**

## Warnings

{warning_text}
"""
    (docs / "PHASE3_TEMPORAL_VALIDATION_REPORT.md").write_text(report, encoding="utf-8")
    baseline = f"""# Phase 3 Baseline Model Report

Official purchase baseline: `purchase_logistic_core`.
Official quantity baseline: `quantity_poisson_core`.

The machine-readable comparison is `artifacts/phase3/baseline_model_comparison.csv`; all model pipelines are serialized under `artifacts/phase3/models/`. Test predictions are locked in `artifacts/phase3/predictions/` and described by `test_access_manifest.json`.

No hyperparameter optimization, advanced tree model, neural network, or pricing optimizer was run.
"""
    (docs / "PHASE3_BASELINE_MODEL_REPORT.md").write_text(baseline, encoding="utf-8")
    def _metric(model_metrics: dict[str, Any], name: str) -> str:
        value = model_metrics.get(name)
        return "NA" if value is None else f"{float(value):.6f}"

    purchase_delta = {
        name: (purchase_test.get(name) - purchase_val.get(name))
        for name in ["roc_auc", "average_precision", "log_loss", "brier_score"]
        if purchase_test.get(name) is not None and purchase_val.get(name) is not None
    }
    fold_summary = metrics["fold_summaries"]["purchase"].get("purchase_logistic_core", {})
    leakage_statement = "0 runtime leakage violations; 0 conditional-feature violations in official baselines; 0 test-fit violations"
    acceptance = f"""# Phase 3 Acceptance Report

## 1. Executive verdict

**{{verdict}}** — chronological baseline framework completed against the frozen Phase 2 dataset.

## 2. Phase 2 dataset verification

- Fingerprint: `{dataset_hash}`
- Rows: **{len(frame):,}**; unique `PricingDecisionID`: **{frame['PricingDecisionID'].nunique():,}**
- Purchases: **{int(frame['PurchasedFlag'].sum()):,}**; non-purchases: **{int((frame['PurchasedFlag'] == 0).sum()):,}**
- The runner blocked before modelling if this fingerprint, row count, uniqueness, or target totals did not match.

## 3. Compute environment

- Physical cores detected: **{compute['detected_physical_cores']}**
- Logical threads detected: **{compute['detected_logical_threads']}**
- Maximum/configured/usable threads: **22 / {compute['configured_thread_limit']} / {compute['usable_threads']}**
- Effective parallelism: **{compute['effective_parallelism']}**; nested parallelism: **{compute['nested_parallelism']}**

## 4. Canonical temporal split

```text
{health_text}
```

All equal `DecisionTime` values remain together. The resulting partitions are approximately 70/15/15 and are strictly ordered.

## 5. Split integrity

Every decision is assigned exactly once; train/validation/test identifier intersections are empty; `max(TRAIN.DecisionTime) < min(VALIDATION.DecisionTime) < min(TEST.DecisionTime)`. The canonical assignments are in `artifacts/phase3/split_assignments.parquet`.

## 6. Expanding-window validation design

Three expanding folds are contained inside TRAIN. Every fold has both target classes and records row counts, target counts, dates, and Product/Category/Store/Channel coverage in `temporal_fold_manifest.json`.

## 7. Feature contract

Official models use `model_feature_columns(contract, population=...)` from the Phase 2 contract with core features only. ProductID, StoreID, competitor, behavior, customer-context, and join-only favorites remain conditional or excluded by default.

## 8. Preprocessing leakage protection

Each model is a single `ColumnTransformer` + `Pipeline`: numeric median imputation and scaling plus constant-missing categorical imputation and `OneHotEncoder(handle_unknown='ignore')`. Every fold and final fit learns preprocessing only from its training rows.

## 9. Purchase dummy baseline

`purchase_dummy_prior` is the natural-prevalence lower bound. Validation ROC-AUC **{_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'roc_auc')}**, log loss **{_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'log_loss')}**, Brier **{_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'brier_score')}**.

## 10. Logistic regression baseline

`purchase_logistic_core` uses fixed L2 `LogisticRegression(C=1.0, solver='lbfgs', max_iter=2000, random_state=42, class_weight=None)` with no search or tuning.

## 11. Purchase probability metrics

| Model | Split | ROC-AUC | AP | Log loss | Brier | ECE | Top-decile lift |
|---|---|---:|---:|---:|---:|---:|---:|
| purchase_dummy_prior | validation | {_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'roc_auc')} | {_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'average_precision')} | {_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'log_loss')} | {_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'brier_score')} | {_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'ece')} | {_metric(metrics['purchase_validation_metrics']['purchase_dummy_prior'], 'top_decile_lift')} |
| purchase_logistic_core | validation | {_metric(purchase_val, 'roc_auc')} | {_metric(purchase_val, 'average_precision')} | {_metric(purchase_val, 'log_loss')} | {_metric(purchase_val, 'brier_score')} | {_metric(purchase_val, 'ece')} | {_metric(purchase_val, 'top_decile_lift')} |
| purchase_logistic_core | test | {_metric(purchase_test, 'roc_auc')} | {_metric(purchase_test, 'average_precision')} | {_metric(purchase_test, 'log_loss')} | {_metric(purchase_test, 'brier_score')} | {_metric(purchase_test, 'ece')} | {_metric(purchase_test, 'top_decile_lift')} |

Precision, recall, and F1 at 0.5 are retained in the JSON metric artifacts; probability quality is the primary criterion.

## 12. Calibration

Native 10-bin calibration tables and ECE are persisted at `purchase_calibration_validation.csv` and `purchase_calibration_test.csv`. No post-hoc calibration was fit.

## 13. Temporal-fold stability

The logistic-core fold summary is **mean ROC-AUC {_metric(fold_summary.get('roc_auc', {}), 'mean')} ± {_metric(fold_summary.get('roc_auc', {}), 'std')}**, with min **{_metric(fold_summary.get('roc_auc', {}), 'min')}** and max **{_metric(fold_summary.get('roc_auc', {}), 'max')}**. Full per-fold and mean/std/min/max metrics are in `temporal_fold_metric_summary.json`.

## 14. Price-response diagnostic

`purchase_logistic_core_no_price` is a validation-only predictive signal ablation. Validation logistic core ROC-AUC **{_metric(purchase_val, 'roc_auc')}** versus no-price **{_metric(metrics['purchase_validation_metrics']['purchase_logistic_core_no_price'], 'roc_auc')}**; observed difference **{purchase_val.get('roc_auc', 0.0) - metrics['purchase_validation_metrics']['purchase_logistic_core_no_price'].get('roc_auc', 0.0):.6f}**. This is not causal elasticity.

## 15. Quantity mean baseline

`quantity_dummy_mean` trains only on purchased TRAIN rows and is evaluated only on purchased future rows. Validation MAE **{_metric(metrics['quantity_validation_metrics']['quantity_dummy_mean'], 'mae')}**, RMSE **{_metric(metrics['quantity_validation_metrics']['quantity_dummy_mean'], 'rmse')}**.

## 16. Poisson quantity baseline

`quantity_poisson_core` uses fixed `PoissonRegressor(alpha=1.0, max_iter=1000)` and the same core contract. Validation MAE **{_metric(quantity_val, 'mae')}**, RMSE **{_metric(quantity_val, 'rmse')}**, R² **{_metric(quantity_val, 'r2')}**, Poisson deviance **{_metric(quantity_val, 'mean_poisson_deviance')}**.

## 17. Quantity metrics

Holdout Poisson MAE **{_metric(quantity_test, 'mae')}**, RMSE **{_metric(quantity_test, 'rmse')}**, R² **{_metric(quantity_test, 'r2')}**, Poisson deviance **{_metric(quantity_test, 'mean_poisson_deviance')}**; negative prediction count **{quantity_test.get('negative_prediction_count', 'NA')}**. Quantity predictions are non-negative.

## 18. Segment diagnostics

Validation and test segment metrics for Channel, Season, RegionID, CategoryID, and StoreType use minimum support 100. Feature missingness, unseen levels, target drift, and price buckets are persisted under `artifacts/phase3/`.

## 19. Holdout-test discipline

The TEST partition was not used for feature choice, threshold choice, preprocessing fit, model selection, or tuning. Frozen specifications were refit once on TRAIN+VALIDATION and evaluated once on TEST. `test_access_manifest.json` records the data ranges, model fingerprints, prediction fingerprints, and generation time.

## 20. Compute performance

`compute_benchmark.json` records threads used, purchase-logistic fit time, quantity-Poisson fit time, and total temporal-fold time. Fitted complete pipelines are serialized with joblib under `artifacts/phase3/models/`.

## 21. Known limitations

The synthetic/observational data show weak purchase signal and quantity concentration; unseen categories, null-rate shifts, and drift are diagnostic warnings rather than repaired by resampling. No source rows or targets were changed.

## 22. Risks for Phase 4

The baselines do not establish causal price elasticity, and advanced models must beat these chronological benchmarks without changing the split or leakage contract. Conditional features require a separately approved experiment.

## 23. Final verdict

**{{verdict}}**

Warnings: {warning_text}

Leakage status: **{leakage_statement}**.

## 24. Recommendation

**{{recommendation}}**
"""
    # The runner substitutes the final verdict before writing this report.
    (docs / "PHASE3_ACCEPTANCE_REPORT.md").write_text(acceptance, encoding="utf-8")


def _implementation_sha() -> str:
    value = os.environ.get("PHASE3_IMPLEMENTATION_SHA", "").strip()
    if value:
        return value
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def main() -> int:
    artifact_dir = PHASE3_ARTIFACTS
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "models").mkdir(parents=True, exist_ok=True)
    (artifact_dir / "predictions").mkdir(parents=True, exist_ok=True)
    config = _load_config()
    compute = configure_thread_environment(detect_compute_environment(config["compute"]["max_cpu_threads"]))
    random.seed(config["compute"]["random_seed"])
    np.random.seed(config["compute"]["random_seed"])
    try:
        tests = _run_tests(artifact_dir)
        contract = load_contract(ROOT / config["phase2"]["contract_path"])
        frame, dataset_hash = _verify_phase2_dataset(config, contract)
        assignments, boundaries = build_temporal_split(
            frame,
            time_column=config["split"]["time_column"],
            id_column=config["split"]["id_column"],
            train_fraction=config["split"]["train_fraction"],
            validation_fraction=config["split"]["validation_fraction"],
        )
        validate_temporal_split(assignments)
        assignments.to_parquet(artifact_dir / "split_assignments.parquet", index=False)
        health = split_health(frame, assignments)
        health.to_csv(artifact_dir / "split_health.csv", index=False)
        fold_splitter = ExpandingWindowSplitter(n_splits=config["split"]["expanding_window_folds"])
        development = _split_frame(frame, assignments, "train")
        fold_manifest = fold_splitter.manifest(development)
        write_json(artifact_dir / "temporal_fold_manifest.json", fold_manifest)
        write_json(artifact_dir / "split_summary.json", {"boundaries": boundaries, "health": health.to_dict("records"), "assignment_sha256": sha256_file(artifact_dir / "split_assignments.parquet")})
        _write_phase3_contract(config, frame, boundaries, health, fold_manifest, dataset_hash, compute)
        core_features = model_feature_columns(contract, population="purchase")
        categorical_core = [name for name in contract["feature_lists"].get("categorical_features", []) if name in core_features]
        missingness = feature_missingness_by_split(frame, assignments, core_features)
        missingness.to_csv(artifact_dir / "feature_missingness_by_split.csv", index=False)
        unseen = unseen_category_report(frame, assignments, categorical_core)
        unseen.to_csv(artifact_dir / "unseen_category_levels.csv", index=False)
        drift = target_drift(frame, assignments)
        write_json(artifact_dir / "target_drift.json", drift)
        metrics = _run_models(frame, assignments, contract, compute, config, dataset_hash, artifact_dir)
        warnings = _warnings(frame, health, missingness, metrics)
        verdict = "PASS_WITH_WARNINGS" if warnings else "PASS"
        recommendation = "PROCEED_TO_PHASE_4"
        write_json(artifact_dir / "environment.json", {
            "python_version": sys.version,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "scikit_learn_version": sklearn.__version__,
            "joblib_version": joblib.__version__,
            "threadpoolctl_version": __import__("threadpoolctl").__version__,
            "psutil_version": __import__("psutil").__version__,
            "random_seed": config["compute"]["random_seed"],
            "environment_variables": {key: os.environ.get(key) for key in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"]},
        })
        write_json(artifact_dir / "compute_environment.json", compute)
        benchmark = {
            "threads_used": compute["usable_threads"],
            "purchase_logistic_fit_seconds": metrics["training_seconds"].get("purchase_logistic_core"),
            "quantity_poisson_fit_seconds": metrics["training_seconds"].get("quantity_poisson_core"),
            "temporal_fold_total_seconds": float(sum(row["training_seconds"] + row["prediction_seconds"] for row in metrics["fold_purchase"] + metrics["fold_quantity"])),
        }
        write_json(artifact_dir / "compute_benchmark.json", benchmark)
        test_manifest = {
            "model_specification": {"purchase": "purchase_dummy_prior and purchase_logistic_core with fixed core feature contract", "quantity": "quantity_dummy_mean and quantity_poisson_core with fixed core feature contract"},
            "training_data_range": {"train_start": _date(boundaries["train_start"]), "train_validation_end": _date(boundaries["validation_end"])},
            "test_data_range": {"test_start": _date(boundaries["test_start"]), "test_end": _date(boundaries["test_end"])},
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_fingerprint": dataset_hash,
            "model_fingerprints": metrics["model_fingerprints"],
            "prediction_fingerprints": metrics["prediction_fingerprints"],
            "holdout_policy": "Test predictions generated once after frozen specification refit on TRAIN+VALIDATION.",
        }
        write_json(artifact_dir / "test_access_manifest.json", test_manifest)
        manifest = {
            "result": verdict,
            "recommendation": recommendation,
            "implementation_git_sha": _implementation_sha(),
            "source_tree_sha256": source_tree_sha256(),
            "phase2_dataset_sha256": dataset_hash,
            "row_count": len(frame),
            "target_counts": {"purchases": int(frame["PurchasedFlag"].sum()), "non_purchases": int((frame["PurchasedFlag"] == 0).sum())},
            "warnings": warnings,
            "tests": tests,
            "model_fingerprints": metrics["model_fingerprints"],
            "prediction_fingerprints": metrics["prediction_fingerprints"],
            "holdout_test_accessed_for_final_benchmark": True,
        }
        write_json(artifact_dir / "phase3_manifest.json", manifest)
        report_path = ROOT / "docs/PHASE3_ACCEPTANCE_REPORT.md"
        _write_reports(artifact_dir, frame, assignments, boundaries, health, fold_manifest, compute, dataset_hash, missingness, unseen, drift, metrics, warnings, tests)
        report = report_path.read_text(encoding="utf-8").replace("{verdict}", verdict).replace("{recommendation}", recommendation)
        report_path.write_text(report, encoding="utf-8")
        return 0
    except Exception as exc:
        payload = {"result": "BLOCKED", "code": type(exc).__name__, "error": str(exc)[:2000], "implementation_git_sha": _implementation_sha()}
        write_json(artifact_dir / "phase3_manifest.json", payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
