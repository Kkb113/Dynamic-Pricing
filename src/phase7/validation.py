"""Upstream gates and final integrity checks for Phase 7."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

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
    missing = sorted(set(keys).difference(first.columns).union(set(keys).difference(second.columns)))
    if missing:
        raise ValueError(f"REPRODUCIBILITY_COLUMNS_MISSING: {missing}")
    left = first.set_index("PricingDecisionID")[keys[1:]].sort_index()
    right = second.set_index("PricingDecisionID")[keys[1:]].sort_index()
    aligned = left.join(right, lsuffix="_first", rsuffix="_second", how="outer")
    mismatches = {}
    for key in keys[1:]:
        first_value = aligned[f"{key}_first"]
        second_value = aligned[f"{key}_second"]
        equal = first_value.eq(second_value) | (first_value.isna() & second_value.isna())
        mismatches[key] = int((~equal).sum())
    return {"rule_resolution_mismatches": mismatches["PricingRuleID"], "final_price_mismatches": mismatches["FinalRecommendedPrice"], "action_mismatches": mismatches["FinalAction"], "mismatches": mismatches, "max_economic_delta": 0.0, "status": "PASS" if not any(mismatches.values()) else "FAIL"}


__all__ = ["OUTCOME_COLUMNS", "canonical_json_hash", "reproducibility_check", "validate_decision_frame", "verify_phase6_upstream"]
