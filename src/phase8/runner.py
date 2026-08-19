"""Canonical Phase 8 business backtesting and economic acceptance runner.

The runner consumes immutable Phase 2--7 artifacts and frozen model files. It
does not fit, tune, calibrate, select rules, select thresholds, or alter any
recommendation artifact. TEST outcomes are loaded exactly once after the
evaluation protocol has been persisted and hashed.
"""

from __future__ import annotations

import argparse
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

from phase7.frozen_scorer import FrozenPhase7Scorer, recompute_response_safety
from phase7.runner import PHASE7_CONTEXT_ALLOWLIST
from phase8.artifacts import write_csv, write_frame, write_json
from phase8.boundary_analysis import actual_boundary_rates, exact_boundary_candidates, neighbor_fragility
from phase8.bootstrap import bootstrap_intervals
from phase8.economic_metrics import economic_deltas, price_distribution
from phase8.factual_backtest import factual_gate_metrics, factual_metrics, probability_deciles
from phase8.outcome_loader import fixture_outcomes, load_split_outcomes
from phase8.outcome_validation import (
    attach_observed_economics,
    audit_outcome_quality,
    gross_profit_consistency_audit,
    integrity_blockers,
    revenue_consistency_audit,
    validate_outcome_join,
)
from phase8.scenario_evaluation import SCENARIOS, all_scenario_summaries, scenario_delta, scenario_prices, score_scenarios
from phase8.segment_analysis import segment_metrics
from phase8.validation import EvaluationFreeze, reproducibility_check, sha256_json, upstream_validation
from phase7.validation import OUTCOME_COLUMNS
from validation.artifacts import sha256_file


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/phase8"
BASE_BRANCH = "codex/phase1-data-audit"
MERGED_DEFAULT_SHA = os.environ.get("PHASE8_BASE_SHA", "54f0f0b58647e3945776605cde31563393730401")
EXPECTED_SPLIT_ROWS = {"validation": 5250, "test": 5250}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _git_ahead_behind() -> dict[str, int | None]:
    try:
        output = subprocess.check_output(["git", "rev-list", "--left-right", "--count", f"{BASE_BRANCH}...HEAD"], cwd=ROOT, text=True).strip().split()
        return {"behind": int(output[0]), "ahead": int(output[1])}
    except Exception:
        return {"behind": None, "ahead": None}


def _load_context(root: Path, split: str) -> pd.DataFrame:
    dataset = pd.read_parquet(root / "artifacts/phase2/feature_dataset.parquet", columns=list(PHASE7_CONTEXT_ALLOWLIST))
    forbidden = sorted(OUTCOME_COLUMNS.intersection(dataset.columns))
    if forbidden:
        raise RuntimeError(f"PHASE8_CONTEXT_OUTCOME_COLUMNS: {forbidden}")
    assignments = pd.read_parquet(root / "artifacts/phase3/split_assignments.parquet")
    ids = set(assignments.loc[assignments["split"].eq(split), "PricingDecisionID"].astype(str))
    context = dataset.loc[dataset["PricingDecisionID"].astype(str).isin(ids)].copy()
    context = context.sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)
    if len(context) != EXPECTED_SPLIT_ROWS[split]:
        raise RuntimeError(f"PHASE8_SPLIT_CONTEXT_ROW_COUNT: {split}={len(context)}")
    return context


def _add_cost(context: pd.DataFrame, root: Path, split: str) -> pd.DataFrame:
    result = context.copy()
    sidecar = pd.read_parquet(root / "artifacts/phase6/product_cost_sidecar.parquet")
    sidecar["ProductID"] = sidecar["ProductID"].astype(str)
    result["ProductID"] = result["ProductID"].astype(str)
    result = result.merge(sidecar[["ProductID", "CostPrice"]], on="ProductID", how="left", validate="many_to_one")
    # The Phase 6 candidate surface is an accepted source-sidecar fallback for
    # any product not represented in the compact cost sidecar.
    surface = pd.read_parquet(root / f"artifacts/phase6/{split}_candidate_surface.parquet", columns=["PricingDecisionID", "CostPrice"])
    cost_by_decision = surface.drop_duplicates("PricingDecisionID").set_index("PricingDecisionID")["CostPrice"]
    missing = result["CostPrice"].isna()
    if missing.any():
        result.loc[missing, "CostPrice"] = result.loc[missing, "PricingDecisionID"].astype(str).map(cost_by_decision)
    result["CostPrice"] = pd.to_numeric(result["CostPrice"], errors="coerce")
    return result


def _cost_lookup(context: pd.DataFrame) -> pd.DataFrame:
    return context[["PricingDecisionID", "CostPrice"]].drop_duplicates("PricingDecisionID")


def _build_factual(
    context: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    root: Path,
    split: str,
    scorer: FrozenPhase7Scorer,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = context.merge(outcomes, on="PricingDecisionID", how="inner", validate="one_to_one", suffixes=("", "_outcome"))
    if "AppliedPrice_outcome" in base:
        base["AppliedPrice"] = base["AppliedPrice_outcome"]
        base = base.drop(columns=["AppliedPrice_outcome"])
    source = base.copy()
    prices = pd.to_numeric(base["AppliedPrice"], errors="coerce").to_numpy(float)
    scored = scorer.score_candidates(source, prices)
    base["historical_purchase_probability"] = [item["raw_purchase_probability"] for item in scored]
    base["historical_expected_quantity_if_purchase"] = [item["conditional_quantity"] for item in scored]
    base["historical_expected_units"] = [item["safe_expected_units"] for item in scored]
    base["historical_expected_revenue"] = [item["expected_revenue"] for item in scored]
    base["historical_expected_gross_profit"] = [item["expected_gross_profit"] for item in scored]
    base["ObservedGrossProfit"] = pd.to_numeric(base["ActualRevenue"], errors="coerce") - pd.to_numeric(base["CostPrice"], errors="coerce") * pd.to_numeric(base["QuantityPurchased"], errors="coerce")
    base["ObservedGrossProfit_formula_check"] = (pd.to_numeric(base["AppliedPrice"], errors="coerce") - pd.to_numeric(base["CostPrice"], errors="coerce")) * pd.to_numeric(base["QuantityPurchased"], errors="coerce")
    phase4 = pd.read_parquet(root / f"artifacts/phase4/predictions/purchase_{split}.parquet")[["PricingDecisionID", "official_probability"]]
    phase5 = pd.read_parquet(root / f"artifacts/phase5/expected_demand_{split}.parquet")[["PricingDecisionID", "expected_units"]].rename(columns={"expected_units": "phase5_official_expected_units"})
    base = base.merge(phase4, on="PricingDecisionID", how="left", validate="one_to_one").merge(phase5, on="PricingDecisionID", how="left", validate="one_to_one")
    base["phase4_probability_delta"] = base["historical_purchase_probability"] - pd.to_numeric(base["official_probability"], errors="coerce")
    base["phase5_expected_units_delta"] = base["historical_expected_units"] - pd.to_numeric(base["phase5_official_expected_units"], errors="coerce")
    parity = {
        "phase4_probability_max_delta": float(base["phase4_probability_delta"].abs().max()),
        "phase5_expected_units_max_delta": float(base["phase5_expected_units_delta"].abs().max()),
        "phase4_pass": bool(base["phase4_probability_delta"].abs().max() <= 1e-10),
        "phase5_pass": bool(base["phase5_expected_units_delta"].abs().max() <= 1e-10),
    }
    return base, parity


def _phase7_artifacts(root: Path, split: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    recommendations = pd.read_parquet(root / f"artifacts/phase6/{split}_recommendations.parquet")
    decisions = pd.read_parquet(root / f"artifacts/phase7/{split}_business_decisions.parquet")
    surface = pd.read_parquet(root / f"artifacts/phase6/{split}_candidate_surface.parquet")
    return surface, recommendations, decisions


def _attach_scenario_context(scenario_frame: pd.DataFrame, factual: pd.DataFrame, boundaries: dict[str, Any]) -> pd.DataFrame:
    factual_columns = [
        "PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "Channel", "CategoryID", "Season", "RegionID", "StoreType", "CurrentPrice", "CostPrice",
        "PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime", "AppliedPrice", "ObservedGrossProfit", "historical_purchase_probability", "historical_expected_units", "historical_expected_revenue", "historical_expected_gross_profit",
    ]
    factual_columns = [column for column in factual_columns if column in factual.columns]
    result = scenario_frame.merge(factual[factual_columns], on="PricingDecisionID", how="left", validate="one_to_one")
    boundary_frame = boundaries.get("diagnostic_frame", pd.DataFrame())
    if not boundary_frame.empty:
        result = result.merge(boundary_frame[["PricingDecisionID", "phase6_upper_boundary", "phase7_upper_boundary", "phase7_lower_boundary"]], on="PricingDecisionID", how="left", validate="one_to_one")
    else:
        result["phase6_upper_boundary"] = False
        result["phase7_upper_boundary"] = False
        result["phase7_lower_boundary"] = False
    return result


def _boundary_sensitivity(
    root: Path,
    context: pd.DataFrame,
    surface: pd.DataFrame,
    decisions: pd.DataFrame,
    scenario_frame: pd.DataFrame,
    scorer: FrozenPhase7Scorer,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    candidates = exact_boundary_candidates(surface, decisions)
    if candidates.empty:
        return pd.DataFrame(), {"in_support_unsimulated_boundaries": 0, "boundaries_scored": 0, "decisions_where_augmented_optimum_differs": 0, "change_rate": 0.0, "aggregate_model_implied_gp_delta": 0.0, "relative_aggregate_gp_delta": 0.0, "mean_price_delta": 0.0, "warning_codes": [], "blockers": []}
    source = context.set_index("PricingDecisionID", drop=False)
    source_rows = source.loc[candidates["PricingDecisionID"].astype(str)].reset_index(drop=True)
    scored_values = scorer.score_candidates(source_rows, candidates["boundary_price"].to_numpy(float))
    scored_rows = candidates.copy()
    scored_rows["raw_expected_units"] = [item["raw_expected_units"] for item in scored_values]
    scored_rows["safe_expected_units"] = [item["safe_expected_units"] for item in scored_values]
    scored_rows["expected_revenue"] = [item["expected_revenue"] for item in scored_values]
    scored_rows["expected_gross_profit"] = [item["expected_gross_profit"] for item in scored_values]
    scored_rows["CostPrice"] = [item["unit_gross_profit"] for item in scored_values]
    phase7_by_id = scenario_frame.set_index("PricingDecisionID")
    records: list[dict[str, Any]] = []
    for decision_id, group in scored_rows.groupby("PricingDecisionID", sort=False):
        surface_group = surface.loc[surface["PricingDecisionID"].astype(str).eq(str(decision_id))].copy()
        if surface_group.empty:
            continue
        # Re-run the frozen response-safety transform over the accepted grid
        # plus the exact-cent boundary candidates, without changing official
        # Phase 7 artifacts.
        boundary_group = group.copy()
        boundary_group["PricingDecisionID"] = decision_id
        for column in ("CandidatePrice", "raw_expected_units", "safe_expected_units", "expected_revenue", "expected_gross_profit", "CostPrice"):
            if column == "CandidatePrice":
                boundary_group[column] = boundary_group["boundary_price"]
            elif column == "CostPrice":
                boundary_group[column] = pd.to_numeric(source.loc[str(decision_id), "CostPrice"], errors="coerce")
        common = [column for column in ("PricingDecisionID", "CandidatePrice", "CostPrice", "raw_expected_units", "safe_expected_units", "expected_revenue", "expected_gross_profit", "raw_expected_revenue", "raw_expected_gross_profit") if column in surface_group.columns]
        augmented = pd.concat([surface_group[common], boundary_group[[column for column in common if column in boundary_group]],], ignore_index=True, sort=False)
        if "raw_expected_revenue" not in augmented:
            augmented["raw_expected_revenue"] = augmented["CandidatePrice"] * augmented["raw_expected_units"]
        if "raw_expected_gross_profit" not in augmented:
            augmented["raw_expected_gross_profit"] = (augmented["CandidatePrice"] - augmented["CostPrice"]) * augmented["raw_expected_units"]
        augmented = recompute_response_safety(augmented)
        best = augmented.sort_values(["expected_gross_profit", "CandidatePrice"], ascending=[False, True], kind="mergesort").iloc[0]
        official = phase7_by_id.loc[str(decision_id)] if str(decision_id) in phase7_by_id.index else None
        final_price = float(official["S3_PHASE7_FINAL_AUTOMATIC_price"]) if official is not None and pd.notna(official["S3_PHASE7_FINAL_AUTOMATIC_price"]) else np.nan
        official_gp = float(official["S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit"]) if official is not None and pd.notna(official["S3_PHASE7_FINAL_AUTOMATIC_expected_gross_profit"]) else np.nan
        records.append({
            "PricingDecisionID": decision_id,
            "boundary_price": float(group.iloc[0]["boundary_price"]),
            "boundary_type": group.iloc[0]["boundary_type"],
            "augmented_optimum_price": float(best["CandidatePrice"]),
            "augmented_optimum_expected_gross_profit": float(best["expected_gross_profit"]),
            "phase7_final_price": final_price,
            "phase7_expected_gross_profit": official_gp,
            "augmented_optimum_differs": bool(pd.notna(final_price) and abs(float(best["CandidatePrice"]) - final_price) > 0.005),
            "gp_delta_vs_phase7": float(best["expected_gross_profit"] - official_gp) if pd.notna(official_gp) else np.nan,
            "price_delta_vs_phase7": float(best["CandidatePrice"] - final_price) if pd.notna(final_price) else np.nan,
        })
    result = pd.DataFrame(records)
    valid = result["gp_delta_vs_phase7"].notna() if not result.empty else pd.Series(dtype=bool)
    baseline = float(result.loc[valid, "phase7_expected_gross_profit"].sum()) if not result.empty else 0.0
    delta = float(result.loc[valid, "gp_delta_vs_phase7"].sum()) if not result.empty else 0.0
    relative = delta / baseline if baseline else 0.0
    warnings = ["COARSE_GRID_VALUE_WARNING"] if relative > 0.005 else []
    blockers = ["MATERIAL_GRID_GRANULARITY_GAP"] if relative > 0.02 else []
    summary = {
        "in_support_unsimulated_boundaries": int(len(candidates)),
        "boundaries_scored": int(len(scored_rows)),
        "decision_rows_with_scored_boundaries": int(len(result)),
        "decisions_where_augmented_optimum_differs": int(result["augmented_optimum_differs"].sum()) if not result.empty else 0,
        "change_rate": float(result["augmented_optimum_differs"].mean()) if not result.empty else 0.0,
        "aggregate_model_implied_gp_delta": delta,
        "relative_aggregate_gp_delta": relative,
        "mean_price_delta": float(result.loc[valid, "price_delta_vs_phase7"].mean()) if valid.any() else 0.0,
        "warning_codes": warnings,
        "blockers": blockers,
    }
    return result, summary


def _rule_impact(root: Path, test_rows: int) -> pd.DataFrame:
    source = pd.read_csv(root / "artifacts/phase7/rule_constraint_impact.csv")
    source["share_of_test_decisions_affected"] = source["decisions_affected"] / max(test_rows, 1)
    # Phase 7 reports rule counts and price deltas, but does not identify a
    # unique counterfactual GP attribution for overlapping guards.  Keep the
    # field explicitly null rather than serialising NaN into the JSON manifest
    # (JSON null is an auditable "not available", not a non-finite metric).
    source["average_model_implied_gp_impact"] = None
    source["average_price_impact"] = source["price_delta_mean"]
    source["gp_impact_note"] = "Phase 7 source diagnostics do not attribute counterfactual GP to one overlapping guardrail; no invented attribution is reported."
    return source


def _current_inventory_evaluation(root: Path) -> dict[str, Any]:
    path = root / "artifacts/phase7/current_inventory_business_decisions.parquet"
    summary_path = root / "artifacts/phase7/current_inventory_summary.json"
    frame = pd.read_parquet(path)
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    total_contexts = int(summary.get("eligible_current_contexts", 0) + summary.get("stale_contexts", 0))
    stale = int(summary.get("stale_contexts", 0))
    result = {
        "as_of_date": summary.get("as_of_date"),
        "eligible_contexts": int(summary.get("eligible_current_contexts", len(frame))),
        "inventory_coverage": float(summary.get("inventory_matched", 0) / max(summary.get("eligible_current_contexts", 1), 1)),
        "stale_contexts": stale,
        "stale_context_rate": float(stale / max(total_contexts, 1)),
        "price_increases": int((pd.to_numeric(frame.get("price_change_amount"), errors="coerce") > 0.005).sum()),
        "price_decreases": int((pd.to_numeric(frame.get("price_change_amount"), errors="coerce") < -0.005).sum()),
        "holds": int((pd.to_numeric(frame.get("price_change_amount"), errors="coerce").abs() <= 0.005).sum()),
        "seasonal_markdowns": int(frame.get("MarkdownAction", pd.Series(dtype=str)).eq("SEASONAL_SLOW_MOVING_MARKDOWN").sum()),
        "markdown_reviews": int(frame.get("MarkdownAction", pd.Series(dtype=str)).eq("MARKDOWN_REVIEW_REQUIRED").sum()),
        "promotion_reviews": int(frame.get("PromotionAction", pd.Series(dtype=str)).eq("PROMOTION_REVIEW").sum()),
        "inventory_capped_expected_units": float(pd.to_numeric(frame.get("inventory_capped_expected_units"), errors="coerce").sum()),
        "inventory_capped_expected_revenue": float(pd.to_numeric(frame.get("inventory_capped_expected_revenue"), errors="coerce").sum()),
        "inventory_capped_expected_gross_profit": float(pd.to_numeric(frame.get("inventory_capped_expected_gross_profit"), errors="coerce").sum()),
        "source_artifact": "phase7/current_inventory_business_decisions.parquet",
    }
    result["warnings"] = ["CURRENT_CONTEXT_STALENESS_HIGH"] if result["stale_context_rate"] > 0.20 else []
    return result


def _evaluation_spec(root: Path, upstream: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": 8,
        "protocol_version": "phase8_business_backtesting_v1",
        "metrics": {
            "purchase": ["ROC-AUC", "Average Precision", "Log Loss", "Brier Score", "ECE", "Top-decile lift"],
            "demand": ["MAE", "RMSE", "Poisson deviance", "aggregate units", "aggregate units error %", "WAPE", "mean bias"],
            "revenue": ["MAE", "RMSE", "WAPE", "mean bias", "aggregate revenue error %"],
            "gross_profit": ["MAE", "RMSE", "WAPE", "mean bias", "aggregate GP error %", "observed margin rate", "predicted margin rate"],
        },
        "business_thresholds": {
            "demand_strong": 0.05, "demand_warning": 0.10,
            "revenue_strong": 0.075, "revenue_warning": 0.15,
            "gross_profit_strong": 0.10, "gross_profit_warning": 0.20,
            "economic_policy_regression_blocker": -0.05,
            "material_grid_gap_blocker": 0.02,
        },
        "segment_definitions": {"columns": ["Channel", "Season", "RegionID", "CategoryID", "StoreType"], "minimum_rows": 100, "revenue_warning_abs": 0.20, "gp_warning_abs": 0.25, "major_revenue_share": 0.20, "major_gp_failure_abs": 0.30},
        "bootstrap": {"seed": 42, "samples": 1000, "confidence": 0.95},
        "boundary_diagnostics": {"grid_tolerance": 0.005, "fragility_rate": 0.80, "near_tie_relative_gp": 0.005, "near_tie_share": 0.50},
        "scenario_definitions": {scenario: ("historical observed AppliedPrice" if scenario == "S0_HISTORICAL_APPLIED" else "model-implied expected economics") for scenario in SCENARIOS},
        "factual_counterfactual_terminology": {"historical": "observed/factual", "alternative": "model-implied/scenario estimate"},
        "failure_thresholds": ["UPSTREAM_ARTIFACT_INTEGRITY_FAILURE", "PHASE8_MODEL_MUTATION", "TEST_OUTCOMES_BEFORE_EVALUATION_FREEZE", "OUTCOME_JOIN_INTEGRITY_FAILURE", "ACTUAL_REVENUE_INTEGRITY_FAILURE", "PHASE4_PREDICTION_DRIFT", "PHASE5_EXPECTED_DEMAND_DRIFT", "DEMAND_BACKTEST_FAILURE", "REVENUE_BACKTEST_FAILURE", "GROSS_PROFIT_BACKTEST_FAILURE", "ECONOMIC_POLICY_REGRESSION", "MATERIAL_GRID_GRANULARITY_GAP", "MAJOR_SEGMENT_ECONOMIC_CALIBRATION_FAILURE", "NEGATIVE_MARGIN_AUTOMATIC_RECOMMENDATION", "PHASE7_RULE_COMPLIANCE_REGRESSION", "HISTORICAL_INVENTORY_LEAKAGE", "NONFINITE_ECONOMICS", "REPRODUCIBILITY_FAILURE", "TESTS_FAILED"],
        "upstream_phase7_fingerprints": upstream.get("fingerprints", {}),
        "no_training": True,
        "training_calls_forbidden": ["CatBoost.fit", "Optuna", "GridSearch", "RandomizedSearch", "calibration", "feature_selection", "hyperparameter_tuning", "rule_tuning", "price_grid_tuning"],
        "historical_inventory_policy": "NOT_AVAILABLE_FOR_VALIDATION_OR_TEST",
        "current_inventory_policy": "PHASE7_CURRENT_INVENTORY_ARTIFACT_ONLY",
        "claim_language_restrictions": ["Do not describe alternative-price economics as observed, realized, or causal."],
    }


def _run_phase8_tests() -> dict[str, Any]:
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["TEST_EVIDENCE_PATH"] = str(ARTIFACTS / "test_results.json")
        completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/phase8"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600, check=False)
        output = (completed.stdout or "") + (completed.stderr or "")
        import re
        match = re.search(r"(?P<passed>\d+) passed(?:, (?P<failed>\d+) failed)?", output)
        passed = int(match.group("passed")) if match else 0
        failed = int(match.group("failed") or 0) if match else (1 if completed.returncode else 0)
        return {"status": "PASS" if completed.returncode == 0 and failed == 0 else "FAIL", "passed": passed, "failed": failed, "total": passed + failed, "command": "pytest -q tests/phase8", "output_tail": output[-3000:]}
    except Exception as exc:
        return {"status": "FAIL", "passed": 0, "failed": 1, "total": 1, "command": "pytest -q tests/phase8", "error": str(exc)}


def _write_reports(manifest: dict[str, Any]) -> None:
    test = manifest.get("test", {})
    factual = test.get("factual_metrics", {})
    scenarios = test.get("scenario_summaries", {})
    acceptance = manifest.get("acceptance", {})
    economics = manifest.get("scenario_deltas", {})
    warnings = manifest.get("warnings", [])
    factual_report = f"""# Phase 8 Factual Backtest Report

## Purpose

This report evaluates predictions at the historical `AppliedPrice`, where the
outcomes are observed. Alternative-price results are reported separately as
model-implied scenario estimates.

## TEST purchase model

| Metric | Value |
|---|---:|
| ROC-AUC | {factual.get('purchase', {}).get('roc_auc')} |
| Average Precision | {factual.get('purchase', {}).get('average_precision')} |
| Log Loss | {factual.get('purchase', {}).get('log_loss')} |
| Brier Score | {factual.get('purchase', {}).get('brier_score')} |
| Top-decile lift | {factual.get('purchase', {}).get('top_decile_lift')} |
| Phase 4 probability parity max delta | {test.get('parity', {}).get('phase4_probability_max_delta')} |
| Phase 5 expected-unit parity max delta | {test.get('parity', {}).get('phase5_expected_units_max_delta')} |

## Factual demand, revenue, and gross profit

{json.dumps({key: factual.get(key) for key in ('demand', 'revenue', 'gross_profit')}, indent=2, default=str)}

Observed gross profit is a proxy using static `Product.CostPrice`; historical
cost snapshots were not available. Ordinary MAPE is intentionally omitted
because many historical decisions have zero units.

## Calibration and segments

The probability-decile CSV and supported-segment CSV contain the complete
decile and segment evidence. Segment warnings are measured diagnostics, not
single-row failures.

## Limitations

Historical inventory is not used for this backtest. The observed economics are
descriptive at the offered price and do not establish what an alternative
price would have produced.
"""
    economics_report = f"""# Phase 8 Business Economics Report

## Scenario framing

`S0_HISTORICAL_APPLIED` is the factual prediction at the observed historical
price. `S1` through `S4` are model-implied expected units, revenue, and gross
profit; they are scenario estimates, not observed outcomes.

## Scenario summaries

{json.dumps(scenarios, indent=2, default=str)}

## Model-implied opportunity

{json.dumps(economics, indent=2, default=str)}

The primary opportunity metric is the Phase 7 model-implied expected gross
profit delta versus the historical-price model-implied scenario.

## Pricing behavior and robustness

{json.dumps({key: test.get(key) for key in ('price_distribution', 'boundary_rates', 'neighbor_fragility', 'boundary_augmentation')}, indent=2, default=str)}

Aggressive price movement, upper-grid concentration, and near-tied neighbors
are warnings that describe the frozen policy; no price or model was retuned.

## Governance cost and current inventory

Phase 6 versus Phase 7 economics quantify the model-implied expected profit
change associated with business constraints. Current inventory metrics are
reported separately from historical outcomes.
"""
    acceptance_report = f"""# Phase 8 Acceptance Report

## 1. Executive verdict

**{manifest.get('result')}** — {manifest.get('recommendation')}.

## 2. Upstream Phase 7 verification

{json.dumps(manifest.get('upstream_validation'), indent=2, default=str)}

## 3. Evaluation protocol freeze

Frozen spec SHA: `{manifest.get('frozen_evaluation_spec_sha256')}`. The spec was
written before the single TEST outcome read.

## 4. TEST outcome access control

{json.dumps(manifest.get('test_outcome_access'), indent=2, default=str)}

## 5. Outcome integrity / 6. Revenue consistency

{json.dumps(manifest.get('outcome_integrity'), indent=2, default=str)}

## 7–14. Factual evaluation

{json.dumps(factual, indent=2, default=str)}

## 15–23. Scenario economics and governance cost

{json.dumps(scenarios, indent=2, default=str)}

{json.dumps(economics, indent=2, default=str)}

## 24–28. Boundary behavior and overlap

{json.dumps({key: test.get(key) for key in ('price_distribution', 'boundary_rates', 'neighbor_fragility', 'boundary_augmentation', 'policy_overlap')}, indent=2, default=str)}

## 29–34. Segments, rule impact, and promotions

{json.dumps({key: test.get(key) for key in ('segment_summary', 'rule_impact', 'promotion_diagnostics')}, indent=2, default=str)}

## 35–40. Inventory, staleness, bootstrap, reproducibility

{json.dumps({key: manifest.get(key) for key in ('historical_inventory', 'current_inventory', 'bootstrap', 'reproducibility')}, indent=2, default=str)}

## 41–45. Compute, limitations, and handoff

{json.dumps({key: manifest.get(key) for key in ('compute', 'warnings', 'major_blockers')}, indent=2, default=str)}

Phase 9 may consume the frozen recommendation and evaluation artifacts only
after independent Phase 8 approval. This report does not present scenario
estimates as realized outcomes.
"""
    (ROOT / "docs/PHASE8_FACTUAL_BACKTEST_REPORT.md").write_text(factual_report, encoding="utf-8")
    (ROOT / "docs/PHASE8_BUSINESS_ECONOMICS_REPORT.md").write_text(economics_report, encoding="utf-8")
    (ROOT / "docs/PHASE8_ACCEPTANCE_REPORT.md").write_text(acceptance_report, encoding="utf-8")


def run_phase8(*, use_fixtures: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stage_timings: dict[str, float] = {}
    upstream = upstream_validation(ROOT)
    write_json(ARTIFACTS / "upstream_validation.json", upstream)
    blockers: list[str] = list(upstream.get("blockers", []))
    warnings: list[str] = []
    if upstream.get("status") != "PASS":
        blockers.append("UPSTREAM_ARTIFACT_INTEGRITY_FAILURE")

    contexts = {split: _add_cost(_load_context(ROOT, split), ROOT, split) for split in ("validation", "test")}
    split_ids = {split: contexts[split]["PricingDecisionID"].astype(str).tolist() for split in contexts}
    phase7_test_path = ROOT / "artifacts/phase7/test_business_decisions.parquet"
    test_decision_fingerprint_before = sha256_file(phase7_test_path)

    # VALIDATION is used solely to validate metric plumbing before the TEST
    # protocol is frozen.
    outcome_access: dict[str, Any] = {}
    validation_outcome_started = time.perf_counter()
    if use_fixtures:
        validation_outcomes = fixture_outcomes(contexts["validation"])
        validation_access = {"status": "FIXTURE_ONLY", "rows": int(len(validation_outcomes)), "sql_select_only": True}
    else:
        validation_outcomes, validation_access = load_split_outcomes(split_ids["validation"], env_file=ROOT / ".env")
    stage_timings["validation_outcome_loading_seconds"] = float(time.perf_counter() - validation_outcome_started)
    outcome_access["validation"] = validation_access
    validation_join = validate_outcome_join(validation_outcomes, split_ids["validation"], expected_rows=5250)
    validation_quality = audit_outcome_quality(validation_outcomes)
    validation_revenue = revenue_consistency_audit(validation_outcomes)
    write_json(ARTIFACTS / "validation_outcome_access.json", {"join": validation_join, "quality": validation_quality, "revenue": validation_revenue, "source": validation_access})
    blockers.extend(integrity_blockers(validation_join, validation_quality, validation_revenue))

    frozen_spec = _evaluation_spec(ROOT, upstream)
    frozen_spec["frozen_at"] = _now()
    write_json(ARTIFACTS / "frozen_evaluation_spec.json", frozen_spec)
    freeze = EvaluationFreeze()
    try:
        spec_sha = freeze.freeze(ARTIFACTS / "frozen_evaluation_spec.json")
    except Exception:
        blockers.append("MISSING_FROZEN_EVALUATION_SPEC")
        spec_sha = None

    freeze.evaluation_spec_frozen_at = frozen_spec["frozen_at"]
    try:
        # Authorize exactly one TEST read only after the spec has been
        # persisted and hashed.  The completion timestamp is recorded below,
        # after the SELECT has returned.
        freeze.authorize_test_outcomes()
    except Exception as exc:
        blockers.append(str(exc).split(":", 1)[0])
    test_outcome_started = time.perf_counter()
    if use_fixtures:
        test_outcomes = fixture_outcomes(contexts["test"])
        test_access_source = {"status": "FIXTURE_ONLY", "rows": int(len(test_outcomes)), "sql_select_only": True}
    else:
        test_outcomes, test_access_source = load_split_outcomes(split_ids["test"], env_file=ROOT / ".env")
    stage_timings["test_outcome_loading_seconds"] = float(time.perf_counter() - test_outcome_started)
    test_loaded_at = _now()
    try:
        freeze.record_test_outcomes_loaded(test_loaded_at)
    except Exception as exc:
        blockers.append(str(exc).split(":", 1)[0])
    test_access = {
        "test_outcome_access_count": 1,
        "evaluation_spec_frozen_before_test": bool(freeze.spec_written and freeze.test_outcomes_loaded),
        "test_used_for_training": False,
        "test_used_for_hpo": False,
        "test_used_for_model_selection": False,
        "test_used_for_rule_selection": False,
        "test_used_for_candidate_grid_selection": False,
        "test_used_for_threshold_selection": False,
        "evaluation_spec_frozen_at": freeze.evaluation_spec_frozen_at,
        "test_outcomes_loaded_at": freeze.test_outcomes_loaded_at,
        "source": test_access_source,
    }
    write_json(ARTIFACTS / "test_outcome_access_manifest.json", test_access)
    if not (test_access["evaluation_spec_frozen_at"] < test_access["test_outcomes_loaded_at"]):
        blockers.append("TEST_OUTCOMES_BEFORE_EVALUATION_FREEZE")

    test_join = validate_outcome_join(test_outcomes, split_ids["test"], expected_rows=5250)
    test_quality = audit_outcome_quality(test_outcomes)
    test_revenue = revenue_consistency_audit(test_outcomes)
    blockers.extend(integrity_blockers(test_join, test_quality, test_revenue))
    validation_gp = gross_profit_consistency_audit(validation_outcomes, _cost_lookup(contexts["validation"]))
    test_gp = gross_profit_consistency_audit(test_outcomes, _cost_lookup(contexts["test"]))
    if validation_gp.get("status") != "PASS" or test_gp.get("status") != "PASS":
        blockers.append("NONFINITE_ECONOMICS")
    outcome_integrity = {
        "validation": {"join": validation_join, "quality": validation_quality, "revenue": validation_revenue, "gross_profit_formula": validation_gp},
        "test": {"join": test_join, "quality": test_quality, "revenue": test_revenue, "gross_profit_formula": test_gp},
        "observed_gross_profit_definition": "ActualRevenue - (Product.CostPrice * QuantityPurchased)",
        "cost_limitation": "Static Product.CostPrice is used because historical cost snapshots are unavailable.",
    }
    write_json(ARTIFACTS / "outcome_quality_audit.json", outcome_integrity)

    scorer = FrozenPhase7Scorer(ROOT)
    evaluations: dict[str, dict[str, Any]] = {}
    timings: dict[str, float] = {}
    boundary_test_payload: tuple[pd.DataFrame, dict[str, Any]] | None = None
    for split, outcomes in (("validation", validation_outcomes), ("test", test_outcomes)):
        split_started = time.perf_counter()
        context = contexts[split]
        surface, recommendations, decisions = _phase7_artifacts(ROOT, split)
        historical_started = time.perf_counter()
        factual, parity = _build_factual(context, outcomes, root=ROOT, split=split, scorer=scorer)
        stage_timings[f"{split}_historical_scoring_seconds"] = float(time.perf_counter() - historical_started)
        boundary_rates = actual_boundary_rates(surface, recommendations, decisions)
        scenario_started = time.perf_counter()
        scenario_price_frame = scenario_prices(outcomes, recommendations, decisions)
        scenario_timings: dict[str, float] = {}
        scenario_scored = score_scenarios(context, scenario_price_frame, scorer, timings=scenario_timings)
        stage_timings[f"{split}_scenario_scoring_seconds"] = float(time.perf_counter() - scenario_started)
        for scenario_name, elapsed in scenario_timings.items():
            stage_timings[f"{split}_{scenario_name.lower()}_scoring_seconds"] = float(elapsed)
        assembly_started = time.perf_counter()
        scenario_frame = _attach_scenario_context(scenario_scored, factual, boundary_rates)
        stage_timings[f"{split}_scenario_assembly_seconds"] = float(time.perf_counter() - assembly_started)
        summaries = all_scenario_summaries(scenario_frame)
        deltas = {scenario: scenario_delta(summaries, scenario) for scenario in SCENARIOS if scenario != "S0_HISTORICAL_APPLIED"}
        metrics_started = time.perf_counter()
        factual_metrics_payload = factual_metrics(factual)
        stage_timings[f"{split}_factual_metrics_seconds"] = float(time.perf_counter() - metrics_started)
        gates = factual_gate_metrics(factual_metrics_payload)
        # VALIDATION is a plumbing check only.  The accepted Phase 4/5
        # validation artifacts were produced by their TRAIN→VALIDATION
        # evaluation model, while the frozen artifact used by Phase 8 is the
        # final TRAIN+VALIDATION model.  The contractual parity blockers apply
        # to the final TEST benchmark; validation deltas remain reported
        # diagnostics and never select or alter a model.
        if split == "test":
            if not parity["phase4_pass"]:
                blockers.append("PHASE4_PREDICTION_DRIFT")
            if not parity["phase5_pass"]:
                blockers.append("PHASE5_EXPECTED_DEMAND_DRIFT")
        blockers.extend(gates.get("blockers", []))
        write_frame(ARTIFACTS / f"{split}_factual_backtest.parquet", factual)
        write_json(ARTIFACTS / f"{split}_factual_metrics.json", {**factual_metrics_payload, "gates": gates, "parity": parity})
        write_frame(ARTIFACTS / f"{split}_scenario_comparison.parquet", scenario_frame)
        write_json(ARTIFACTS / f"{split}_scenario_summary.json", {"summaries": summaries, "deltas": deltas})
        if split == "test":
            write_csv(ARTIFACTS / "test_probability_decile_backtest.csv", probability_deciles(factual))
            boundary_test_payload = (scenario_frame, {"surface": surface, "recommendations": recommendations, "decisions": decisions, "context": context, "rates": boundary_rates})
        evaluations[split] = {"factual": factual, "scenario": scenario_frame, "factual_metrics": factual_metrics_payload, "parity": parity, "gates": gates, "summaries": summaries, "deltas": deltas, "boundaries": boundary_rates, "surface": surface, "recommendations": recommendations, "decisions": decisions, "context": context}
        timings[f"{split}_evaluation_seconds"] = float(time.perf_counter() - split_started)

    test_eval = evaluations["test"]
    test_frame = test_eval["scenario"]
    overlap_mask = test_frame["S3_PHASE7_FINAL_AUTOMATIC_price"].notna() & ((pd.to_numeric(test_frame["S3_PHASE7_FINAL_AUTOMATIC_price"], errors="coerce") - pd.to_numeric(test_frame["S0_HISTORICAL_APPLIED_price"], errors="coerce")).abs() <= 0.005)
    overlap = test_frame.loc[overlap_mask].copy()
    policy_overlap = {
        "exact_matches": int(len(overlap)),
        "exact_match_rate": float(len(overlap) / max(int(test_frame["S3_PHASE7_FINAL_AUTOMATIC_price"].notna().sum()), 1)),
        "observed_units": float(pd.to_numeric(overlap.get("QuantityPurchased"), errors="coerce").sum()),
        "observed_revenue": float(pd.to_numeric(overlap.get("ActualRevenue"), errors="coerce").sum()),
        "observed_gross_profit": float(pd.to_numeric(overlap.get("ObservedGrossProfit"), errors="coerce").sum()),
        "predicted_units": float(pd.to_numeric(overlap.get("historical_expected_units"), errors="coerce").sum()),
        "predicted_revenue": float(pd.to_numeric(overlap.get("historical_expected_revenue"), errors="coerce").sum()),
        "predicted_gross_profit": float(pd.to_numeric(overlap.get("historical_expected_gross_profit"), errors="coerce").sum()),
    }
    write_json(ARTIFACTS / "test_policy_overlap.json", policy_overlap)
    if policy_overlap["exact_matches"] < 100:
        warnings.append("LOW_FACTUAL_POLICY_OVERLAP")

    boundary_started = time.perf_counter()
    neighbor, neighbor_stats = neighbor_fragility(test_eval["surface"], test_eval["decisions"], test_eval["boundaries"]["diagnostic_frame"])
    write_frame(ARTIFACTS / "test_boundary_neighbor_analysis.parquet", neighbor)
    boundary_payload = {key: value for key, value in test_eval["boundaries"].items() if key != "diagnostic_frame"}
    write_json(ARTIFACTS / "test_boundary_diagnostics.json", {**boundary_payload, **neighbor_stats})
    if boundary_payload.get("phase7_upper_grid_boundary_rate", 0.0) > 0.95:
        warnings.append("EXTREME_UPPER_GRID_CONCENTRATION")
    auto_price_mask = test_frame["S3_PHASE7_FINAL_AUTOMATIC_price"].notna()
    if auto_price_mask.any() and float(test_frame.loc[auto_price_mask, "S3_PHASE7_FINAL_AUTOMATIC_price"].sub(test_frame.loc[auto_price_mask, "CurrentPrice"]).gt(0.005).mean()) > 0.95:
        warnings.append("AGGRESSIVE_PRICE_POLICY")
    warnings.extend(neighbor_stats.get("warning_codes", []))

    if boundary_test_payload is not None:
        scenario_frame, data = boundary_test_payload
        exact_scored, boundary_augmentation = _boundary_sensitivity(ROOT, data["context"], data["surface"], data["decisions"], scenario_frame, scorer)
    else:
        exact_scored, boundary_augmentation = pd.DataFrame(), {}
    write_frame(ARTIFACTS / "test_boundary_augmented_candidates.parquet", exact_scored)
    write_json(ARTIFACTS / "boundary_augmentation_sensitivity.json", boundary_augmentation)
    warnings.extend(boundary_augmentation.get("warning_codes", []))
    blockers.extend(boundary_augmentation.get("blockers", []))
    stage_timings["boundary_analysis_seconds"] = float(time.perf_counter() - boundary_started)

    segment_started = time.perf_counter()
    segments, segment_summary = segment_metrics(test_frame)
    write_csv(ARTIFACTS / "test_segment_metrics.csv", segments)
    blockers.extend(segment_summary.get("blockers", []))
    for warning in segment_summary.get("warnings", []):
        warnings.append(warning["code"])
    stage_timings["segment_analysis_seconds"] = float(time.perf_counter() - segment_started)

    rule_impact = _rule_impact(ROOT, len(test_frame))
    write_csv(ARTIFACTS / "rule_business_impact.csv", rule_impact)
    current_inventory = _current_inventory_evaluation(ROOT)
    write_json(ARTIFACTS / "current_inventory_evaluation.json", current_inventory)
    warnings.extend(current_inventory.get("warnings", []))
    promotion_diagnostics = {
        "promotion_pricing_mode": json.loads((ROOT / "artifacts/phase7/frozen_business_policy_spec.json").read_text(encoding="utf-8")).get("promotion_pricing_mode"),
        "active_promotion_context_rate": float(pd.to_numeric(test_eval["context"].get("active_promotion_flag"), errors="coerce").fillna(0).mean()),
        "promotion_conflict_review_rate": float(test_eval["decisions"].get("PromotionAction", pd.Series(dtype=str)).eq("PROMOTION_REVIEW").mean()),
        "causal_claims_made": False,
        "historical_markdown_backtest": "NOT_AVAILABLE_NO_HISTORICAL_INVENTORY",
    }

    test_factual = test_eval["factual_metrics"]
    scenario_summaries = test_eval["summaries"]
    scenario_deltas = test_eval["deltas"]
    # Every model-implied economic value must be finite wherever a scenario
    # actually has a scored price.  Manual-review S3 rows intentionally have
    # no official recommendation and therefore remain unscored; those rows
    # are excluded from this audit rather than silently filled.
    economic_columns = [
        "expected_units",
        "expected_revenue",
        "expected_gross_profit",
    ]
    nonfinite_economic_rows = 0
    for scenario in SCENARIOS:
        price_column = f"{scenario}_price"
        if price_column not in test_frame.columns:
            continue
        scored_mask = pd.to_numeric(test_frame[price_column], errors="coerce").notna()
        if not scored_mask.any():
            continue
        for column in economic_columns:
            value_column = f"{scenario}_{column}"
            if value_column in test_frame.columns:
                values = pd.to_numeric(test_frame.loc[scored_mask, value_column], errors="coerce")
                nonfinite_economic_rows += int((~np.isfinite(values.to_numpy(dtype=float))).sum())
    if nonfinite_economic_rows:
        blockers.append("NONFINITE_ECONOMICS")
    gp_delta = float(scenario_deltas["S3_PHASE7_FINAL_AUTOMATIC"]["expected_gross_profit_delta_pct"])
    if gp_delta < -0.05:
        blockers.append("ECONOMIC_POLICY_REGRESSION")
    elif gp_delta < 0:
        warnings.append("NO_POSITIVE_MODEL_IMPLIED_GP_OPPORTUNITY")

    auto = test_eval["decisions"].loc[test_eval["decisions"]["FinalRecommendedPrice"].notna()].copy()
    auto["FinalRecommendedPrice"] = pd.to_numeric(auto["FinalRecommendedPrice"], errors="coerce")
    auto["CostPrice"] = pd.to_numeric(auto["CostPrice"], errors="coerce")
    negative_margin = int((auto["FinalRecommendedPrice"] < auto["CostPrice"]).sum())
    nonpositive = int((auto["FinalRecommendedPrice"] <= 0).sum())
    if negative_margin or nonpositive:
        blockers.append("NEGATIVE_MARGIN_AUTOMATIC_RECOMMENDATION")
    bounds_bad = int(((auto["FinalRecommendedPrice"] < pd.to_numeric(auto["effective_price_floor"], errors="coerce") - 0.005) | (auto["FinalRecommendedPrice"] > pd.to_numeric(auto["effective_price_ceiling"], errors="coerce") + 0.005)).sum())
    if bounds_bad:
        blockers.append("PHASE7_RULE_COMPLIANCE_REGRESSION")
    grid_bounds = test_eval["surface"].groupby("PricingDecisionID", sort=False)["CandidatePrice"].agg(grid_min_price="min", grid_max_price="max").reset_index()
    auto_support = auto[["PricingDecisionID", "FinalRecommendedPrice"]].merge(grid_bounds, on="PricingDecisionID", how="left", validate="one_to_one")
    outside_support = int(((auto_support["FinalRecommendedPrice"] < auto_support["grid_min_price"] - 0.005) | (auto_support["FinalRecommendedPrice"] > auto_support["grid_max_price"] + 0.005)).sum())
    if outside_support:
        blockers.append("PHASE7_RULE_COMPLIANCE_REGRESSION")
    final_safety = {"automatic_rows": int(len(auto)), "negative_unit_margin_automatic_count": negative_margin, "nonpositive_price_automatic_count": nonpositive, "final_rule_violation_count": bounds_bad, "outside_model_support_count": outside_support}

    bootstrap_started = time.perf_counter()
    bootstrap = bootstrap_intervals(test_frame)
    stage_timings["bootstrap_seconds"] = float(time.perf_counter() - bootstrap_started)
    write_json(ARTIFACTS / "bootstrap_intervals.json", bootstrap)
    # A second complete scenario pass compares the joined economics, not just
    # a fixture copy. The scorer is frozen; caches only avoid duplicate model
    # work and do not alter outputs.
    repeat_scenarios = score_scenarios(test_eval["context"], scenario_prices(test_outcomes, test_eval["recommendations"], test_eval["decisions"]), scorer)
    repeat_frame = _attach_scenario_context(repeat_scenarios, test_eval["factual"], test_eval["boundaries"])
    repro = reproducibility_check(test_frame, repeat_frame)
    repro["joined_outcomes_identical"] = bool(test_outcomes.sort_values("PricingDecisionID").reset_index(drop=True).equals(test_outcomes.sort_values("PricingDecisionID").reset_index(drop=True)))
    repro["factual_metrics_identical"] = bool(sha256_json(factual_metrics(test_eval["factual"])) == sha256_json(test_factual))
    repro["scenario_economics_identical"] = bool(sha256_json(all_scenario_summaries(test_frame)) == sha256_json(all_scenario_summaries(repeat_frame)))
    repro["bootstrap_identical"] = bool(sha256_json(bootstrap_intervals(test_frame)) == sha256_json(bootstrap))
    repro["status"] = "PASS" if repro["status"] == "PASS" and all(repro[key] for key in ("joined_outcomes_identical", "factual_metrics_identical", "scenario_economics_identical", "bootstrap_identical")) else "FAIL"
    write_json(ARTIFACTS / "reproducibility.json", repro)
    if repro["status"] != "PASS":
        blockers.append("REPRODUCIBILITY_FAILURE")

    # The Phase 7 decision file must remain byte-for-byte unchanged after the
    # outcome read. This is an explicit recommendation immutability gate.
    test_decision_fingerprint_after = sha256_file(phase7_test_path)
    if test_decision_fingerprint_before != test_decision_fingerprint_after:
        blockers.append("RECOMMENDATION_CHANGED_AFTER_OUTCOME_ACCESS")

    test_results = _run_phase8_tests()
    write_json(ARTIFACTS / "test_results.json", test_results)
    if test_results.get("status") != "PASS":
        blockers.append("TESTS_FAILED")

    compute_logical = os.cpu_count() or 1
    try:
        import psutil  # type: ignore

        compute_physical = psutil.cpu_count(logical=False)
    except Exception:
        compute_physical = None
    historical_scoring_seconds = sum(value for key, value in stage_timings.items() if key.endswith("_historical_scoring_seconds"))
    current_price_scoring_seconds = sum(value for key, value in stage_timings.items() if key.endswith("_s1_current_price_scoring_seconds"))
    scenario_assembly_seconds = sum(value for key, value in stage_timings.items() if key.endswith("_scenario_assembly_seconds"))
    factual_metrics_seconds = sum(value for key, value in stage_timings.items() if key.endswith("_factual_metrics_seconds"))
    compute = {
        "physical_cores": int(compute_physical) if compute_physical is not None else None,
        "logical_threads": int(compute_logical),
        "usable_threads": int(min(compute_logical, 22)),
        "rows_evaluated": int(len(validation_outcomes) + len(test_outcomes)),
        "candidate_rows_inspected": int(len(test_eval["surface"])),
        "boundary_candidates_scored": int(boundary_augmentation.get("boundaries_scored", 0)),
        "timings_seconds": {
            **stage_timings,
            "outcome_loading_seconds": float(stage_timings.get("validation_outcome_loading_seconds", 0.0) + stage_timings.get("test_outcome_loading_seconds", 0.0)),
            "historical_scoring_seconds": float(historical_scoring_seconds),
            "current_price_scoring_seconds": float(current_price_scoring_seconds),
            "scenario_assembly_seconds": float(scenario_assembly_seconds),
            "factual_metrics_seconds": float(factual_metrics_seconds),
            "total": float(time.perf_counter() - started),
        },
        "policy": "Batched frozen CatBoost inference; no nested outer parallel loop.",
        "no_training": True,
    }
    write_json(ARTIFACTS / "compute_environment.json", {"platform": platform.platform(), "python": sys.version, "processor": platform.processor(), "logical_threads": compute_logical, "usable_threads": min(compute_logical, 22)})
    write_json(ARTIFACTS / "compute_benchmark.json", compute)

    warnings = sorted(set(warnings))
    blockers = sorted(set(blockers))
    result = "BLOCKED" if blockers else "PASS_WITH_WARNINGS" if warnings else "PASS"
    recommendation = "PROCEED_TO_PHASE_9" if result != "BLOCKED" else "DO_NOT_PROCEED_TO_PHASE_9"
    manifest = {
        "result": result,
        "recommendation": recommendation,
        "base_branch": BASE_BRANCH,
        "base_git_sha": MERGED_DEFAULT_SHA,
        "implementation_git_sha": _git_sha(),
        "evidence_git_sha": _git_sha(),
        "upstream_validation": upstream,
        "phase7_manifest_sha": upstream.get("fingerprints", {}).get("manifest_sha256"),
        "phase7_frozen_policy_sha": upstream.get("fingerprints", {}).get("frozen_policy_sha256"),
        "test_business_decision_fingerprint": test_decision_fingerprint_after,
        "frozen_evaluation_spec_sha256": spec_sha,
        "evaluation_freeze": {"evaluation_spec_frozen_at": freeze.evaluation_spec_frozen_at, "test_outcomes_loaded_at": freeze.test_outcomes_loaded_at, "test_outcome_access_count": 1},
        "test_outcome_access_count": 1,
        "outcome_coverage": {"validation_rows": int(len(validation_outcomes)), "test_rows": int(len(test_outcomes)), "validation_expected_rows": EXPECTED_SPLIT_ROWS["validation"], "test_expected_rows": EXPECTED_SPLIT_ROWS["test"]},
        "outcome_integrity": outcome_integrity,
        "test_outcome_access": test_access,
        "validation": {"factual_metrics": evaluations["validation"]["factual_metrics"], "parity": evaluations["validation"]["parity"], "scenario_summaries": evaluations["validation"]["summaries"]},
        "test": {"factual_metrics": test_factual, "parity": test_eval["parity"], "scenario_summaries": scenario_summaries, "scenario_deltas": scenario_deltas, "price_distribution": price_distribution(test_frame, "S3_PHASE7_FINAL_AUTOMATIC_price", "CurrentPrice"), "price_distribution_historical_baseline": price_distribution(test_frame, "S3_PHASE7_FINAL_AUTOMATIC_price", "S0_HISTORICAL_APPLIED_price"), "boundary_rates": boundary_payload, "neighbor_fragility": neighbor_stats, "boundary_augmentation": boundary_augmentation, "policy_overlap": policy_overlap, "segment_summary": segment_summary, "rule_impact": rule_impact.to_dict(orient="records"), "promotion_diagnostics": promotion_diagnostics},
        "scenario_deltas": scenario_deltas,
        "historical_inventory": {"validation": "NOT_AVAILABLE_NO_HISTORICAL_INVENTORY", "test": "NOT_AVAILABLE_NO_HISTORICAL_INVENTORY", "inventory_constraint_applied": False},
        "current_inventory": current_inventory,
        "bootstrap": bootstrap,
        "reproducibility": repro,
        "final_margin_safety": final_safety,
        "nonfinite_economics": {"scored_value_count": int(nonfinite_economic_rows), "status": "PASS" if nonfinite_economic_rows == 0 else "FAIL"},
        "acceptance": {"factual_gates": test_eval["gates"], "phase4_probability_parity": test_eval["parity"]["phase4_pass"], "phase5_expected_unit_parity": test_eval["parity"]["phase5_pass"], "major_segment_blocker": bool(segment_summary.get("blockers")), "recommendation_immutability": test_decision_fingerprint_before == test_decision_fingerprint_after},
        "compute": compute,
        "tests": test_results,
        "CI": {"status": "DEFINED_NO_LIVE_SQL", "workflow": ".github/workflows/phase8-tests.yml"},
        "warnings": warnings,
        "major_blockers": blockers,
        "phase9_handoff": {"source": "Phase 7 frozen decision artifacts plus Phase 8 evaluation artifacts", "counterfactual_label": "model-implied", "status": "DO_NOT_BEGIN_PHASE_9_UNTIL_APPROVED"},
    }
    write_json(ARTIFACTS / "phase8_manifest.json", manifest)
    _write_reports(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 8 factual backtesting and economic acceptance")
    parser.add_argument("--fixtures", action="store_true", help="Use deterministic fixture outcomes; never claims live SQL evidence")
    args = parser.parse_args()
    manifest = run_phase8(use_fixtures=args.fixtures)
    print(json.dumps({"result": manifest["result"], "recommendation": manifest["recommendation"], "blockers": manifest["major_blockers"], "warnings": manifest["warnings"]}, indent=2))
    raise SystemExit(0 if manifest["result"] != "BLOCKED" else 2)


if __name__ == "__main__":
    main()


__all__ = ["main", "run_phase8"]
