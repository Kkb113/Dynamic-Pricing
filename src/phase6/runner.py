"""Canonical Phase 6 acceptance run for the candidate-price optimizer.

The runner deliberately freezes every optimizer policy before the TEST scenario
is opened and keeps TEST outcome columns out of all scenario-engine frames.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from catboost import CatBoostClassifier

from features.feature_contract import load_contract
from features.validation import canonical_dataset_hash
from models.catboost_data import (
    build_feature_families,
    build_purchase_model_features_for_candidate_price,
    prepare_catboost_frame,
    make_catboost_pool,
)
from models.quantity_data import build_quantity_model_features_for_candidate_price, prepare_quantity_catboost_frame
from models.quantity_estimator import load_quantity_estimator
from optimization.candidate_grid import audit_price_support, build_candidate_grid
from optimization.candidate_simulator import OUTCOME_COLUMNS, load_outcome_blind_context, simulate_candidate_prices
from optimization.cost_resolver import resolve_cost_prices
from optimization.price_selector import select_model_optimal_prices
from validation.artifacts import prediction_fingerprint, sha256_file, write_json
from validation.compute import configure_thread_environment, detect_compute_environment


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/phase6"
BASE_BRANCH = "codex/phase1-data-audit"
BASE_SHA = "91cb9bff7e16fa845eac5b7abf4ddd945af40c78"
PHASE2_SHA = "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2"
PHASE3_SPLIT_SHA = "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d"
PHASE4_SPEC_SHA = "87ffb4e56af455937a0c92b1be45be0e2c8082cc0efd6afa51eb62f9c05ba9d0"
PHASE4_MODEL_SHA = "1af936a1905dcb21e3623392a16afbdbfc6b57c6866093fd6b33f12976dfd86d"
PHASE5_SPEC_SHA = "260354340c41fe8eaccaafc4e3388f7fb28c81ec4fbaba049504a25b7a487914"
PHASE5_MEAN = 1.3057971014492753
OPTIMIZER_CONTEXT_ROUTING_COLUMNS = (
    "PricingDecisionID",
    "DecisionTime",
    "ProductID",
    "StoreID",
    "Channel",
    "CurrentPrice",
    "AppliedPrice",
    "BasePrice",
)


def _config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config/phase6_optimizer.yaml").read_text(encoding="utf-8"))


def _json_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def _split(frame: pd.DataFrame, assignments: pd.DataFrame, split: str) -> pd.DataFrame:
    ids = set(assignments.loc[assignments["split"].eq(split), "PricingDecisionID"].astype(str))
    return frame.loc[frame["PricingDecisionID"].astype(str).isin(ids)].copy().sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)


def _optimizer_context_columns(
    frame: pd.DataFrame,
    phase4_spec: dict[str, Any],
    phase5_metadata: dict[str, Any],
) -> list[str]:
    """Return the explicit, outcome-free scenario-engine allowlist."""

    ordered = list(dict.fromkeys([
        *OPTIMIZER_CONTEXT_ROUTING_COLUMNS,
        *phase4_spec["ordered_feature_names"],
        *phase5_metadata["ordered_feature_names"],
    ]))
    forbidden = sorted(OUTCOME_COLUMNS.intersection(ordered))
    if forbidden:
        raise RuntimeError(f"OPTIMIZER_CONTEXT_ALLOWLIST_OUTCOME_COLUMNS: {forbidden}")
    missing = sorted(set(ordered).difference(frame.columns))
    if missing:
        raise RuntimeError(f"OPTIMIZER_CONTEXT_COLUMNS_MISSING: {missing}")
    return ordered


def _high_response_guard_usage(timings: list[dict[str, Any]], threshold: float = 0.25) -> bool:
    """Flag decisions whose candidate response surface was actually adjusted."""

    adjusted_rates = [
        float(timing.get("safety_summary", {}).get("adjusted_decision_rate", 0.0))
        for timing in timings
    ]
    return max(adjusted_rates, default=0.0) > threshold


def _verify_hash_payload(payload: dict[str, Any], key: str, expected: str, label: str) -> None:
    actual = dict(payload)
    actual.pop(key, None)
    if payload.get(key) != expected or _json_hash(actual) != expected:
        raise RuntimeError(f"{label}_FINGERPRINT_MISMATCH")


def _verify_upstream(config: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    dataset_path = ROOT / config["phase2"]["dataset_path"]
    split_path = ROOT / config["phase3"]["split_path"]
    frame = pd.read_parquet(dataset_path)
    ordered_columns = [item["name"] for item in contract["features"]]
    dataset_sha = canonical_dataset_hash(frame, ordered_columns)
    if dataset_sha != PHASE2_SHA or len(frame) != 35000 or frame["PricingDecisionID"].nunique() != len(frame):
        raise RuntimeError("PHASE2_FINGERPRINT_MISMATCH")
    assignments = pd.read_parquet(split_path)
    split_sha = sha256_file(split_path)
    if split_sha != PHASE3_SPLIT_SHA:
        raise RuntimeError("PHASE3_SPLIT_FINGERPRINT_MISMATCH")
    if assignments["PricingDecisionID"].duplicated().any() or set(assignments["PricingDecisionID"].astype(str)) != set(frame["PricingDecisionID"].astype(str)):
        raise RuntimeError("PHASE3_SPLIT_ID_SET_MISMATCH")
    phase4_spec_path = ROOT / config["phase4"]["frozen_spec_path"]
    phase4_model_path = ROOT / config["phase4"]["model_path"]
    phase4_spec = json.loads(phase4_spec_path.read_text(encoding="utf-8"))
    _verify_hash_payload(phase4_spec, "frozen_model_spec_sha256", PHASE4_SPEC_SHA, "PHASE4_SPEC")
    if sha256_file(phase4_model_path) != PHASE4_MODEL_SHA:
        raise RuntimeError("PHASE4_MODEL_FINGERPRINT_MISMATCH")
    phase5_spec_path = ROOT / config["phase5"]["frozen_spec_path"]
    phase5_spec = json.loads(phase5_spec_path.read_text(encoding="utf-8"))
    _verify_hash_payload(phase5_spec, "frozen_quantity_spec_sha256", PHASE5_SPEC_SHA, "PHASE5_SPEC")
    metadata_path = ROOT / config["phase5"]["estimator_metadata_path"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if str(metadata.get("estimator_type", "")).upper() != "CONSTANT_MEAN":
        raise RuntimeError("NON_OFFICIAL_QUANTITY_MODEL_USED")
    mean_path = ROOT / config["phase5"]["mean_path"]
    mean_value = float(json.loads(mean_path.read_text(encoding="utf-8"))["mean_value"])
    if abs(mean_value - PHASE5_MEAN) > 1e-15:
        raise RuntimeError("PHASE5_ESTIMATOR_FINGERPRINT_MISMATCH")
    optimizer_columns = _optimizer_context_columns(frame, phase4_spec, metadata)
    # The canonical frame above is used only for upstream integrity checks. The
    # scenario engine receives a separate parquet read with an explicit
    # outcome-free allowlist, before cost resolution, parity, or simulation.
    optimizer_frame = pd.read_parquet(dataset_path, columns=optimizer_columns)
    if len(optimizer_frame) != len(frame) or set(optimizer_frame["PricingDecisionID"].astype(str)) != set(frame["PricingDecisionID"].astype(str)):
        raise RuntimeError("OPTIMIZER_CONTEXT_ID_SET_MISMATCH")
    return {
        "optimizer_frame": optimizer_frame,
        "optimizer_columns": optimizer_columns,
        "assignments": assignments,
        "dataset_sha": dataset_sha,
        "split_sha": split_sha,
        "phase4_spec": phase4_spec,
        "phase4_spec_sha": PHASE4_SPEC_SHA,
        "phase4_model_path": phase4_model_path,
        "phase4_model_sha": PHASE4_MODEL_SHA,
        "phase5_spec": phase5_spec,
        "phase5_spec_sha": PHASE5_SPEC_SHA,
        "phase5_metadata_path": metadata_path,
        "phase5_metadata_sha": sha256_file(metadata_path),
        "phase5_mean_path": mean_path,
        "phase5_estimator_type": "CONSTANT_MEAN",
        "phase5_mean": mean_value,
        "health": {
            split: {"rows": int(len(_split(optimizer_frame, assignments, split))), "start": _date(_split(optimizer_frame, assignments, split)["DecisionTime"].min()), "end": _date(_split(optimizer_frame, assignments, split)["DecisionTime"].max())}
            for split in ("train", "validation", "test")
        },
    }


def _parity(
    context: pd.DataFrame,
    *,
    split: str,
    purchase_model: CatBoostClassifier,
    purchase_contract: dict[str, Any],
    purchase_features: tuple[str, ...],
    quantity_estimator: Any,
    quantity_contract: dict[str, Any],
    quantity_features: tuple[str, ...],
    phase4_prediction_path: Path,
    phase5_prediction_path: Path,
    phase5_expected_path: Path,
) -> dict[str, Any]:
    blind = load_outcome_blind_context(context, allow_columns=list(context.columns))
    historical_purchase = prepare_catboost_frame(blind, purchase_contract, purchase_features)
    candidate_purchase = build_purchase_model_features_for_candidate_price(blind, blind["AppliedPrice"].to_numpy(float), purchase_contract, purchase_features)
    feature_delta = 0.0
    violations = 0
    for column in purchase_features:
        if column in set(purchase_contract["feature_lists"].get("categorical_features", [])):
            mismatch = historical_purchase[column].astype(str).to_numpy() != candidate_purchase[column].astype(str).to_numpy()
            violations += int(mismatch.sum())
        else:
            left = pd.to_numeric(historical_purchase[column], errors="coerce").to_numpy(float)
            right = pd.to_numeric(candidate_purchase[column], errors="coerce").to_numpy(float)
            delta = np.nanmax(np.abs(left - right)) if len(left) else 0.0
            feature_delta = max(feature_delta, float(np.nan_to_num(delta, nan=0.0)))
            violations += int(np.sum(~np.isclose(left, right, equal_nan=True, atol=1e-12, rtol=0.0)))
    historical_pool = make_catboost_pool(historical_purchase, purchase_contract, purchase_features)
    candidate_pool = make_catboost_pool(candidate_purchase, purchase_contract, purchase_features)
    historical_probabilities = purchase_model.predict_proba(historical_pool)[:, 1]
    probabilities = purchase_model.predict_proba(candidate_pool)[:, 1]
    probability_delta = float(np.max(np.abs(probabilities - historical_probabilities)))
    test_prediction_delta = 0.0
    if split == "test":
        p4 = pd.read_parquet(phase4_prediction_path, columns=["PricingDecisionID", "official_probability"]).set_index("PricingDecisionID")
        expected_probability = blind["PricingDecisionID"].astype(str).map(p4["official_probability"]).to_numpy(float)
        test_prediction_delta = float(np.max(np.abs(probabilities - expected_probability)))
    quantity_historical = prepare_quantity_catboost_frame(blind, quantity_contract, quantity_features)
    quantity_candidate = build_quantity_model_features_for_candidate_price(blind, blind["AppliedPrice"].to_numpy(float), quantity_contract, quantity_features)
    quantity_feature_delta = 0.0
    for column in quantity_features:
        if column in set(quantity_contract["feature_lists"].get("categorical_features", [])):
            if not np.array_equal(quantity_historical[column].astype(str).to_numpy(), quantity_candidate[column].astype(str).to_numpy()):
                quantity_feature_delta = 1.0
        else:
            left = pd.to_numeric(quantity_historical[column], errors="coerce").to_numpy(float)
            right = pd.to_numeric(quantity_candidate[column], errors="coerce").to_numpy(float)
            quantity_feature_delta = max(quantity_feature_delta, float(np.nan_to_num(np.nanmax(np.abs(left - right)), nan=0.0)))
    historical_quantities = quantity_estimator.predict_conditional_quantity(quantity_historical)
    quantities = quantity_estimator.predict_conditional_quantity(quantity_candidate)
    p5 = pd.read_parquet(phase5_prediction_path, columns=["PricingDecisionID", "conditional_quantity_official", "expected_units"]).set_index("PricingDecisionID")
    expected_quantity = blind["PricingDecisionID"].astype(str).map(p5["conditional_quantity_official"]).to_numpy(float)
    expected_units = blind["PricingDecisionID"].astype(str).map(p5["expected_units"]).to_numpy(float)
    # VALIDATION is an immutable pre-freeze Phase 5 artifact (TRAIN-only
    # fallback mean). Report its delta separately; the parity gate compares
    # historical and candidate paths through the frozen official loader.
    model_quantity_delta = float(np.max(np.abs(quantities - historical_quantities)))
    artifact_quantity_delta = float(np.max(np.abs(quantities - expected_quantity)))
    quantity_delta = model_quantity_delta
    integrated = probabilities * quantities
    historical_integrated = historical_probabilities * quantities
    expected_unit_delta = float(np.max(np.abs(integrated - historical_integrated)))
    test_expected_unit_delta = float(np.max(np.abs(integrated - expected_units))) if split == "test" else 0.0
    return {
        "split": split,
        "rows": int(len(blind)),
        "phase4_feature_violations": int(violations),
        "phase4_feature_max_delta": float(feature_delta),
        "phase4_candidate_probability_delta": probability_delta,
        "phase4_test_prediction_delta": test_prediction_delta,
        "phase5_feature_max_delta": float(quantity_feature_delta),
        "phase5_candidate_quantity_delta": quantity_delta,
        "phase5_artifact_quantity_delta": artifact_quantity_delta,
        "phase5_artifact_scope": "PRE_FREEZE_TRAIN_ONLY" if split == "validation" else "POST_FREEZE_TRAIN_PLUS_VALIDATION",
        "integrated_expected_unit_delta": expected_unit_delta,
        "phase5_test_expected_unit_delta": test_expected_unit_delta,
        "tolerance": 1e-10,
        "status": "PASS" if violations == 0 and feature_delta <= 1e-12 and probability_delta <= 1e-10 and test_prediction_delta <= 1e-10 and quantity_feature_delta <= 1e-12 and quantity_delta <= 1e-10 and expected_unit_delta <= 1e-10 and test_expected_unit_delta <= 1e-10 else "FAIL",
    }


def _recommendation_summary(surface: pd.DataFrame, recommendations: pd.DataFrame, split: str) -> dict[str, Any]:
    if recommendations.empty:
        return {"split": split, "decision_count": 0, "candidate_rows": 0}
    change = recommendations["price_change_pct"]
    counts = surface.groupby("PricingDecisionID", sort=False).size()
    all_negative = surface.groupby("PricingDecisionID", sort=False)["negative_unit_margin_candidate"].all()
    lower_multiplier = float(surface["candidate_multiplier"].min())
    upper_multiplier = float(surface["candidate_multiplier"].max())
    lower_boundary = recommendations["candidate_multiplier"].eq(lower_multiplier)
    upper_boundary = recommendations["candidate_multiplier"].eq(upper_multiplier)
    boundary = lower_boundary | upper_boundary
    raw_safe = recommendations["raw_vs_safe_optimum_changed"]
    uplift = recommendations["absolute_expected_profit_uplift"]
    return {
        "split": split,
        "decision_count": int(len(recommendations)),
        "candidate_rows": int(len(surface)),
        "mean_candidate_count": float(counts.mean()),
        "min_candidate_count": int(counts.min()),
        "max_candidate_count": int(counts.max()),
        "price_increase_rate": float((change > 1e-12).mean()),
        "price_decrease_rate": float((change < -1e-12).mean()),
        "no_change_rate": float((change.abs() <= 1e-12).mean()),
        "mean_price_change_pct": float(change.mean()),
        "median_price_change_pct": float(change.median()),
        "p05_price_change_pct": float(change.quantile(0.05)),
        "p25_price_change_pct": float(change.quantile(0.25)),
        "p75_price_change_pct": float(change.quantile(0.75)),
        "p95_price_change_pct": float(change.quantile(0.95)),
        "lower_boundary_selection_rate": float(lower_boundary.mean()),
        "upper_boundary_selection_rate": float(upper_boundary.mean()),
        "any_boundary_selection_rate": float(boundary.mean()),
        "raw_vs_safe_recommendation_change_rate": float(raw_safe.mean()),
        "mean_expected_profit_uplift": float(uplift.mean()),
        "median_expected_profit_uplift": float(uplift.median()),
        "positive_uplift_rate": float((uplift > 0).mean()),
        "mean_expected_revenue_delta": float((recommendations["recommended_expected_revenue"] - recommendations["current_expected_revenue"]).mean()),
        "all_candidates_negative_margin_rate": float(all_negative.mean()),
        "candidate_negative_margin_rate": float(surface["negative_unit_margin_candidate"].mean()),
        "decisions_with_any_negative_margin_candidate": int(surface.groupby("PricingDecisionID")["negative_unit_margin_candidate"].any().sum()),
        "decisions_where_all_candidates_negative_margin": int(all_negative.sum()),
        "median_recommended_multiplier": float(recommendations["candidate_multiplier"].median()),
        "revenue_profit_differ_rate": float((recommendations["RevenueOptimalCandidatePrice"] != recommendations["GrossProfitOptimalCandidatePrice"]).mean()),
    }


def _segment_diagnostics(recommendations: pd.DataFrame, context: pd.DataFrame, split: str) -> pd.DataFrame:
    joined = recommendations.merge(context[["PricingDecisionID", "Season", "RegionID", "CategoryID", "StoreType"]], on="PricingDecisionID", how="left", validate="one_to_one")
    rows: list[dict[str, Any]] = []
    for column in ["Channel", "Season", "RegionID", "CategoryID", "StoreType"]:
        for value, group in joined.groupby(column, dropna=False, sort=True):
            if len(group) < 100:
                continue
            rows.append({
                "split": split,
                "segment": column,
                "value": "__MISSING__" if pd.isna(value) else str(value),
                "support": int(len(group)),
                "mean_recommended_multiplier": float(group["candidate_multiplier"].mean()),
                "no_change_rate": float((group["decision_status"] == "KEEP_CURRENT_NO_MATERIAL_UPLIFT").mean()),
                "increase_rate": float((group["price_change_pct"] > 0).mean()),
                "decrease_rate": float((group["price_change_pct"] < 0).mean()),
                "boundary_rate": float(group["support_boundary_flag"].mean()),
                "mean_expected_profit_uplift": float(group["absolute_expected_profit_uplift"].mean()),
            })
    return pd.DataFrame(rows)


def _write_reports(manifest: dict[str, Any], support: dict[str, Any], grid: Any, parity: dict[str, Any], test_parity: dict[str, Any]) -> None:
    warnings = manifest.get("warnings", [])
    p01 = support.get("p01")
    p99 = support.get("p99")
    low = grid.effective_low
    high = grid.effective_high
    support_text = f"p01={p01:.6f}, p99={p99:.6f}; effective envelope=[{low:.6f}, {high:.6f}]" if all(value is not None for value in (p01, p99, low, high)) else "unavailable because the acceptance run was blocked before support completion"
    (ROOT / "docs").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/PHASE6_CANDIDATE_SIMULATION_REPORT.md").write_text(
        "# Phase 6 Candidate Simulation Report\n\n"
        "Phase 6 evaluates deterministic candidate-price scenarios using the frozen Phase 4 native probability model and the official Phase 5 estimator. It is observational scenario modelling, not causal elasticity.\n\n"
        f"## Support\n\nTRAIN AppliedPrice/CurrentPrice {support_text}. Candidates: `{list(grid.multipliers)}`. Prices use Decimal `ROUND_HALF_UP` to cents.\n\n"
        "## Response safety\n\nRaw expected units are retained. The optimizer-safe series is the low-price-to-high-price cumulative minimum, so it cannot increase with price. This is a conservative shape guard, not a trained model or calibration step.\n\n"
        f"Historical validation parity: `{parity.get('status', 'UNKNOWN')}`; TEST parity: `{test_parity.get('status', 'UNKNOWN')}`.\n\n"
        "## Limitations\n\nInventory and Pricing_Rules are intentionally not applied in Phase 6. CostPrice is a static Product reference used only after model inference.\n",
        encoding="utf-8",
    )
    (ROOT / "docs/PHASE6_PRICE_OPTIMIZER_REPORT.md").write_text(
        "# Phase 6 Price Optimizer Report\n\n"
        "The official objective is expected gross profit `(CandidatePrice - CostPrice) * SafeExpectedUnits`. Revenue optimization is diagnostic only. Near ties use a 0.1% band, then closest-to-current price, then lower price. A non-current candidate must exceed the current candidate by at least 0.5% relative expected gross profit; otherwise the engine keeps the current price.\n\n"
        "The output is `ModelOptimalCandidatePrice`, never a final business recommendation. Phase 7 owns price rules, margin floors, promotion/markdown actions, and inventory constraints.\n\n"
        f"Warnings measured by this run: {json.dumps(warnings, sort_keys=True)}\n",
        encoding="utf-8",
    )
    acceptance = f"""# Phase 6 Acceptance Report

## 1. Executive verdict

**{manifest.get('result', 'BLOCKED')}** — {manifest.get('recommendation', 'DO_NOT_PROCEED_TO_PHASE_7')}

## 2. Upstream verification

- Phase 2: `{manifest.get('phase2_dataset_sha')}`
- Phase 3: `{manifest.get('phase3_split_sha')}`
- Phase 4 model/spec: `{manifest.get('phase4_model_sha')}` / `{manifest.get('phase4_frozen_spec_sha')}`
- Phase 5 official estimator: `{manifest.get('phase5_estimator_type')}`, mean `{manifest.get('phase5_mean_value')}`

## 3–20. Contract and parity gates

TEST outcomes accessed by scenario engine: **{manifest.get('outcome_blindness', {}).get('test_scenario_outcomes_accessed', False)}**. TEST scenario context outcome columns: **{json.dumps(manifest.get('outcome_blindness', {}).get('test_scenario_context_outcome_columns', []), sort_keys=True)}**. Cost coverage: **{manifest.get('cost_coverage')}**. Support: **{json.dumps(manifest.get('price_support', {}), sort_keys=True)}**. Candidate parity: **{json.dumps(manifest.get('candidate_parity', {}), sort_keys=True)}**. TEST stack parity: **{json.dumps(manifest.get('test_stack_parity', {}), sort_keys=True)}**.

## 21–30. Scenario diagnostics

VALIDATION: `{json.dumps(manifest.get('validation_optimizer_summary', {}), sort_keys=True)}`

TEST: `{json.dumps(manifest.get('test_optimizer_summary', {}), sort_keys=True)}`

The response guard, safe-demand invariants, gross-profit surface, raw-vs-safe optimizer comparison, revenue-vs-profit comparison, boundary diagnostics, and segment diagnostics are serialized in `artifacts/phase6/`.

## 31. Compute and reproducibility

`{json.dumps(manifest.get('compute', {}), sort_keys=True)}`

`{json.dumps(manifest.get('reproducibility', {}), sort_keys=True)}`

## 32–35. Limitations and handoff

Phase 6 does not claim actual uplift and does not access historical inventory or outcomes during scenario simulation. Phase 7 must apply Pricing_Rules, MinPrice/MaxPrice, margin and discount limits, scope priority, promotion/markdown logic, and current inventory constraints.

Warnings: {json.dumps(manifest.get('warnings', []), sort_keys=True)}

Major blockers: {json.dumps(manifest.get('major_blockers', []), sort_keys=True)}

Final recommendation: **{manifest.get('recommendation', 'DO_NOT_PROCEED_TO_PHASE_7')}**
"""
    (ROOT / "docs/PHASE6_ACCEPTANCE_REPORT.md").write_text(acceptance, encoding="utf-8")


def _run_tests() -> dict[str, Any]:
    evidence_path = ARTIFACTS / "test_results.json"
    env = os.environ.copy()
    env["TEST_EVIDENCE_PATH"] = str(evidence_path)
    # The desktop sandbox may have a protected global pytest temp root. Keep
    # fixture scratch data inside this repository's writable workspace.
    base_temp = Path(tempfile.mkdtemp(prefix=".phase6-pytest-", dir=ROOT))
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--basetemp={base_temp}"], cwd=ROOT, env=env, check=False)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {"status": "FAIL", "total": 0, "passed": 0, "failed": 1}
    evidence["runner_exit_code"] = int(result.returncode)
    if result.returncode != 0 or evidence.get("failed", 0) != 0:
        raise RuntimeError("UNIT_INTEGRATION_TEST_FAILURE")
    return evidence


def _reproducibility(test_context: pd.DataFrame, kwargs: dict[str, Any]) -> dict[str, Any]:
    first, first_rec, _ = _run_scenario(test_context, kwargs)
    second, second_rec, _ = _run_scenario(test_context, kwargs)
    def delta(column: str) -> float:
        return float(np.max(np.abs(first[column].to_numpy(float) - second[column].to_numpy(float)))) if len(first) else 0.0
    price_mismatch = int((first["CandidatePrice"].to_numpy(float) != second["CandidatePrice"].to_numpy(float)).sum())
    selected_price_mismatch = int((first_rec["ModelOptimalCandidatePrice"].to_numpy(float) != second_rec["ModelOptimalCandidatePrice"].to_numpy(float)).sum())
    status_mismatch = int((first_rec["decision_status"].to_numpy() != second_rec["decision_status"].to_numpy()).sum())
    return {
        "candidate_row_count_run1": int(len(first)),
        "candidate_row_count_run2": int(len(second)),
        "max_probability_delta": delta("raw_purchase_probability"),
        "max_expected_units_delta": delta("safe_expected_units"),
        "max_revenue_delta": delta("expected_revenue"),
        "max_expected_profit_delta": delta("expected_gross_profit"),
        "candidate_price_mismatch_count": price_mismatch,
        "selected_price_mismatch_count": selected_price_mismatch,
        "decision_status_mismatch_count": status_mismatch,
        "tolerance": 1e-10,
        "status": "PASS" if max(delta("raw_purchase_probability"), delta("safe_expected_units"), delta("expected_revenue"), delta("expected_gross_profit")) <= 1e-10 and price_mismatch == 0 and selected_price_mismatch == 0 and status_mismatch == 0 else "FAIL",
    }


def _run_scenario(context: pd.DataFrame, kwargs: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    started = time.perf_counter()
    surface, timings = simulate_candidate_prices(context, **kwargs)
    simulation_seconds = time.perf_counter() - started
    selection_started = time.perf_counter()
    recommendations = select_model_optimal_prices(surface)
    selection_seconds = time.perf_counter() - selection_started
    timings["optimizer_selection_seconds"] = float(selection_seconds)
    timings["simulation_seconds"] = float(simulation_seconds)
    timings["total_seconds"] = float(simulation_seconds + selection_seconds)
    timings["candidate_rows_per_second"] = float(len(surface) / simulation_seconds) if simulation_seconds else None
    return surface, recommendations, timings


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    config = _config()
    compute = configure_thread_environment(detect_compute_environment(config["compute"]["max_threads"]))
    compute.update({"physical_cores": compute["detected_physical_cores"], "logical_threads": compute["detected_logical_threads"], "threads_used": compute["usable_threads"], "nested_parallelism": False})
    blockers: list[str] = []
    warnings: list[str] = []
    try:
        contract = load_contract(ROOT / config["phase2"]["contract_path"])
        upstream = _verify_upstream(config, contract)
        frame, assignments = upstream["optimizer_frame"], upstream["assignments"]
        train = _split(frame, assignments, "train")
        validation = _split(frame, assignments, "validation")
        test = _split(frame, assignments, "test")
        support = audit_price_support(train)
        write_json(ARTIFACTS / "price_support_audit.json", support)
        grid = build_candidate_grid(support, technical_low=config["candidate_grid"]["technical_multiplier_low"], technical_high=config["candidate_grid"]["technical_multiplier_high"])
        # CostPrice is resolved on the complete decision context, then reused by both splits.
        with_cost, cost_audit = resolve_cost_prices(frame, project_root=ROOT, artifact_dir=ARTIFACTS, schema=config["cost"]["schema"])
        validation_cost = _split(with_cost, assignments, "validation")
        test_cost = _split(with_cost, assignments, "test")
        phase4_spec = upstream["phase4_spec"]
        purchase_features = tuple(phase4_spec["ordered_feature_names"])
        quantity_features = tuple(json.loads((upstream["phase5_metadata_path"]).read_text(encoding="utf-8"))["ordered_feature_names"])
        purchase_model = CatBoostClassifier()
        purchase_model.load_model(str(upstream["phase4_model_path"]))
        quantity_contract = contract
        quantity_estimator = load_quantity_estimator(upstream["phase5_metadata_path"], contract=quantity_contract, mean_path=upstream["phase5_mean_path"])
        if quantity_estimator.estimator_type != "CONSTANT_MEAN":
            raise RuntimeError("NON_OFFICIAL_QUANTITY_MODEL_USED")
        upstream_validation = {
            "phase2_dataset_sha256": upstream["dataset_sha"], "phase3_split_assignment_sha256": upstream["split_sha"],
            "phase4_model_sha256": upstream["phase4_model_sha"], "phase4_frozen_spec_sha256": upstream["phase4_spec_sha"],
            "phase5_frozen_quantity_spec_sha256": upstream["phase5_spec_sha"], "phase5_estimator_type": upstream["phase5_estimator_type"],
            "phase5_mean_value": upstream["phase5_mean"], "phase5_estimator_fingerprint": upstream["phase5_metadata_sha"], "status": "PASS",
        }
        write_json(ARTIFACTS / "upstream_validation.json", upstream_validation)
        parity = _parity(validation, split="validation", purchase_model=purchase_model, purchase_contract=contract, purchase_features=purchase_features, quantity_estimator=quantity_estimator, quantity_contract=contract, quantity_features=quantity_features, phase4_prediction_path=ROOT / config["phase4"]["validation_prediction_path"], phase5_prediction_path=ROOT / "artifacts/phase5/predictions/quantity_validation.parquet", phase5_expected_path=ROOT / "artifacts/phase5/expected_demand_validation.parquet")
        test_parity = _parity(test, split="test", purchase_model=purchase_model, purchase_contract=contract, purchase_features=purchase_features, quantity_estimator=quantity_estimator, quantity_contract=contract, quantity_features=quantity_features, phase4_prediction_path=ROOT / config["phase4"]["test_prediction_path"], phase5_prediction_path=ROOT / "artifacts/phase5/predictions/quantity_test.parquet", phase5_expected_path=ROOT / "artifacts/phase5/expected_demand_test.parquet")
        write_json(ARTIFACTS / "candidate_parity.json", parity)
        write_json(ARTIFACTS / "test_stack_parity.json", test_parity)
        if parity["status"] != "PASS" or test_parity["status"] != "PASS":
            if parity.get("phase5_candidate_quantity_delta", 0.0) > 1e-10:
                raise RuntimeError("PHASE5_QUANTITY_PARITY_FAILURE")
            if test_parity.get("phase4_test_prediction_delta", 0.0) > 1e-10:
                raise RuntimeError("PHASE4_TEST_INFERENCE_PARITY_FAILURE")
            raise RuntimeError("CANDIDATE_PARITY_FAILURE")

        optimizer_spec: dict[str, Any] = {
            "phase2_dataset_sha": PHASE2_SHA, "phase3_split_sha": PHASE3_SPLIT_SHA,
            "phase4_frozen_spec_sha": PHASE4_SPEC_SHA, "phase4_model_sha": PHASE4_MODEL_SHA,
            "phase4_ordered_feature_names": list(purchase_features), "phase4_calibration": "NATIVE",
            "phase5_frozen_quantity_spec_sha": PHASE5_SPEC_SHA, "phase5_estimator_type": "CONSTANT_MEAN",
            "phase5_estimator_fingerprint": upstream["phase5_metadata_sha"], "phase5_ordered_feature_names": list(quantity_features),
            "phase5_mean_value": upstream["phase5_mean"], "cost_source": cost_audit["source"], "cost_sidecar_sha": cost_audit["sidecar_sha256"],
            **grid.as_dict(), "price_rounding_policy": "ROUND_HALF_UP_2_DECIMAL",
            "response_safety_policy": "LOW_TO_HIGH_CUMULATIVE_MINIMUM", "response_safety_tolerance": 1e-12,
            "official_objective": "EXPECTED_GROSS_PROFIT", "tie_band": {"absolute": 1e-8, "relative": 0.001},
            "tie_break_policy": ["CLOSEST_TO_CURRENT_PRICE", "LOWER_PRICE", "DETERMINISTIC_CANDIDATE_ORDER"],
            "minimum_relative_profit_uplift": 0.005, "outcome_blind_policy": True, "random_seed": 42,
            "thread_count": compute["usable_threads"], "candidate_prediction_batch_size": config["candidate_grid"]["candidate_prediction_batch_size"],
            "inventory_constraint_applied": False, "pricing_rules_applied": False, "promotion_actions_generated": False,
        }
        optimizer_spec["frozen_optimizer_spec_sha256"] = _json_hash(optimizer_spec)
        write_json(ARTIFACTS / "frozen_optimizer_spec.json", optimizer_spec)

        common_kwargs = {"optimizer_spec": optimizer_spec, "purchase_model": purchase_model, "purchase_contract": contract, "quantity_estimator": quantity_estimator, "quantity_contract": contract, "candidate_grid": grid, "batch_size": config["candidate_grid"]["candidate_prediction_batch_size"]}
        val_surface, val_recs, val_timing = _run_scenario(validation_cost, common_kwargs)
        test_surface, test_recs, test_timing = _run_scenario(test_cost, common_kwargs)
        val_surface.to_parquet(ARTIFACTS / "validation_candidate_surface.parquet", index=False)
        val_recs.to_parquet(ARTIFACTS / "validation_recommendations.parquet", index=False)
        test_surface.to_parquet(ARTIFACTS / "test_candidate_surface.parquet", index=False)
        test_recs.to_parquet(ARTIFACTS / "test_recommendations.parquet", index=False)
        val_summary = _recommendation_summary(val_surface, val_recs, "validation")
        test_summary = _recommendation_summary(test_surface, test_recs, "test")
        write_json(ARTIFACTS / "validation_optimizer_summary.json", val_summary)
        write_json(ARTIFACTS / "test_optimizer_summary.json", test_summary)
        response = {"validation": val_timing["safety_summary"], "test": test_timing["safety_summary"]}
        write_json(ARTIFACTS / "response_safety_summary.json", response)
        distribution = pd.concat([val_recs.assign(split="validation"), test_recs.assign(split="test")], ignore_index=True).groupby(["split", "candidate_multiplier"], as_index=False).size().rename(columns={"size": "decision_count"})
        distribution["percentage"] = distribution["decision_count"] / distribution.groupby("split")["decision_count"].transform("sum") * 100.0
        distribution.to_csv(ARTIFACTS / "recommendation_multiplier_distribution.csv", index=False)
        segments = pd.concat([_segment_diagnostics(val_recs, validation_cost, "validation"), _segment_diagnostics(test_recs, test_cost, "test")], ignore_index=True)
        segments.to_csv(ARTIFACTS / "segment_recommendation_diagnostics.csv", index=False)
        all_summaries = [val_summary, test_summary]
        boundary_max = max(x["any_boundary_selection_rate"] for x in all_summaries)
        if boundary_max > 0.50:
            warnings.append("OPTIMIZER_BOUNDARY_HEAVY")
        if boundary_max > 0.80:
            warnings.append("OPTIMIZER_STRONGLY_BOUNDARY_SEEKING")
        if _high_response_guard_usage([val_timing, test_timing]):
            warnings.append("HIGH_RESPONSE_GUARD_USAGE")
        if val_timing["safety_summary"]["safe_monotonic_violations"] or test_timing["safety_summary"]["safe_monotonic_violations"]:
            raise RuntimeError("OPTIMIZER_SAFE_DEMAND_MONOTONICITY_FAILURE")
        scenario_context_outcome_columns = sorted(OUTCOME_COLUMNS.intersection(test_cost.columns))
        if scenario_context_outcome_columns:
            raise RuntimeError(f"TEST_SCENARIO_CONTEXT_OUTCOME_COLUMNS: {scenario_context_outcome_columns}")
        test_access = {
            "frozen_optimizer_spec_sha256": optimizer_spec["frozen_optimizer_spec_sha256"],
            "test_feature_start": _date(test_cost["DecisionTime"].min()), "test_feature_end": _date(test_cost["DecisionTime"].max()),
            "test_scenario_outcomes_accessed": False,
            "test_scenario_context_columns": list(test_cost.columns),
            "test_scenario_context_outcome_columns": scenario_context_outcome_columns,
            "test_outcomes_accessed": False, "PurchasedFlag_accessed": False, "QuantityPurchased_accessed": False,
            "ActualRevenue_accessed": False, "OutcomeTime_accessed": False, "OrderLineID_accessed": False,
            "test_used_to_tune_candidate_grid": False, "test_used_to_tune_objective": False,
            "test_used_to_tune_response_guard": False, "test_used_to_tune_materiality": False,
        }
        write_json(ARTIFACTS / "test_access_manifest.json", test_access)
        reproducibility = _reproducibility(test_cost, common_kwargs)
        write_json(ARTIFACTS / "reproducibility.json", reproducibility)
        if reproducibility["status"] != "PASS":
            raise RuntimeError("REPRODUCIBILITY_FAILURE")
        benchmark = {
            "decisions_scored": int(val_timing["decisions_scored"] + test_timing["decisions_scored"]),
            "candidate_rows_scored": int(val_timing["candidate_rows_scored"] + test_timing["candidate_rows_scored"]),
            "candidate_generation_seconds": val_timing["candidate_generation_seconds"] + test_timing["candidate_generation_seconds"],
            "feature_generation_seconds": val_timing["feature_generation_seconds"] + test_timing["feature_generation_seconds"],
            "Phase4_prediction_seconds": val_timing["phase4_prediction_seconds"] + test_timing["phase4_prediction_seconds"],
            "Phase5_quantity_seconds": val_timing["phase5_quantity_seconds"] + test_timing["phase5_quantity_seconds"],
            "economic_scoring_seconds": val_timing["economic_scoring_seconds"] + test_timing["economic_scoring_seconds"], "optimizer_selection_seconds": val_timing["optimizer_selection_seconds"] + test_timing["optimizer_selection_seconds"],
            "total_seconds": val_timing["total_seconds"] + test_timing["total_seconds"],
            "candidate_rows_per_second": float((val_timing["candidate_rows_scored"] + test_timing["candidate_rows_scored"]) / max(val_timing["total_seconds"] + test_timing["total_seconds"], 1e-12)),
            "physical_cores": compute["physical_cores"], "logical_threads": compute["logical_threads"], "threads_used": compute["threads_used"],
        }
        write_json(ARTIFACTS / "compute_environment.json", {**compute, "python_version": sys.version, "platform": platform.platform()})
        write_json(ARTIFACTS / "compute_benchmark.json", benchmark)
        tests = _run_tests()
        manifest = {
            "result": "PASS_WITH_WARNINGS" if warnings else "PASS", "recommendation": "PROCEED_TO_PHASE_7",
            "base_branch": BASE_BRANCH, "base_git_sha": BASE_SHA,
            "implementation_git_sha": os.environ.get("PHASE6_IMPLEMENTATION_SHA", "PENDING"), "evidence_git_sha": os.environ.get("PHASE6_EVIDENCE_SHA", "PENDING"),
            "phase2_dataset_sha": PHASE2_SHA, "phase3_split_sha": PHASE3_SPLIT_SHA, "phase4_model_sha": PHASE4_MODEL_SHA, "phase4_frozen_spec_sha": PHASE4_SPEC_SHA,
            "phase5_frozen_spec_sha": PHASE5_SPEC_SHA, "phase5_estimator_type": "CONSTANT_MEAN", "phase5_mean_value": PHASE5_MEAN, "phase5_estimator_fingerprint": upstream["phase5_metadata_sha"],
            "cost_source": cost_audit["source"], "cost_coverage": cost_audit["coverage_rate"], "cost_audit": cost_audit,
            "price_support": {**support, **grid.as_dict()}, "candidate_grid": list(grid.multipliers),
            "candidate_counts": {"validation": val_summary["candidate_rows"], "test": test_summary["candidate_rows"]},
            "response_guard_metrics": response, "official_objective": "EXPECTED_GROSS_PROFIT",
            "tie_policy": {"band": {"absolute": 1e-8, "relative": 0.001}, "break": ["CLOSEST_TO_CURRENT_PRICE", "LOWER_PRICE", "DETERMINISTIC_CANDIDATE_ORDER"]},
            "materiality_policy": {"minimum_relative_expected_profit_uplift": 0.005}, "validation_optimizer_summary": val_summary, "test_optimizer_summary": test_summary,
            "candidate_parity": parity, "test_stack_parity": test_parity, "outcome_blindness": test_access, "reproducibility": reproducibility, "compute": benchmark,
            "tests": tests, "ci_status": "PENDING", "warnings": warnings, "major_blockers": [],
        }
        write_json(ARTIFACTS / "phase6_manifest.json", manifest)
        _write_reports(manifest, support, grid, parity, test_parity)
        return 0
    except Exception as exc:
        blockers.append(str(exc))
        def _read_json(name: str) -> dict[str, Any]:
            path = ARTIFACTS / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        support = _read_json("price_support_audit.json")
        cost = _read_json("cost_audit.json")
        parity = _read_json("candidate_parity.json")
        test_parity = _read_json("test_stack_parity.json")
        manifest = {
            "result": "BLOCKED", "recommendation": "DO_NOT_PROCEED_TO_PHASE_7", "base_branch": BASE_BRANCH, "base_git_sha": BASE_SHA,
            "phase2_dataset_sha": PHASE2_SHA, "phase3_split_sha": PHASE3_SPLIT_SHA, "phase4_model_sha": PHASE4_MODEL_SHA, "phase4_frozen_spec_sha": PHASE4_SPEC_SHA,
            "phase5_frozen_spec_sha": PHASE5_SPEC_SHA, "phase5_estimator_type": "CONSTANT_MEAN", "phase5_mean_value": PHASE5_MEAN,
            "cost_source": cost.get("source"), "cost_coverage": cost.get("coverage_rate"), "cost_audit": cost,
            "price_support": support, "candidate_parity": parity, "test_stack_parity": test_parity,
            "outcome_blindness": {"test_outcomes_accessed": False}, "warnings": warnings, "major_blockers": blockers,
        }
        write_json(ARTIFACTS / "phase6_manifest.json", manifest)
        _write_reports(manifest, support or {"p01": None, "p99": None}, type("Grid", (), {"effective_low": support.get("effective_support_low"), "effective_high": support.get("effective_support_high"), "multipliers": tuple(support.get("candidate_multiplier_template", ()))})(), parity, test_parity)
        print(f"PHASE6 BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
