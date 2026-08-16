from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import yaml

from audit.database_profile import connect_read_only, connection_string_from_settings
from audit.report_builder import source_tree_sha256

from .feature_builder import build_feature_dataset_from_tables, fetch_source_tables
from .feature_contract import load_contract
from .source_snapshot import SourceDataChangedError, validate_source_snapshot
from .validation import canonical_dataset_hash, write_artifacts

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("phase2.validation")


def _load_test_evidence(path: Path) -> dict:
    if not path.exists():
        return {"status": "MISSING", "total": 0, "passed": 0, "failed": 1}
    return json.loads(path.read_text(encoding="utf-8"))


def _run_tests(artifact_dir: Path) -> dict:
    evidence_path = artifact_dir / "test_results.json"
    env = os.environ.copy()
    env["TEST_EVIDENCE_PATH"] = str(evidence_path)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, env=env, check=False)
    evidence = _load_test_evidence(evidence_path)
    evidence["runner_exit_code"] = int(result.returncode)
    if result.returncode != 0 or evidence.get("status") != "PASS" or evidence.get("failed", 0) != 0:
        raise RuntimeError(f"Phase 2 tests failed; evidence={evidence}")
    if evidence.get("source_tree_sha256") != source_tree_sha256():
        raise RuntimeError("Phase 2 test evidence does not match the current source tree")
    return evidence


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = yaml.safe_load((ROOT / "config/phase2_features.yaml").read_text(encoding="utf-8"))
    artifact_dir = ROOT / cfg["features"]["artifact_dir"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    tests = _run_tests(artifact_dir)
    contract = load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")
    raw = connection_string_from_settings(cfg["database"], ROOT)
    try:
        with connect_read_only(None, cfg["database"]["odbc_driver"], cfg["database"]["connect_timeout_seconds"], raw_connection=raw) as db:
            source_snapshot = validate_source_snapshot(db, ROOT, cfg["database"]["schema"], cfg["phase1"].get("accepted_head"))
            tables = fetch_source_tables(db, cfg["database"]["schema"])
        params = cfg["features"]
        build_1 = build_feature_dataset_from_tables(
            tables, params["eligible_sales_order_statuses"], params["sales_windows_days"],
            params["behavior_windows_hours"], params["competitor_window_days"],
        )
        build_2 = build_feature_dataset_from_tables(
            tables, params["eligible_sales_order_statuses"], params["sales_windows_days"],
            params["behavior_windows_hours"], params["competitor_window_days"],
        )
        ordered = [feature["name"] for feature in contract["features"]]
        hash_1 = canonical_dataset_hash(build_1.frame, ordered)
        hash_2 = canonical_dataset_hash(build_2.frame, ordered)
        deterministic = {"build_1_fingerprint": hash_1, "build_2_fingerprint": hash_2, "match": hash_1 == hash_2, "canonical_order": ["DecisionTime", "PricingDecisionID"]}
        if not deterministic["match"]:
            raise RuntimeError("NON_DETERMINISTIC_FEATURE_BUILD")
        diagnostics = dict(build_1.diagnostics)
        diagnostics["deterministic_regeneration"] = deterministic
        diagnostics["verdict"] = "PASS_WITH_WARNINGS"
        diagnostics["verdict_reason"] = "All hard Phase 2 checks passed; known sparse optional context remains quantified as warnings."
        write_artifacts(ROOT, build_1.frame, contract, diagnostics, source_snapshot, deterministic, tests)
        LOG.info(json.dumps({"event": "phase2_acceptance_completed", "result": "PASS_WITH_WARNINGS", "rows": len(build_1.frame)}))
        return 0
    except SourceDataChangedError as exc:
        payload = {"result": "BLOCKED", "code": SourceDataChangedError.code, "error": str(exc)}
        (artifact_dir / "phase2_manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        LOG.error(json.dumps(payload))
        return 2
    except Exception as exc:
        LOG.exception("phase2 validation failed")
        payload = {"result": "BLOCKED", "code": type(exc).__name__, "error": str(exc)[:1000]}
        (artifact_dir / "phase2_manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        LOG.error(json.dumps(payload))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
