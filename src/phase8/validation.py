"""Phase 8 acceptance gates, fingerprints, and freeze-order state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from validation.artifacts import sha256_file


class EvaluationFreeze:
    """Small state machine preventing TEST outcomes before the protocol hash."""

    def __init__(self) -> None:
        self.spec_written = False
        self.spec_sha256: str | None = None
        self.test_outcomes_loaded = False
        self.evaluation_spec_frozen_at: str | None = None
        self.test_outcomes_loaded_at: str | None = None

    def freeze(self, spec_path: Path) -> str:
        if self.spec_written:
            raise RuntimeError("EVALUATION_SPEC_ALREADY_FROZEN")
        if not spec_path.exists():
            raise RuntimeError("MISSING_FROZEN_EVALUATION_SPEC")
        self.spec_sha256 = sha256_file(spec_path)
        self.spec_written = True
        return self.spec_sha256

    def authorize_test_outcomes(self) -> None:
        """Open the one-time TEST read gate after the spec is frozen."""

        if not self.spec_written:
            raise RuntimeError("TEST_OUTCOMES_BEFORE_EVALUATION_FREEZE")
        if self.test_outcomes_loaded:
            raise RuntimeError("TEST_OUTCOMES_READ_MORE_THAN_ONCE")
        # Authorization is deliberately separate from the completion
        # timestamp: the latter is recorded only after the SELECT has
        # returned, so the manifest's loaded-at timestamp describes reality.
        self.test_outcomes_loaded = True

    def record_test_outcomes_loaded(self, loaded_at: str) -> None:
        if not self.test_outcomes_loaded:
            raise RuntimeError("TEST_OUTCOMES_NOT_AUTHORIZED")
        if self.test_outcomes_loaded_at is not None:
            raise RuntimeError("TEST_OUTCOMES_READ_MORE_THAN_ONCE")
        self.test_outcomes_loaded_at = loaded_at

    def allow_test_outcomes(self, loaded_at: str) -> None:
        """Backward-compatible one-step authorization used by unit tests."""

        self.authorize_test_outcomes()
        self.record_test_outcomes_loaded(loaded_at)


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def upstream_validation(root: Path) -> dict[str, Any]:
    """Verify Phase 7 accepted artifacts without rewriting them."""

    manifest_path = root / "artifacts/phase7/phase7_manifest.json"
    policy_path = root / "artifacts/phase7/frozen_business_policy_spec.json"
    validation_path = root / "artifacts/phase7/validation_business_decisions.parquet"
    test_path = root / "artifacts/phase7/test_business_decisions.parquet"
    current_path = root / "artifacts/phase7/current_inventory_business_decisions.parquet"
    required = [manifest_path, policy_path, validation_path, test_path, current_path]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    if missing:
        return {"status": "BLOCKED", "blocker": "UPSTREAM_ARTIFACT_INTEGRITY_FAILURE", "missing": missing}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    validation = pd.read_parquet(validation_path)
    test = pd.read_parquet(test_path)
    current = pd.read_parquet(current_path)
    blockers = list(manifest.get("major_blockers", []))
    if manifest.get("result") not in {"PASS", "PASS_WITH_WARNINGS"}:
        blockers.append("UPSTREAM_ARTIFACT_INTEGRITY_FAILURE")
    if manifest.get("final_rule_violation_count") != 0:
        blockers.append("PHASE7_FINAL_RULE_VIOLATION")
    if policy.get("rule_precedence_policy") in {None, ""}:
        blockers.append("UPSTREAM_ARTIFACT_INTEGRITY_FAILURE")
    fingerprints = {
        "manifest_sha256": sha256_file(manifest_path),
        "frozen_policy_sha256": sha256_file(policy_path),
        "validation_decisions_sha256": sha256_file(validation_path),
        "test_decisions_sha256": sha256_file(test_path),
        "current_decisions_sha256": sha256_file(current_path),
    }
    return {
        "status": "BLOCKED" if blockers else "PASS",
        "blockers": sorted(set(blockers)),
        "phase7_result": manifest.get("result"),
        "phase7_frozen_policy": policy.get("rule_precedence_policy"),
        "final_rule_violation_count": manifest.get("final_rule_violation_count"),
        "rows": {"validation": int(len(validation)), "test": int(len(test)), "current": int(len(current))},
        "fingerprints": fingerprints,
        "phase7_manifest_base_git_sha": manifest.get("base_git_sha"),
        "phase7_evidence_git_sha": manifest.get("evidence_git_sha"),
        "phase7_upstream": manifest.get("upstream", {}),
    }


def reproducibility_check(first: pd.DataFrame, second: pd.DataFrame, numeric_tolerance: float = 1e-10) -> dict[str, Any]:
    if set(first["PricingDecisionID"].astype(str)) != set(second["PricingDecisionID"].astype(str)):
        return {"status": "FAIL", "mismatches": 1, "max_numeric_delta": float("inf"), "reason": "ID_SET_MISMATCH"}
    left = first.sort_values("PricingDecisionID").reset_index(drop=True)
    right = second.sort_values("PricingDecisionID").reset_index(drop=True)
    mismatches = 0
    max_delta = 0.0
    for column in sorted(set(left.columns).intersection(right.columns)):
        if column == "PricingDecisionID":
            continue
        if pd.api.types.is_bool_dtype(left[column]) or pd.api.types.is_bool_dtype(right[column]):
            mismatches += int((left[column].fillna(False).astype(bool) != right[column].fillna(False).astype(bool)).sum())
        elif pd.api.types.is_numeric_dtype(left[column]) or pd.api.types.is_numeric_dtype(right[column]):
            a = pd.to_numeric(left[column], errors="coerce")
            b = pd.to_numeric(right[column], errors="coerce")
            delta = (a - b).abs()
            max_delta = max(max_delta, float(delta.max(skipna=True) or 0.0))
            mismatches += int((delta.fillna(0.0) > numeric_tolerance).sum())
        else:
            mismatches += int((left[column].astype(str).fillna("<NA>") != right[column].astype(str).fillna("<NA>")).sum())
    return {"status": "PASS" if mismatches == 0 and max_delta <= numeric_tolerance else "FAIL", "mismatches": mismatches, "max_numeric_delta": max_delta, "tolerance": numeric_tolerance}


__all__ = ["EvaluationFreeze", "reproducibility_check", "sha256_json", "upstream_validation"]
