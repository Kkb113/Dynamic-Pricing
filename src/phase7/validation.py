"""Upstream gates and final integrity checks for Phase 7."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from validation.artifacts import sha256_file


OUTCOME_COLUMNS = frozenset({"PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime", "OrderLineID"})
REQUIRED_DECISION_COLUMNS = (
    "PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "Channel", "CategoryID",
    "CurrentPrice", "BasePrice", "CostPrice", "Phase6ModelOptimalCandidatePrice",
    "FinalRecommendedPrice", "FinalAction", "PricingRuleID", "effective_price_floor",
    "effective_price_ceiling", "passes_all_pricing_rules", "PromotionAction", "MarkdownAction",
    "inventory_constraint_applied", "InventorySnapshotDate", "AvailableQty", "StockStatus",
    "expected_units", "expected_revenue", "expected_gross_profit", "manual_review_flag",
    "ADVISORY_ONLY", "AUTO_WRITEBACK",
)


def canonical_json_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def verify_phase6_upstream(root: Path) -> dict[str, Any]:
    artifact_dir = root / "artifacts/phase6"
    manifest_path = artifact_dir / "phase6_manifest.json"
    spec_path = artifact_dir / "frozen_optimizer_spec.json"
    surface_paths = {split: artifact_dir / f"{split}_candidate_surface.parquet" for split in ("validation", "test")}
    recommendation_paths = {split: artifact_dir / f"{split}_recommendations.parquet" for split in ("validation", "test")}
    required = [manifest_path, spec_path, *surface_paths.values(), *recommendation_paths.values()]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"UPSTREAM_ARTIFACT_INTEGRITY_FAILURE: missing={missing}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if manifest.get("result") != "PASS_WITH_WARNINGS":
        raise RuntimeError("UPSTREAM_ARTIFACT_INTEGRITY_FAILURE: phase6 result")
    if spec.get("official_objective") != "EXPECTED_GROSS_PROFIT" or spec.get("phase5_estimator_type") != "CONSTANT_MEAN":
        raise RuntimeError("UPSTREAM_ARTIFACT_INTEGRITY_FAILURE: official stack")
    if abs(float(spec.get("phase5_mean_value", 0.0)) - 1.3057971014492753) > 1e-15:
        raise RuntimeError("UPSTREAM_ARTIFACT_INTEGRITY_FAILURE: quantity mean")
    fingerprints = {split: sha256_file(path) for split, path in surface_paths.items()}
    recommendation_fingerprints = {split: sha256_file(path) for split, path in recommendation_paths.items()}
    return {
        "manifest_path": str(manifest_path.relative_to(root)),
        "manifest_sha256": sha256_file(manifest_path),
        "spec_path": str(spec_path.relative_to(root)),
        "spec_sha256": sha256_file(spec_path),
        "candidate_surface_fingerprints": fingerprints,
        "recommendation_fingerprints": recommendation_fingerprints,
        "phase6_manifest": manifest,
        "frozen_optimizer_spec": spec,
        "warnings_preserved": ["OPTIMIZER_BOUNDARY_HEAVY", "OPTIMIZER_STRONGLY_BOUNDARY_SEEKING", "HIGH_RESPONSE_GUARD_USAGE"],
        "status": "PASS",
    }


def validate_decision_frame(frame: pd.DataFrame, *, mode: str) -> dict[str, Any]:
    missing = sorted(set(REQUIRED_DECISION_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"PHASE7_DECISION_SCHEMA_MISMATCH: {missing}")
    if OUTCOME_COLUMNS.intersection(frame.columns):
        raise ValueError(f"FORBIDDEN_OUTCOME_COLUMNS_IN_DECISIONS: {sorted(OUTCOME_COLUMNS.intersection(frame.columns))}")
    non_null = frame["FinalRecommendedPrice"].notna()
    violations = int((non_null & ~frame["passes_all_pricing_rules"].astype(bool)).sum())
    if violations:
        raise ValueError("FINAL_PRICE_RULE_VIOLATION")
    if mode == "HISTORICAL_POLICY_MODE":
        if frame["inventory_constraint_applied"].astype(bool).any() or frame["InventorySnapshotDate"].notna().any() or frame["AvailableQty"].notna().any():
            raise ValueError("HISTORICAL_INVENTORY_LEAKAGE")
    if mode == "CURRENT_INVENTORY_MODE":
        out = frame["FinalAction"].eq("OUT_OF_STOCK_NO_PRICE_ACTION")
        if (out & frame["FinalRecommendedPrice"].notna()).any():
            raise ValueError("OUT_OF_STOCK_RECEIVED_PRICE")
    return {
        "rows": int(len(frame)),
        "final_rule_violation_count": violations,
        "manual_review_rate": float(frame["manual_review_flag"].astype(bool).mean()) if len(frame) else 0.0,
        "outcome_columns_used": False,
        "mode": mode,
    }


def reproducibility_check(first: pd.DataFrame, second: pd.DataFrame) -> dict[str, Any]:
    keys = ["PricingDecisionID", "PricingRuleID", "RecommendedPromotionID", "MarkdownAction", "FinalRecommendedPrice", "FinalAction", "manual_review_flag"]
    economic_columns = [
        "expected_units", "expected_revenue", "expected_gross_profit",
        "inventory_capped_expected_units", "inventory_capped_expected_revenue",
        "inventory_capped_expected_gross_profit",
    ]
    present_economics = [column for column in economic_columns if column in first.columns or column in second.columns]
    comparison_columns = [*keys[1:], *present_economics]
    missing = sorted(set(keys).difference(first.columns).union(set(keys).difference(second.columns)))
    missing.extend(sorted(set(present_economics).difference(first.columns).union(set(present_economics).difference(second.columns))))
    if missing:
        raise ValueError(f"REPRODUCIBILITY_COLUMNS_MISSING: {sorted(set(missing))}")
    left = first.set_index("PricingDecisionID")[comparison_columns].sort_index()
    right = second.set_index("PricingDecisionID")[comparison_columns].sort_index()
    aligned = left.join(right, lsuffix="_first", rsuffix="_second", how="outer")
    mismatches = {}
    max_economic_delta = 0.0

    def _numeric_equal(left_values: pd.Series, right_values: pd.Series) -> tuple[pd.Series, float]:
        left_numeric = pd.to_numeric(left_values, errors="coerce").to_numpy(dtype=float)
        right_numeric = pd.to_numeric(right_values, errors="coerce").to_numpy(dtype=float)
        one_missing = np.isnan(left_numeric) ^ np.isnan(right_numeric)
        equal = np.isclose(left_numeric, right_numeric, atol=1e-12, rtol=0.0, equal_nan=True)
        equal[one_missing] = False
        finite = np.isfinite(left_numeric) & np.isfinite(right_numeric)
        delta = float(np.max(np.abs(left_numeric[finite] - right_numeric[finite]))) if finite.any() else 0.0
        return pd.Series(equal, index=left_values.index), delta

    for key in comparison_columns:
        first_value = aligned[f"{key}_first"]
        second_value = aligned[f"{key}_second"]
        numeric = key in {"FinalRecommendedPrice", *economic_columns}
        if numeric:
            equal, delta = _numeric_equal(first_value, second_value)
            if key in economic_columns:
                max_economic_delta = max(max_economic_delta, delta)
        else:
            equal = first_value.eq(second_value) | (first_value.isna() & second_value.isna())
        mismatches[key] = int((~equal).sum())
    return {
        "rows_compared": int(len(aligned)),
        "rule_resolution_mismatches": mismatches["PricingRuleID"],
        "final_price_mismatches": mismatches["FinalRecommendedPrice"],
        "action_mismatches": mismatches["FinalAction"],
        "economic_mismatches": int(sum(mismatches[column] for column in present_economics)),
        "mismatches": mismatches,
        "max_economic_delta": max_economic_delta,
        "status": "PASS" if not any(mismatches.values()) else "FAIL",
    }


__all__ = ["OUTCOME_COLUMNS", "canonical_json_hash", "reproducibility_check", "validate_decision_frame", "verify_phase6_upstream"]
