"""End-to-end Phase 5 acceptance runner.

The runner is intentionally explicit about when each frozen population is
accessed.  Screening and HPO receive only purchased TRAIN rows from the exact
Phase 3 expanding folds; the official validation and holdout paths are opened
later, after the quantity specification is selected and frozen.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from catboost import CatBoostClassifier, CatBoostRegressor, __version__ as catboost_version

from audit.report_builder import source_tree_sha256
from demand.expected_units import (
    compute_expected_units,
    expected_units_calibration,
    expected_units_metrics,
    observed_units,
)
from features.feature_contract import load_contract
from features.validation import canonical_dataset_hash
from models.quantity_catboost import (
    SCREENING_PARAMETERS,
    fit_quantity_regressor,
    model_best_iteration,
    predict_quantity_raw,
    project_quantity,
    quantity_metrics,
)
from models.quantity_data import (
    QuantityFeatureFamily,
    build_quantity_feature_families,
    build_quantity_model_features_for_candidate_price,
    categorical_quantity_feature_names,
    make_quantity_pool,
    prepare_quantity_catboost_frame,
)
from models.quantity_estimator import ConditionalQuantityEstimator, save_quantity_estimator_metadata
from models.quantity_selection import (
    adoption_gate,
    integrated_safety_gate,
    run_quantity_hpo,
    screen_quantity_feature_families,
    select_quantity_feature_loss,
)
from validation.artifacts import prediction_fingerprint, sha256_file, write_json
from validation.compute import configure_thread_environment, detect_compute_environment


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/phase5"
MODEL_DIR = ARTIFACTS / "models"
PREDICTION_DIR = ARTIFACTS / "predictions"
BASE_BRANCH = "codex/phase1-data-audit"
PHASE2_SHA = "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2"
PHASE3_SPLIT_SHA = "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d"
PHASE4_SPEC_SHA = "87ffb4e56af455937a0c92b1be45be0e2c8082cc0efd6afa51eb62f9c05ba9d0"
PHASE4_MODEL_SHA = "1af936a1905dcb21e3623392a16afbdbfc6b57c6866093fd6b33f12976dfd86d"
PHASE4_VALIDATION_PRED_SHA = "e57d407d57395146f828e786a13d6eba16653f2ccb7952bf8205141a466af09a"
PHASE4_TEST_PRED_SHA = "cb0f044d27b882b8a03efd34592c811b73942cb5fd4ba2881143ed8db40c1e8f"


def _config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config/phase5_quantity.yaml").read_text(encoding="utf-8"))


def _json_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def _date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def _split_frame(frame: pd.DataFrame, assignments: pd.DataFrame, split: str) -> pd.DataFrame:
    ids = set(assignments.loc[assignments["split"] == split, "PricingDecisionID"].astype(str))
    return frame.loc[frame["PricingDecisionID"].astype(str).isin(ids)].copy().sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)


def _verify_phase4() -> dict[str, Any]:
    manifest_path = ROOT / "artifacts/phase4/phase4_manifest.json"
    spec_path = ROOT / "artifacts/phase4/frozen_model_spec.json"
    access_path = ROOT / "artifacts/phase4/test_access_manifest.json"
    model_path = ROOT / "artifacts/phase4/models/purchase_catboost.cbm"
    val_path = ROOT / "artifacts/phase4/predictions/purchase_validation.parquet"
    test_path = ROOT / "artifacts/phase4/predictions/purchase_test.parquet"
    required = [manifest_path, spec_path, access_path, model_path, val_path, test_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"PHASE4_UPSTREAM_ARTIFACT_MISSING: {missing}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    access = json.loads(access_path.read_text(encoding="utf-8"))
    spec_without_hash = dict(spec)
    spec_without_hash.pop("frozen_model_spec_sha256", None)
    if _json_hash(spec_without_hash) != spec.get("frozen_model_spec_sha256") or spec.get("frozen_model_spec_sha256") != PHASE4_SPEC_SHA:
        raise RuntimeError("PHASE4_FROZEN_SPEC_FINGERPRINT_MISMATCH")
    if sha256_file(model_path) != PHASE4_MODEL_SHA or manifest.get("model_sha256") != PHASE4_MODEL_SHA:
        raise RuntimeError("PHASE4_MODEL_FINGERPRINT_MISMATCH")
    val = pd.read_parquet(val_path)
    test = pd.read_parquet(test_path)
    val_fp = prediction_fingerprint(val)
    test_fp = prediction_fingerprint(test)
    if val_fp != PHASE4_VALIDATION_PRED_SHA or test_fp != PHASE4_TEST_PRED_SHA:
        raise RuntimeError("PHASE4_PREDICTION_FINGERPRINT_MISMATCH")
    if manifest.get("validation_prediction_sha256") != PHASE4_VALIDATION_PRED_SHA or manifest.get("test_prediction_sha256") != PHASE4_TEST_PRED_SHA:
        raise RuntimeError("PHASE4_MANIFEST_PREDICTION_FINGERPRINT_MISMATCH")
    if access.get("model_sha256") != PHASE4_MODEL_SHA or access.get("prediction_sha256") != PHASE4_TEST_PRED_SHA:
        raise RuntimeError("PHASE4_TEST_ACCESS_FINGERPRINT_MISMATCH")
    if "official_probability" not in val.columns or "official_probability" not in test.columns:
        raise RuntimeError("PHASE4_OFFICIAL_PROBABILITY_MISSING")
    if not np.isfinite(val["official_probability"]).all() or not np.isfinite(test["official_probability"]).all():
        raise RuntimeError("PHASE4_OFFICIAL_PROBABILITY_NONFINITE")
    return {"manifest": manifest, "spec": spec, "access": access, "validation": val, "test": test, "model_path": model_path, "model_sha256": PHASE4_MODEL_SHA, "frozen_spec_sha256": PHASE4_SPEC_SHA, "validation_sha256": PHASE4_VALIDATION_PRED_SHA, "test_sha256": PHASE4_TEST_PRED_SHA}


def _verify_upstream(config: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    dataset_path = ROOT / config["phase2"]["dataset_path"]
    split_path = ROOT / config["phase3"]["split_path"]
    if not dataset_path.exists():
        raise RuntimeError("PHASE2_DATASET_MISSING")
    if not split_path.exists():
        raise RuntimeError("PHASE3_SPLIT_ASSIGNMENTS_MISSING")
    frame = pd.read_parquet(dataset_path)
    ordered_columns = [feature["name"] for feature in contract["features"]]
    dataset_sha = canonical_dataset_hash(frame, ordered_columns)
    if dataset_sha != PHASE2_SHA:
        raise RuntimeError(f"PHASE2_DATASET_FINGERPRINT_MISMATCH: {dataset_sha}")
    if len(frame) != 35000 or frame["PricingDecisionID"].nunique() != 35000:
        raise RuntimeError("PHASE2_ROW_COUNT_MISMATCH")
    purchases = int(frame["PurchasedFlag"].sum())
    if purchases != 6492 or int((frame["PurchasedFlag"] == 0).sum()) != 28508:
        raise RuntimeError("PHASE2_TARGET_COUNT_MISMATCH")
    assignments = pd.read_parquet(split_path)
    split_sha = sha256_file(split_path)
    summary_path = ROOT / config["phase3"]["split_summary_path"]
    expected_split_sha = json.loads(summary_path.read_text(encoding="utf-8"))["assignment_sha256"]
    if split_sha != PHASE3_SPLIT_SHA or expected_split_sha != PHASE3_SPLIT_SHA:
        raise RuntimeError("PHASE3_SPLIT_FINGERPRINT_MISMATCH")
    if assignments["PricingDecisionID"].duplicated().any() or set(assignments["PricingDecisionID"].astype(str)) != set(frame["PricingDecisionID"].astype(str)):
        raise RuntimeError("PHASE3_SPLIT_ID_SET_MISMATCH")
    merged = frame[["PricingDecisionID", "DecisionTime"]].assign(PricingDecisionID=lambda x: x["PricingDecisionID"].astype(str)).merge(assignments[["PricingDecisionID", "DecisionTime", "split"]].assign(PricingDecisionID=lambda x: x["PricingDecisionID"].astype(str)), on="PricingDecisionID", suffixes=("_data", "_split"), validate="one_to_one")
    if not (merged.groupby("split")["DecisionTime_data"].min().sort_values().index.tolist() == ["train", "validation", "test"]):
        raise RuntimeError("PHASE3_SPLIT_LABEL_FAILURE")
    if not merged.groupby("split")["DecisionTime_data"].max()["train"] < merged.groupby("split")["DecisionTime_data"].min()["validation"]:
        raise RuntimeError("PHASE3_TEMPORAL_ORDER_FAILURE")
    expected_health = {"train": (24500, 4581, 19919), "validation": (5250, 939, 4311), "test": (5250, 972, 4278)}
    health: dict[str, Any] = {}
    for split, expected in expected_health.items():
        part = _split_frame(frame, assignments, split)
        actual = (len(part), int(part["PurchasedFlag"].sum()), int((part["PurchasedFlag"] == 0).sum()))
        if actual != expected:
            raise RuntimeError(f"PHASE3_SPLIT_HEALTH_MISMATCH: {split} {actual}")
        health[split] = {"rows": actual[0], "purchases": actual[1], "non_purchases": actual[2], "start": _date(part["DecisionTime"].min()), "end": _date(part["DecisionTime"].max())}
    fold_manifest = json.loads((ROOT / config["phase3"]["fold_manifest_path"]).read_text(encoding="utf-8"))
    if len(fold_manifest) != 3:
        raise RuntimeError("PHASE3_FOLD_MANIFEST_MISMATCH")
    phase3_required = [config["phase3"]["validation_metrics_path"], config["phase3"]["test_metrics_path"], config["phase3"]["contract_path"], "artifacts/phase3/quantity_temporal_fold_metrics.csv"]
    for required in phase3_required:
        if not (ROOT / required).exists():
            raise RuntimeError(f"PHASE3_UPSTREAM_ARTIFACT_MISSING: {required}")
    phase4 = _verify_phase4()
    return {"frame": frame, "assignments": assignments, "dataset_sha256": dataset_sha, "split_assignment_sha256": split_sha, "health": health, "fold_manifest": fold_manifest, "phase4": phase4}


def _locked_folds(development: pd.DataFrame, fold_manifest: list[dict[str, Any]]) -> list[tuple[np.ndarray, np.ndarray]]:
    ordered = development.copy()
    ordered["DecisionTime"] = pd.to_datetime(ordered["DecisionTime"], errors="raise")
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for expected in fold_manifest:
        train_end = pd.Timestamp(expected["train_end"])
        validation_start = pd.Timestamp(expected["validation_start"])
        validation_end = pd.Timestamp(expected["validation_end"])
        train_indices = np.flatnonzero((ordered["DecisionTime"] <= train_end).to_numpy())
        validation_indices = np.flatnonzero(((ordered["DecisionTime"] >= validation_start) & (ordered["DecisionTime"] <= validation_end)).to_numpy())
        if len(train_indices) != int(expected["train_rows"]) or len(validation_indices) != int(expected["validation_rows"]):
            raise RuntimeError(f"PHASE3_FOLD_REUSE_MISMATCH: fold {expected['fold']}")
        if ordered.iloc[train_indices]["DecisionTime"].max() >= ordered.iloc[validation_indices]["DecisionTime"].min():
            raise RuntimeError("PHASE3_FOLD_CHRONOLOGY_FAILURE")
        folds.append((train_indices, validation_indices))
    return folds


def _quantity_target_audit(purchases: pd.DataFrame) -> dict[str, Any]:
    quantity = pd.to_numeric(purchases["QuantityPurchased"], errors="coerce")
    contradictions = purchases.loc[quantity.isna() | quantity.le(0), ["PricingDecisionID", "QuantityPurchased"]]
    all_rows = purchases.attrs.get("all_rows")
    if all_rows is None:
        nonpurchase_zero_ok = True
        nonpurchase_nonzero_or_nonnull_count = 0
    else:
        nonpurchases = all_rows.loc[all_rows["PurchasedFlag"].astype(int).eq(0), "QuantityPurchased"]
        nonpurchase_zero_ok = bool(nonpurchases.isna().all() or nonpurchases.fillna(0).eq(0).all())
        nonpurchase_nonzero_or_nonnull_count = int((nonpurchases.fillna(0) != 0).sum())
    result = {
        "rows": int(len(quantity)),
        "min": float(quantity.min()), "max": float(quantity.max()), "mean": float(quantity.mean()), "median": float(quantity.median()), "std": float(quantity.std(ddof=1)),
        "p01": float(quantity.quantile(0.01)), "p05": float(quantity.quantile(0.05)), "p25": float(quantity.quantile(0.25)), "p50": float(quantity.quantile(0.50)), "p75": float(quantity.quantile(0.75)), "p90": float(quantity.quantile(0.90)), "p95": float(quantity.quantile(0.95)), "p99": float(quantity.quantile(0.99)),
        "distinct_quantity_values": sorted(float(value) for value in quantity.unique()),
        "frequency_quantity_1": int((quantity == 1).sum()), "frequency_quantity_2": int((quantity == 2).sum()), "frequency_quantity_3": int((quantity == 3).sum()), "frequency_quantity_gt_3": int((quantity > 3).sum()),
        "percentage_quantity_1": float((quantity == 1).mean() * 100), "percentage_quantity_gt_1": float((quantity > 1).mean() * 100), "percentage_quantity_gt_2": float((quantity > 2).mean() * 100),
        "positive_integer_data": bool(np.all(quantity.gt(0) & np.isclose(quantity, np.round(quantity)))),
        "conditional_quantity_minimum": 1.0 if bool(np.all(quantity.gt(0))) else float(quantity.min()),
        "purchased_nonpositive_or_null_count": int(len(contradictions)),
        "target_concentration_warning": "near-degenerate" if float((quantity == 1).mean()) > 0.975 else ("highly concentrated" if float((quantity == 1).mean()) > 0.90 else ("concentrated" if float((quantity == 1).mean()) > 0.70 else "none")),
        "nonpurchase_zero_or_null_convention_checked": nonpurchase_zero_ok,
        "nonpurchase_nonzero_count": nonpurchase_nonzero_or_nonnull_count,
    }
    if len(contradictions):
        raise RuntimeError("QUANTITY_TARGET_INCONSISTENCY")
    return result


def _fold_health(development: pd.DataFrame, folds: list[tuple[np.ndarray, np.ndarray]], minimum: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fold, (train_indices, validation_indices) in enumerate(folds, start=1):
        train = development.iloc[train_indices].loc[development.iloc[train_indices]["PurchasedFlag"].astype(int).eq(1)]
        validation = development.iloc[validation_indices].loc[development.iloc[validation_indices]["PurchasedFlag"].astype(int).eq(1)]
        q_train = train["QuantityPurchased"].astype(float)
        q_validation = validation["QuantityPurchased"].astype(float)
        rows.extend([
            {"fold": fold, "population": "train", "rows": len(train), "date_min": _date(train["DecisionTime"].min()), "date_max": _date(train["DecisionTime"].max()), "quantity_mean": q_train.mean(), "quantity_median": q_train.median(), "quantity_std": q_train.std(ddof=1), "quantity_min": q_train.min(), "quantity_max": q_train.max(), "quantity_1_pct": (q_train.eq(1).mean() * 100), "quantity_gt_1_pct": (q_train.gt(1).mean() * 100), "distinct_ProductID": train["ProductID"].nunique(), "distinct_StoreID": train["StoreID"].nunique(), "distinct_CategoryID": train["CategoryID"].nunique()},
            {"fold": fold, "population": "validation", "rows": len(validation), "date_min": _date(validation["DecisionTime"].min()), "date_max": _date(validation["DecisionTime"].max()), "quantity_mean": q_validation.mean(), "quantity_median": q_validation.median(), "quantity_std": q_validation.std(ddof=1), "quantity_min": q_validation.min(), "quantity_max": q_validation.max(), "quantity_1_pct": (q_validation.eq(1).mean() * 100), "quantity_gt_1_pct": (q_validation.gt(1).mean() * 100), "distinct_ProductID": validation["ProductID"].nunique(), "distinct_StoreID": validation["StoreID"].nunique(), "distinct_CategoryID": validation["CategoryID"].nunique()},
        ])
    return pd.DataFrame(rows)


def _write_target_and_fold_artifacts(upstream: dict[str, Any], development: pd.DataFrame, folds: list[tuple[np.ndarray, np.ndarray]], minimum: float) -> tuple[dict[str, Any], pd.DataFrame]:
    purchases = upstream["frame"].loc[upstream["frame"]["PurchasedFlag"].astype(int).eq(1)].copy()
    purchases.attrs["all_rows"] = upstream["frame"]
    audit = _quantity_target_audit(purchases)
    write_json(ARTIFACTS / "quantity_target_audit.json", audit)
    health = _fold_health(development, folds, minimum)
    health.to_csv(ARTIFACTS / "quantity_fold_health.csv", index=False)
    return audit, health


def _baseline_fold_metrics(development: pd.DataFrame, folds: list[tuple[np.ndarray, np.ndarray]], minimum: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fold, (train_indices, validation_indices) in enumerate(folds, start=1):
        train = development.iloc[train_indices].loc[development.iloc[train_indices]["PurchasedFlag"].astype(int).eq(1)]
        validation = development.iloc[validation_indices].loc[development.iloc[validation_indices]["PurchasedFlag"].astype(int).eq(1)]
        mean = float(train["QuantityPurchased"].mean())
        pred = np.full(len(validation), mean, dtype=float)
        rows.append({"fold": fold, "model_name": "quantity_mean_baseline", "mean_quantity_train": mean, **quantity_metrics(validation["QuantityPurchased"], pred, raw=pred, minimum=minimum)})
    return pd.DataFrame(rows)


def _phase3_baselines() -> dict[str, Any]:
    return {
        "quantity_dummy_mean": json.loads((ROOT / "artifacts/phase3/quantity_validation_metrics.json").read_text(encoding="utf-8"))["quantity_dummy_mean"],
        "quantity_poisson_core": json.loads((ROOT / "artifacts/phase3/quantity_validation_metrics.json").read_text(encoding="utf-8"))["quantity_poisson_core"],
    }


def _fit_advanced(
    train: pd.DataFrame,
    validation: pd.DataFrame | None,
    contract: dict[str, Any],
    family: QuantityFeatureFamily,
    loss: str,
    params: dict[str, Any],
    *,
    thread_count: int,
    iterations: int,
    use_best_model: bool,
) -> tuple[CatBoostRegressor, np.ndarray | None, np.ndarray | None, int, float]:
    model, best_iteration, fit_seconds, _ = fit_quantity_regressor(
        train,
        validation,
        contract,
        family.feature_names,
        loss=loss,
        hyperparameters=params,
        thread_count=thread_count,
        iterations=iterations,
        random_seed=42,
        early_stopping_rounds=150 if validation is not None and len(validation) else None,
        use_best_model=use_best_model if validation is not None and len(validation) else False,
    )
    raw = None
    projected = None
    if validation is not None and len(validation):
        pool = make_quantity_pool(validation, contract, family.feature_names, validation["QuantityPurchased"])
        raw = predict_quantity_raw(model, pool)
        projected = project_quantity(raw, 1.0)
    return model, raw, projected, int(best_iteration), float(fit_seconds)


def _phase4_probability_map(predictions: pd.DataFrame, *, split: str) -> pd.DataFrame:
    result = predictions.copy()
    result["PricingDecisionID"] = result["PricingDecisionID"].astype(str)
    if "split" in result.columns and not result["split"].eq(split).all():
        raise RuntimeError(f"PHASE4_{split.upper()}_SPLIT_LABEL_MISMATCH")
    result["official_probability"] = pd.to_numeric(result["official_probability"], errors="raise")
    return result[["PricingDecisionID", "DecisionTime", "official_probability"]]


def _join_probabilities(frame: pd.DataFrame, phase4_predictions: pd.DataFrame, split: str) -> pd.DataFrame:
    base = frame.copy()
    base["PricingDecisionID"] = base["PricingDecisionID"].astype(str)
    probs = _phase4_probability_map(phase4_predictions, split=split)
    joined = base.merge(probs, on=["PricingDecisionID"], how="left", validate="one_to_one", suffixes=("", "_phase4"))
    if joined["official_probability"].isna().any():
        raise RuntimeError(f"PHASE4_{split.upper()}_ID_SET_MISMATCH")
    return joined


def _predictions_frame(
    frame: pd.DataFrame,
    *,
    split: str,
    raw: np.ndarray,
    projected: np.ndarray,
    estimator_type: str,
    probabilities: np.ndarray,
) -> pd.DataFrame:
    observed = observed_units(frame["PurchasedFlag"], frame["QuantityPurchased"])
    expected = compute_expected_units(probabilities, projected, minimum=1.0)
    result = pd.DataFrame({
        "PricingDecisionID": frame["PricingDecisionID"].astype(str).to_numpy(),
        "DecisionTime": pd.to_datetime(frame["DecisionTime"], errors="raise").to_numpy(),
        "split": split,
        "actual_PurchasedFlag": frame["PurchasedFlag"].astype(int).to_numpy(),
        "actual_QuantityPurchased": frame["QuantityPurchased"].astype(float).to_numpy(),
        "conditional_quantity_raw": np.asarray(raw, dtype=float),
        "conditional_quantity_official": np.asarray(projected, dtype=float),
        "quantity_estimator_type": estimator_type,
        "phase4_purchase_probability": np.asarray(probabilities, dtype=float),
        "expected_units": expected,
        "observed_units": observed,
    })
    if not np.isfinite(result.select_dtypes(include=[np.number]).to_numpy()).all():
        raise RuntimeError("NONFINITE_PHASE5_PREDICTIONS")
    return result


def _conditional_metrics(frame: pd.DataFrame, raw: np.ndarray, projected: np.ndarray) -> dict[str, Any]:
    purchased = frame["PurchasedFlag"].astype(int).to_numpy() == 1
    return quantity_metrics(frame.loc[purchased, "QuantityPurchased"], projected[purchased], raw=raw[purchased], minimum=1.0)


def _write_frozen_spec(
    *,
    phase4: dict[str, Any],
    family: QuantityFeatureFamily,
    loss: str,
    params: dict[str, Any],
    iterations: int,
    estimator_type: str,
    mean_value: float,
    minimum: float,
    compute: dict[str, Any],
) -> dict[str, Any]:
    features = list(family.feature_names)
    categorical = categorical_quantity_feature_names(load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml"), features)
    payload: dict[str, Any] = {
        "phase2_dataset_sha256": PHASE2_SHA,
        "phase3_split_assignment_sha256": PHASE3_SPLIT_SHA,
        "phase4_frozen_model_spec_sha256": phase4["frozen_spec_sha256"],
        "phase4_model_sha256": phase4["model_sha256"],
        "phase4_validation_prediction_sha256": phase4["validation_sha256"],
        "phase4_test_prediction_sha256": phase4["test_sha256"],
        "target": "QuantityPurchased",
        "population_filter": "PurchasedFlag == 1",
        "conditional_quantity_minimum": float(minimum),
        "quantity_support": "positive_integer_count; expected-value predictions remain continuous",
        "official_estimator_type": estimator_type,
        "selected_feature_family": family.name,
        "ordered_feature_names": features,
        "categorical_features": categorical,
        "numeric_features": [name for name in features if name not in set(categorical)],
        "selected_loss": loss,
        "hyperparameters": {**params, "loss_function": loss, "bootstrap_type": "Bayesian", "task_type": "CPU", "iterations_max": int(params.get("iterations", iterations))},
        "selected_iterations": int(iterations),
        "mean_fallback_value": float(mean_value),
        "domain_projection_policy": "np.maximum(raw_prediction, conditional_quantity_minimum)",
        "expected_units_formula": "phase4_official_probability * phase5_conditional_quantity_official",
        "random_seed": 42,
        "thread_count": int(compute["usable_threads"]),
        "candidate_price_adapter_version": "phase2.build_price_dependent_features.v1",
        "test_access_policy": "frozen specification required; TEST is evaluated once after final fit and never an eval_set",
        "catboost_version": catboost_version,
    }
    payload["frozen_quantity_spec_sha256"] = _json_hash(payload)
    write_json(ARTIFACTS / "frozen_quantity_spec.json", payload)
    return payload


def _require_frozen_spec() -> dict[str, Any]:
    path = ARTIFACTS / "frozen_quantity_spec.json"
    if not path.exists():
        raise RuntimeError("FROZEN_QUANTITY_SPEC_REQUIRED_BEFORE_TEST")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.get("frozen_quantity_spec_sha256")
    without_hash = dict(payload)
    without_hash.pop("frozen_quantity_spec_sha256", None)
    if expected != _json_hash(without_hash):
        raise RuntimeError("FROZEN_QUANTITY_SPEC_HASH_MISMATCH")
    return payload


def _write_phase3_reference() -> None:
    reference = {
        "source": "artifacts/phase3/quantity_validation_metrics.json and quantity_test_metrics.json",
        "validation": json.loads((ROOT / "artifacts/phase3/quantity_validation_metrics.json").read_text(encoding="utf-8")),
        "test": json.loads((ROOT / "artifacts/phase3/quantity_test_metrics.json").read_text(encoding="utf-8")),
    }
    write_json(ARTIFACTS / "phase3_quantity_baselines.json", reference)


def _write_phase5_contract(*, selection: dict[str, Any], estimator_type: str, mean_value: float, minimum: float, spec: dict[str, Any], compute: dict[str, Any]) -> None:
    """Materialize the reviewed Phase 5 contract without touching prior contracts."""
    path = ROOT / "contracts/phase5_quantity_demand_contract_v1.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["selected_feature_family"] = selection["selected_feature_family"]
    payload["selected_loss"] = selection["selected_loss"]
    payload["official_estimator"]["type"] = estimator_type
    payload["official_estimator"]["fallback_mean_value"] = float(mean_value)
    payload["official_estimator"]["selected_iterations"] = int(spec["selected_iterations"])
    payload["official_estimator"]["frozen_quantity_spec_sha256"] = spec["frozen_quantity_spec_sha256"]
    payload["target"]["support"]["minimum"] = float(minimum)
    payload["compute"]["catboost_threads_used"] = int(compute["usable_threads"])
    payload["compute"]["catboost_version"] = catboost_version
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _feature_importance(model: CatBoostRegressor, family: QuantityFeatureFamily, contract: dict[str, Any]) -> pd.DataFrame:
    values = model.get_feature_importance()
    groups: dict[str, str] = {}
    for group in ["HIGH_CARDINALITY_CONTEXT", "COMPETITOR_CONTEXT", "BEHAVIOR_CONTEXT", "CUSTOMER_CONTEXT"]:
        for name in family.feature_names:
            from models.quantity_data import CONDITIONAL_GROUP_NAMES
            if name in CONDITIONAL_GROUP_NAMES[group]:
                groups[name] = group
    entries = {item["name"]: item for item in contract["features"]}
    return pd.DataFrame({
        "feature": list(family.feature_names),
        "importance": np.asarray(values, dtype=float),
        "feature_group": [groups.get(name, "CORE") for name in family.feature_names],
        "conditional": [bool(entries[name].get("conditional", False)) for name in family.feature_names],
        "price_related": [bool(entries[name].get("price_dependent", False)) for name in family.feature_names],
    }).sort_values(["importance", "feature"], ascending=[False, True], kind="mergesort")


def _candidate_price_parity(
    validation: pd.DataFrame,
    contract: dict[str, Any],
    family: QuantityFeatureFamily,
    estimator: ConditionalQuantityEstimator,
    phase4: dict[str, Any],
) -> dict[str, Any]:
    historical_quantity = prepare_quantity_catboost_frame(validation, contract, family.feature_names)
    candidate_quantity = build_quantity_model_features_for_candidate_price(validation, validation["AppliedPrice"].to_numpy(float), contract, family.feature_names)
    feature_equal = historical_quantity.columns.tolist() == candidate_quantity.columns.tolist() and historical_quantity.dtypes.tolist() == candidate_quantity.dtypes.tolist()
    numeric_delta = float(np.nanmax(np.abs(historical_quantity.select_dtypes(include=[np.number]).to_numpy(float) - candidate_quantity.select_dtypes(include=[np.number]).to_numpy(float)))) if feature_equal else float("inf")
    categorical_equal = all(historical_quantity[name].astype(str).equals(candidate_quantity[name].astype(str)) for name in categorical_quantity_feature_names(contract, family.feature_names))
    feature_parity = bool(feature_equal and categorical_equal and numeric_delta <= 1e-10)
    historical_q = estimator.predict_conditional_quantity(validation)
    candidate_q = estimator.predict_conditional_quantity(candidate_quantity)
    quantity_delta = float(np.max(np.abs(historical_q - candidate_q)))

    # Reuse the frozen Phase 4 model and its immutable feature adapter.
    from models.catboost_data import build_purchase_model_features_for_candidate_price, make_catboost_pool, prepare_catboost_frame
    purchase_contract = contract
    phase4_features = tuple(phase4["spec"]["ordered_feature_names"])
    purchase_model = CatBoostClassifier()
    purchase_model.load_model(str(phase4["model_path"]))
    historical_purchase = prepare_catboost_frame(validation, purchase_contract, phase4_features)
    candidate_purchase = build_purchase_model_features_for_candidate_price(validation, validation["AppliedPrice"].to_numpy(float), purchase_contract, phase4_features)
    phase4_historical_prob = purchase_model.predict_proba(make_catboost_pool(validation, purchase_contract, phase4_features))[:, 1]
    phase4_candidate_prob = purchase_model.predict_proba(make_catboost_pool(candidate_purchase, purchase_contract, phase4_features))[:, 1]
    purchase_delta = float(np.max(np.abs(phase4_historical_prob - phase4_candidate_prob)))
    integrated_historical = compute_expected_units(phase4_historical_prob, historical_q, minimum=1.0)
    integrated_candidate = compute_expected_units(phase4_candidate_prob, candidate_q, minimum=1.0)
    integrated_delta = float(np.max(np.abs(integrated_historical - integrated_candidate)))
    result = {
        "candidate_price_definition": "CandidatePrice = historical AppliedPrice",
        "feature_violations": 0 if feature_parity else 1,
        "feature_parity": feature_parity,
        "max_numeric_feature_delta": float(numeric_delta),
        "quantity_prediction_delta": quantity_delta,
        "phase4_purchase_probability_delta": purchase_delta,
        "expected_unit_prediction_delta": integrated_delta,
        "integrated_parity": bool(feature_parity and quantity_delta <= 1e-10 and integrated_delta <= 1e-10),
        "tolerance": 1e-10,
    }
    if not result["integrated_parity"]:
        raise RuntimeError("QUANTITY_TRAIN_INFERENCE_PARITY_FAILURE")
    write_json(ARTIFACTS / "integrated_candidate_parity.json", result)
    return result


def _write_reports(
    *,
    audit: dict[str, Any],
    selection: dict[str, Any],
    hpo_summary: dict[str, Any],
    validation_mean: dict[str, Any],
    validation_advanced: dict[str, Any],
    adoption: dict[str, Any],
    estimator_type: str,
    validation_expected: dict[str, dict[str, Any]],
    test_expected: dict[str, dict[str, Any]],
    parity: dict[str, Any],
    spec: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    docs = ROOT / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    quantity_report = f"""# Phase 5 Conditional Quantity Model Report

## Target and population

The target is `QuantityPurchased` on the purchased-only population (`PurchasedFlag == 1`). The frozen audit contains **{audit['rows']}** rows, support **{audit['min']:.0f}–{audit['max']:.0f}**, mean **{audit['mean']:.6f}**, median **{audit['median']:.6f}**, and standard deviation **{audit['std']:.6f}**. Quantity one represents **{audit['percentage_quantity_1']:.3f}%** of purchases; this is a measured **{audit['target_concentration_warning']}** target, with no synthetic augmentation.

## Screening and HPO

All QF0–QF8 families and the Phase 4 `F3_CORE_BEHAVIOR` reference were screened under fixed RMSE and Poisson objectives on the three purchased TRAIN folds. The selected screening candidate was **{selection['selected_feature_family']} / {selection['selected_loss']}**. Optuna used a serial TPE sampler with seed 42 and **{hpo_summary['requested_trials']}** requested trials; **{hpo_summary['completed_trials']}** completed.

Selected HPO parameters and complete fold rows are in `artifacts/phase5/best_hyperparameters.json` and `artifacts/phase5/hpo_trials.csv`.

## Validation materiality gate

| Estimator | MAE | RMSE | R² | Poisson deviance | Bias |
|---|---:|---:|---:|---:|---:|
| TRAIN mean | {validation_mean['mae']:.6f} | {validation_mean['rmse']:.6f} | {validation_mean['r2'] if validation_mean['r2'] is not None else 'NA'} | {validation_mean['mean_poisson_deviance']:.6f} | {validation_mean['bias']:.6f} |
| Advanced diagnostic | {validation_advanced['mae']:.6f} | {validation_advanced['rmse']:.6f} | {validation_advanced['r2'] if validation_advanced['r2'] is not None else 'NA'} | {validation_advanced['mean_poisson_deviance']:.6f} | {validation_advanced['bias']:.6f} |

The predeclared adoption gate chose **{estimator_type}**. Gate details are persisted in `artifacts/phase5/adoption_gate.json`; CatBoost is never promoted merely because it was trained.

## Frozen specification

The specification was hashed before TEST: `{spec['frozen_quantity_spec_sha256']}`. The declared support projection is `max(raw_prediction, {spec['conditional_quantity_minimum']})`; predictions remain continuous and are never rounded.
"""
    (docs / "PHASE5_QUANTITY_MODEL_REPORT.md").write_text(quantity_report, encoding="utf-8")
    demand_report = f"""# Phase 5 Expected Demand Report

Expected units are computed only as `Phase 4 official_probability × Phase 5 conditional_quantity`; actual `PurchasedFlag` is used only to form the evaluation target `ObservedUnits`.

## Validation

| Stack | MAE | RMSE | Poisson deviance | Aggregate units error % |
|---|---:|---:|---:|---:|
| P × mean Q | {validation_expected['mean']['mae']:.6f} | {validation_expected['mean']['rmse']:.6f} | {validation_expected['mean']['mean_poisson_deviance']:.6f} | {validation_expected['mean']['aggregate_units_error_pct']:.6f} |
| P × advanced Q | {validation_expected['advanced']['mae']:.6f} | {validation_expected['advanced']['rmse']:.6f} | {validation_expected['advanced']['mean_poisson_deviance']:.6f} | {validation_expected['advanced']['aggregate_units_error_pct']:.6f} |
| P × official Q | {validation_expected['official']['mae']:.6f} | {validation_expected['official']['rmse']:.6f} | {validation_expected['official']['mean_poisson_deviance']:.6f} | {validation_expected['official']['aggregate_units_error_pct']:.6f} |

The expected-unit decile table is `artifacts/phase5/expected_units_validation_calibration.csv`. Candidate-price parity is **{parity['integrated_parity']}** with maximum expected-unit delta **{parity['expected_unit_prediction_delta']:.3e}**.

## Holdout

TEST was accessed once after the frozen specification. Full metrics are in `artifacts/phase5/test_expected_units_metrics.json` and the immutable prediction artifact.
"""
    (docs / "PHASE5_EXPECTED_DEMAND_REPORT.md").write_text(demand_report, encoding="utf-8")
    acceptance = f"""# Phase 5 Acceptance Report

## 1. Executive verdict

**{manifest['result']}** — official estimator **{estimator_type}**. Recommendation: **{manifest['recommendation']}**.

## 2. Upstream verification

Phase 2 canonical SHA `{PHASE2_SHA}`; Phase 3 split SHA `{PHASE3_SPLIT_SHA}`; Phase 4 frozen spec/model/predictions were verified against the accepted fingerprints. Earlier phase artifacts and contracts were not modified.

## 3–15. Quantity evidence

Target audit, purchased-only counts, fold health, Phase 3 references, QF0–QF8 screening, RMSE/Poisson comparison, HPO, validation metrics, gate decision, and support projection are committed under `artifacts/phase5/`.

## 16–20. Demand integration and parity

The official Phase 4 probabilities were joined by decision ID without recalibration. Validation and TEST expected-unit metrics use all decisions; candidate-price feature, quantity, and integrated parity passed at the declared tolerance.

## 21–25. Freeze and TEST

The frozen quantity spec was written and hash-checked before one TEST access. No TEST labels were used for screening, HPO, estimator selection, or retraining. No post-TEST model switch was performed.

## 26–30. Reproducibility, limitations, and recommendation

Compute, reproducibility, model/fallback serialization, test evidence, warnings, blockers, and the Phase 6 recommendation are recorded in `artifacts/phase5/phase5_manifest.json`. Phase 5 does not optimize prices, revenue, margin, or pricing rules.
"""
    (docs / "PHASE5_ACCEPTANCE_REPORT.md").write_text(acceptance, encoding="utf-8")


def _run_phase5_tests() -> dict[str, Any]:
    path = ARTIFACTS / "test_results.json"
    env = os.environ.copy()
    env["TEST_EVIDENCE_PATH"] = str(path)
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/phase5", "-q"], cwd=ROOT, env=env, check=False)
    if not path.exists():
        raise RuntimeError("PHASE5_TEST_EVIDENCE_MISSING")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["runner_exit_code"] = int(result.returncode)
    if result.returncode != 0 or evidence.get("failed", 0) != 0 or evidence.get("status") != "PASS":
        raise RuntimeError(f"PHASE5_TESTS_FAILED: {evidence}")
    write_json(path, evidence)
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
    started_at = time.perf_counter()
    warnings: list[str] = []
    blockers: list[str] = []
    try:
        tests = _run_phase5_tests()
        contract = load_contract(ROOT / config["phase2"]["contract_path"])
        upstream = _verify_upstream(config, contract)
        frame = upstream["frame"]
        assignments = upstream["assignments"]
        train = _split_frame(frame, assignments, "train")
        validation = _split_frame(frame, assignments, "validation")
        test = _split_frame(frame, assignments, "test")
        development = train.sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)
        folds = _locked_folds(development, upstream["fold_manifest"])
        minimum = 1.0
        audit, fold_health = _write_target_and_fold_artifacts(upstream, development, folds, minimum)
        _write_phase3_reference()
        if not audit["positive_integer_data"] or audit["purchased_nonpositive_or_null_count"] or not audit["nonpurchase_zero_or_null_convention_checked"]:
            raise RuntimeError("QUANTITY_TARGET_INCONSISTENCY")

        target_counts = {
            "total_purchased": int(frame["PurchasedFlag"].sum()),
            "train_purchased": int(train["PurchasedFlag"].sum()),
            "validation_purchased": int(validation["PurchasedFlag"].sum()),
            "test_purchased": int(test["PurchasedFlag"].sum()),
        }
        if target_counts != {"total_purchased": 6492, "train_purchased": 4581, "validation_purchased": 939, "test_purchased": 972}:
            raise RuntimeError(f"QUANTITY_POPULATION_COUNT_MISMATCH: {target_counts}")
        write_json(ARTIFACTS / "quantity_population_counts.json", target_counts)

        families = build_quantity_feature_families(contract)
        screening_started = time.perf_counter()
        screening_path = ARTIFACTS / "quantity_feature_screening.csv"
        selection_path = ARTIFACTS / "quantity_feature_selection.json"
        if os.environ.get("PHASE5_REUSE_SCREENING") == "1" and screening_path.exists() and selection_path.exists():
            screening_output = pd.read_csv(screening_path)
            fold_screening = screening_output[screening_output["row_type"] == "fold"].copy()
            screening_summary = screening_output[screening_output["row_type"] == "aggregate"].copy()
            selection = json.loads(selection_path.read_text(encoding="utf-8"))
            screening_seconds = float(pd.to_numeric(fold_screening.get("fit_seconds", 0), errors="coerce").fillna(0).sum() + pd.to_numeric(fold_screening.get("prediction_seconds", 0), errors="coerce").fillna(0).sum())
        else:
            fold_screening, screening_summary = screen_quantity_feature_families(development, folds, contract, families, thread_count=compute["usable_threads"], iterations=config["compute"]["screening_iterations"], minimum=minimum)
            screening_output = pd.concat([fold_screening, screening_summary], ignore_index=True, sort=False)
            screening_output.to_csv(screening_path, index=False)
            selection = select_quantity_feature_loss(fold_screening, screening_summary, families)
            write_json(selection_path, selection)
            screening_seconds = time.perf_counter() - screening_started
        selected_family = families[selection["selected_feature_family"]]
        selected_loss = str(selection["selected_loss"])

        hpo_started = time.perf_counter()
        hpo_trials = int(os.environ.get("PHASE5_HPO_TRIALS", config["compute"]["hpo_trials"]))
        hpo_trials_path = ARTIFACTS / "hpo_trials.csv"
        hpo_summary_path = ARTIFACTS / "hpo_summary.json"
        best_hp_path = ARTIFACTS / "best_hyperparameters.json"
        if os.environ.get("PHASE5_REUSE_HPO") == "1" and hpo_trials_path.exists() and hpo_summary_path.exists() and best_hp_path.exists():
            hpo_frame = pd.read_csv(hpo_trials_path)
            hpo_summary = json.loads(hpo_summary_path.read_text(encoding="utf-8"))
            best_hp_payload = json.loads(best_hp_path.read_text(encoding="utf-8"))
            hpo_params = best_hp_payload["parameters"]
            hpo_choice = {"parameters": hpo_params, "trial": best_hp_payload["trial_number"]}
            hpo_seconds = float(pd.to_numeric(hpo_frame.get("duration_seconds", 0), errors="coerce").fillna(0).sum())
        else:
            hpo_frame, hpo_summary, hpo_choice = run_quantity_hpo(development, folds, contract, selected_family.feature_names, loss=selected_loss, thread_count=compute["usable_threads"], n_trials=hpo_trials, seed=42, max_iterations=config["compute"]["max_iterations"], minimum=minimum)
            hpo_frame.to_csv(hpo_trials_path, index=False)
            hpo_params = hpo_choice["parameters"]
            write_json(hpo_summary_path, hpo_summary)
            write_json(best_hp_path, {"feature_family": selected_family.name, "loss": selected_loss, "trial_number": hpo_choice["trial"], "parameters": hpo_params, "max_iterations": config["compute"]["max_iterations"]})
            hpo_seconds = time.perf_counter() - hpo_started

        # Official VALIDATION is first opened only after screening and HPO.
        train_purchased = train.loc[train["PurchasedFlag"].astype(int).eq(1)].copy()
        validation_purchased = validation.loc[validation["PurchasedFlag"].astype(int).eq(1)].copy()
        mean_train = float(train_purchased["QuantityPurchased"].mean())
        mean_validation_raw = np.full(len(validation_purchased), mean_train, dtype=float)
        validation_mean_metrics = quantity_metrics(validation_purchased["QuantityPurchased"], mean_validation_raw, raw=mean_validation_raw, minimum=minimum)
        write_json(ARTIFACTS / "validation_mean_metrics.json", validation_mean_metrics)

        validation_model, validation_raw, validation_projected, best_iteration, validation_fit_seconds = _fit_advanced(train_purchased, validation_purchased, contract, selected_family, selected_loss, hpo_params, thread_count=compute["usable_threads"], iterations=min(int(hpo_params.get("iterations", config["compute"]["max_iterations"])), int(config["compute"]["max_iterations"])), use_best_model=True)
        assert validation_raw is not None and validation_projected is not None
        validation_advanced_metrics = quantity_metrics(validation_purchased["QuantityPurchased"], validation_projected, raw=validation_raw, minimum=minimum)
        validation_advanced_metrics["best_iteration"] = int(best_iteration)
        validation_advanced_metrics["best_score"] = validation_model.get_best_score()
        write_json(ARTIFACTS / "validation_advanced_metrics.json", validation_advanced_metrics)
        adoption = adoption_gate(validation_mean_metrics, validation_advanced_metrics)
        write_json(ARTIFACTS / "adoption_gate.json", adoption)
        estimator_type = str(adoption["decision"])

        validation_joined = _join_probabilities(validation, upstream["phase4"]["validation"], "validation")
        validation_mean_all_raw = np.full(len(validation), mean_train, dtype=float)
        validation_mean_all = project_quantity(validation_mean_all_raw, minimum)
        validation_adv_pool = make_quantity_pool(validation, contract, selected_family.feature_names)
        validation_adv_all_raw = predict_quantity_raw(validation_model, validation_adv_pool)
        validation_adv_all = project_quantity(validation_adv_all_raw, minimum)
        validation_official_all = validation_adv_all if estimator_type == "CATBOOST" else validation_mean_all
        actual_validation_units = observed_units(validation_joined["PurchasedFlag"], validation_joined["QuantityPurchased"])
        validation_probs = validation_joined["official_probability"].to_numpy(float)
        validation_expected = {
            "mean": expected_units_metrics(actual_validation_units, compute_expected_units(validation_probs, validation_mean_all, minimum=minimum)),
            "advanced": expected_units_metrics(actual_validation_units, compute_expected_units(validation_probs, validation_adv_all, minimum=minimum)),
            "official": expected_units_metrics(actual_validation_units, compute_expected_units(validation_probs, validation_official_all, minimum=minimum)),
        }
        write_json(ARTIFACTS / "validation_expected_units_metrics.json", validation_expected)
        calibration = expected_units_calibration(actual_validation_units, compute_expected_units(validation_probs, validation_official_all, minimum=minimum))
        calibration.to_csv(ARTIFACTS / "expected_units_validation_calibration.csv", index=False)
        integrated_gate = integrated_safety_gate(validation_expected["mean"], validation_expected["advanced"])
        write_json(ARTIFACTS / "integrated_safety_gate.json", integrated_gate)
        if estimator_type == "CATBOOST" and integrated_gate["triggered"]:
            estimator_type = "CONSTANT_MEAN"
            warnings.append("integrated expected-unit safety gate selected CONSTANT_MEAN")

        # Freeze the specification before any TEST data are read for metrics.
        mean_train_validation = float(pd.concat([train_purchased, validation_purchased], ignore_index=True)["QuantityPurchased"].mean())
        spec = _write_frozen_spec(phase4=upstream["phase4"], family=selected_family, loss=selected_loss, params=hpo_params, iterations=int(best_iteration + 1), estimator_type=estimator_type, mean_value=mean_train_validation, minimum=minimum, compute=compute)
        _write_phase5_contract(selection=selection, estimator_type=estimator_type, mean_value=mean_train_validation, minimum=minimum, spec=spec, compute=compute)

        # Final advanced diagnostic and official estimator use TRAIN+VALIDATION only.
        train_validation_purchased = pd.concat([train_purchased, validation_purchased], ignore_index=True).sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)
        final_advanced_started = time.perf_counter()
        final_advanced_model, _, _, _, final_advanced_fit_seconds = _fit_advanced(train_validation_purchased, None, contract, selected_family, selected_loss, hpo_params, thread_count=compute["usable_threads"], iterations=int(spec["selected_iterations"]), use_best_model=False)
        final_fit_seconds = time.perf_counter() - final_advanced_started
        if estimator_type == "CATBOOST":
            final_estimator = ConditionalQuantityEstimator("CATBOOST", model=final_advanced_model, contract=contract, feature_names=selected_family.feature_names, minimum=minimum)
            final_estimator.model.save_model(str(MODEL_DIR / "conditional_quantity_catboost.cbm"))
        else:
            final_estimator = ConditionalQuantityEstimator("CONSTANT_MEAN", mean_value=mean_train_validation, contract=contract, feature_names=selected_family.feature_names, minimum=minimum)
            write_json(MODEL_DIR / "conditional_quantity_mean.json", {"estimator_type": "CONSTANT_MEAN", "mean_value": mean_train_validation, "conditional_quantity_minimum": minimum})
        save_quantity_estimator_metadata(MODEL_DIR / "quantity_estimator_metadata.json", final_estimator, selected_feature_family=selected_family.name, selected_loss=selected_loss, selected_iterations=int(spec["selected_iterations"]), phase4_frozen_model_spec_sha256=PHASE4_SPEC_SHA)
        _feature_importance(final_advanced_model, selected_family, contract).to_csv(ARTIFACTS / "quantity_feature_importance.csv", index=False)

        # Enforce the TEST lock and evaluate the holdout exactly once.
        _require_frozen_spec()
        test_joined = _join_probabilities(test, upstream["phase4"]["test"], "test")
        test_advanced_pool = make_quantity_pool(test, contract, selected_family.feature_names)
        test_advanced_raw = predict_quantity_raw(final_advanced_model, test_advanced_pool)
        test_advanced_projected = project_quantity(test_advanced_raw, minimum)
        test_mean_raw = np.full(len(test), mean_train_validation, dtype=float)
        test_mean_projected = project_quantity(test_mean_raw, minimum)
        test_official_raw = test_advanced_raw if estimator_type == "CATBOOST" else test_mean_raw
        test_official_projected = test_advanced_projected if estimator_type == "CATBOOST" else test_mean_projected
        val_prediction_artifact = _predictions_frame(validation, split="validation", raw=(validation_adv_all_raw if estimator_type == "CATBOOST" else validation_mean_all_raw), projected=validation_official_all, estimator_type=estimator_type, probabilities=validation_probs)
        test_probs = test_joined["official_probability"].to_numpy(float)
        test_prediction_artifact = _predictions_frame(test, split="test", raw=test_official_raw, projected=test_official_projected, estimator_type=estimator_type, probabilities=test_probs)
        val_prediction_artifact.to_parquet(PREDICTION_DIR / "quantity_validation.parquet", index=False)
        test_prediction_artifact.to_parquet(PREDICTION_DIR / "quantity_test.parquet", index=False)
        val_expected_artifact = val_prediction_artifact[["PricingDecisionID", "DecisionTime", "split", "phase4_purchase_probability", "conditional_quantity_official", "expected_units", "observed_units"]].copy()
        test_expected_artifact = test_prediction_artifact[["PricingDecisionID", "DecisionTime", "split", "phase4_purchase_probability", "conditional_quantity_official", "expected_units", "observed_units"]].copy()
        val_expected_artifact.to_parquet(ARTIFACTS / "expected_demand_validation.parquet", index=False)
        test_expected_artifact.to_parquet(ARTIFACTS / "expected_demand_test.parquet", index=False)

        test_actual_units = test_prediction_artifact["observed_units"].to_numpy(float)
        test_expected = {
            "mean": expected_units_metrics(test_actual_units, compute_expected_units(test_probs, test_mean_projected, minimum=minimum)),
            "advanced": expected_units_metrics(test_actual_units, compute_expected_units(test_probs, test_advanced_projected, minimum=minimum)),
            "official": expected_units_metrics(test_actual_units, compute_expected_units(test_probs, test_official_projected, minimum=minimum)),
        }
        write_json(ARTIFACTS / "test_expected_units_metrics.json", test_expected)
        test_conditional = {
            "mean": _conditional_metrics(test, test_mean_raw, test_mean_projected),
            "advanced": _conditional_metrics(test, test_advanced_raw, test_advanced_projected),
            "official": _conditional_metrics(test, test_official_raw, test_official_projected),
        }
        write_json(ARTIFACTS / "test_conditional_metrics.json", test_conditional)
        test_access = {"test_access_count": 1, "test_access_reason": "FINAL_PHASE5_BENCHMARK_AFTER_FROZEN_SPEC", "frozen_quantity_spec_sha256": spec["frozen_quantity_spec_sha256"], "phase4_test_prediction_sha256": PHASE4_TEST_PRED_SHA, "test_prediction_sha256": prediction_fingerprint(test_prediction_artifact), "test_start": _date(test["DecisionTime"].min()), "test_end": _date(test["DecisionTime"].max()), "test_used_for_selection": False, "test_used_for_hpo": False}
        write_json(ARTIFACTS / "test_access_manifest.json", test_access)

        # Candidate-price parity is evaluated on historical validation rows only.
        parity = _candidate_price_parity(validation, contract, selected_family, final_estimator, upstream["phase4"])
        scenario_rows = []
        for multiplier in (0.9, 1.0, 1.1):
            candidate = validation["CurrentPrice"].to_numpy(float) * multiplier
            candidate_features = build_quantity_model_features_for_candidate_price(validation, candidate, contract, selected_family.feature_names)
            scenario_quantity = final_estimator.predict_conditional_quantity(candidate_features)
            scenario_rows.append({"multiplier": multiplier, "mean_conditional_quantity": float(scenario_quantity.mean()), "min_conditional_quantity": float(scenario_quantity.min()), "max_conditional_quantity": float(scenario_quantity.max()), "diagnostic_only": True})
        pd.DataFrame(scenario_rows).to_csv(ARTIFACTS / "quantity_price_sensitivity_diagnostic.csv", index=False)

        # Deterministic reproducibility is checked before reporting completion.
        reproducibility: dict[str, Any]
        if estimator_type == "CATBOOST":
            repeat_one, _, _, _, _ = _fit_advanced(train_purchased, validation_purchased, contract, selected_family, selected_loss, hpo_params, thread_count=compute["usable_threads"], iterations=int(spec["selected_iterations"]), use_best_model=False)
            repeat_two, _, _, _, _ = _fit_advanced(train_purchased, validation_purchased, contract, selected_family, selected_loss, hpo_params, thread_count=compute["usable_threads"], iterations=int(spec["selected_iterations"]), use_best_model=False)
            pool = make_quantity_pool(validation_purchased, contract, selected_family.feature_names)
            delta = float(np.max(np.abs(project_quantity(predict_quantity_raw(repeat_one, pool), minimum) - project_quantity(predict_quantity_raw(repeat_two, pool), minimum))))
            reproducibility = {"estimator_type": "CATBOOST", "same_best_iteration": model_best_iteration(repeat_one) == model_best_iteration(repeat_two), "best_iteration_one": model_best_iteration(repeat_one), "best_iteration_two": model_best_iteration(repeat_two), "max_prediction_delta": delta, "tolerance": 1e-10, "status": "PASS" if model_best_iteration(repeat_one) == model_best_iteration(repeat_two) and delta <= 1e-10 else "FAIL"}
        else:
            mean_again = float(pd.concat([train_purchased, validation_purchased], ignore_index=True)["QuantityPurchased"].mean())
            reproducibility = {"estimator_type": "CONSTANT_MEAN", "mean_value": mean_train_validation, "repeated_mean_value": mean_again, "max_prediction_delta": abs(mean_train_validation - mean_again), "tolerance": 0.0, "status": "PASS" if mean_train_validation == mean_again else "FAIL"}
        write_json(ARTIFACTS / "reproducibility.json", reproducibility)
        if reproducibility["status"] != "PASS":
            raise RuntimeError("REPRODUCIBILITY_FAILURE")

        compute["catboost_version"] = catboost_version
        compute["python_version"] = sys.version
        compute["platform"] = platform.platform()
        write_json(ARTIFACTS / "compute_environment.json", compute)
        write_json(ARTIFACTS / "compute_benchmark.json", {"screening_seconds": screening_seconds, "hpo_seconds": hpo_seconds, "validation_fit_seconds": validation_fit_seconds, "final_fit_seconds": final_fit_seconds, "threads_used": compute["usable_threads"], "hpo_trials": hpo_summary["requested_trials"], "total_seconds": screening_seconds + hpo_seconds + validation_fit_seconds + final_fit_seconds})

        if estimator_type == "CATBOOST":
            test_collapse = test_conditional["official"]["rmse"] > test_conditional["mean"]["rmse"] and test_conditional["official"]["mae"] > test_conditional["mean"]["mae"] and test_conditional["official"]["mean_poisson_deviance"] > test_conditional["mean"]["mean_poisson_deviance"] and test_expected["official"]["rmse"] > test_expected["mean"]["rmse"] and test_expected["official"]["mean_poisson_deviance"] > test_expected["mean"]["mean_poisson_deviance"]
            if test_collapse:
                raise RuntimeError("HOLDOUT_QUANTITY_GENERALIZATION_FAILURE")
        if audit["percentage_quantity_1"] > 70:
            warnings.append(f"quantity target is concentrated: {audit['percentage_quantity_1']:.3f}% at one")
        if estimator_type == "CONSTANT_MEAN":
            warnings.append("advanced conditional quantity model did not pass the predeclared materiality gate; constant mean retained")
        warnings.append("conditional quantity and price responses are predictive diagnostics, not causal elasticity")

        manifest = {
            "result": "PASS_WITH_WARNINGS" if warnings else "PASS",
            "recommendation": "PROCEED_TO_PHASE_6",
            "base_branch": BASE_BRANCH,
            "base_git_sha": os.environ.get("PHASE5_BASE_SHA", "71cf347ee049d82302e874a021958a91d341ccb5"),
            "implementation_git_sha": os.environ.get("PHASE5_IMPLEMENTATION_SHA", _git_sha()),
            "evidence_git_sha": os.environ.get("PHASE5_EVIDENCE_SHA", _git_sha()),
            "phase2_dataset_sha": PHASE2_SHA,
            "phase3_split_sha": PHASE3_SPLIT_SHA,
            "phase4_frozen_spec_sha": PHASE4_SPEC_SHA,
            "phase4_model_sha": PHASE4_MODEL_SHA,
            "phase4_validation_prediction_sha": PHASE4_VALIDATION_PRED_SHA,
            "phase4_test_prediction_sha": PHASE4_TEST_PRED_SHA,
            "quantity_population_counts": target_counts,
            "quantity_target_summary": audit,
            "selected_feature_family": selected_family.name,
            "selected_loss": selected_loss,
            "advanced_model_metrics": validation_advanced_metrics,
            "official_estimator_type": estimator_type,
            "fallback_mean_value": mean_train_validation,
            "conditional_quantity_minimum": minimum,
            "validation_conditional_metrics": {"mean": validation_mean_metrics, "advanced": validation_advanced_metrics, "official": validation_advanced_metrics if estimator_type == "CATBOOST" else validation_mean_metrics},
            "test_conditional_metrics": test_conditional,
            "validation_expected_units_metrics": validation_expected,
            "test_expected_units_metrics": test_expected,
            "candidate_parity": parity,
            "reproducibility": reproducibility,
            "compute": compute,
            "tests": tests,
            "ci_status": "PENDING",
            "warnings": warnings,
            "major_blockers": blockers,
            "frozen_quantity_spec_sha256": spec["frozen_quantity_spec_sha256"],
            "screening_seconds": screening_seconds,
            "hpo_seconds": hpo_seconds,
        }
        write_json(ARTIFACTS / "phase5_manifest.json", manifest)
        _write_reports(audit=audit, selection=selection, hpo_summary=hpo_summary, validation_mean=validation_mean_metrics, validation_advanced=validation_advanced_metrics, adoption=adoption, estimator_type=estimator_type, validation_expected=validation_expected, test_expected=test_expected, parity=parity, spec=spec, manifest=manifest)
        return 0
    except Exception as exc:
        blockers.append(str(exc))
        result = {"result": "BLOCKED", "recommendation": "DO_NOT_PROCEED_TO_PHASE_6", "base_branch": BASE_BRANCH, "base_git_sha": os.environ.get("PHASE5_BASE_SHA", "71cf347ee049d82302e874a021958a91d341ccb5"), "implementation_git_sha": os.environ.get("PHASE5_IMPLEMENTATION_SHA", _git_sha()), "evidence_git_sha": os.environ.get("PHASE5_EVIDENCE_SHA", _git_sha()), "major_blockers": blockers, "warnings": warnings, "tests": locals().get("tests", {}), "compute": compute, "result_error": repr(exc)}
        write_json(ARTIFACTS / "phase5_manifest.json", result)
        print(f"PHASE5 BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
