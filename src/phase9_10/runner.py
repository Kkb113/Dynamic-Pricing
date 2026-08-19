"""Generate Phase 9–10 evidence without touching upstream artifacts."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .acceptance import build_manifest, data_exposure_audit, render_acceptance_report
from .validation import write_json


def _run_tests(root: Path, target: str) -> dict[str, Any]:
    started = time.perf_counter()
    command = [sys.executable, "-m", "pytest", "-q"] + ([target] if target else [])
    environment = os.environ.copy()
    # The repository conftest defaults to the historical Phase 1 evidence
    # path. Keep final-phase regression runs from mutating accepted upstream
    # artifacts.
    environment["TEST_EVIDENCE_PATH"] = "artifacts/phase9_10/pytest_hook_results.json"
    process = subprocess.run(command, cwd=root, text=True, capture_output=True, env=environment)
    output = (process.stdout + "\n" + process.stderr).strip()
    passed = failed = total = 0
    import re

    match = re.search(r"(\d+) passed", output)
    if match:
        passed = int(match.group(1))
    match = re.search(r"(\d+) failed", output)
    if match:
        failed = int(match.group(1))
    total = passed + failed
    return {"status": "PASS" if process.returncode == 0 else "FAIL", "command": " ".join(command[2:]), "total": total, "passed": passed, "failed": failed, "duration_seconds": round(time.perf_counter() - started, 3), "output_tail": output[-4000:]}


def run(root: Path | str, *, skip_tests: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    evidence = root / "artifacts/phase9_10"
    evidence.mkdir(parents=True, exist_ok=True)
    if skip_tests:
        test_results = {"status": "NOT_RUN", "command": "pytest -q tests/phase9_10"}
        full_suite = {"status": "NOT_RUN", "command": "pytest -q"}
    else:
        test_results = _run_tests(root, "tests/phase9_10")
        full_suite = _run_tests(root, "")
    base_branch = os.getenv("PHASE9_10_BASE_BRANCH", "codex/phase1-data-audit")
    base_sha = os.getenv("PHASE9_10_BASE_SHA", "c23bece2839c8c2e4ece5a474b28041daaf64e53")
    manifest = build_manifest(root, base_branch=base_branch, base_git_sha=base_sha, test_results=test_results, full_suite=full_suite)
    manifest["implementation_git_sha"] = os.getenv("PHASE9_10_IMPLEMENTATION_SHA", "CURRENT_HEAD")
    manifest["evidence_git_sha"] = os.getenv("PHASE9_10_EVIDENCE_SHA", "CURRENT_HEAD")
    write_json(evidence / "upstream_validation.json", manifest["upstream"])
    write_json(evidence / "agent_tool_registry.json", manifest["agent_tool_registry"])
    write_json(evidence / "openai_data_exposure_audit.json", manifest["openai_data_exposure"])
    write_json(evidence / "application_validation.json", manifest["application"])
    write_json(evidence / "recommendation_parity.json", manifest["recommendation_parity"])
    write_json(evidence / "simulation_parity.json", manifest["simulation_parity"])
    write_json(evidence / "model_metrics_parity.json", manifest["model_metrics_parity"])
    write_json(evidence / "agent_tool_reproducibility.json", manifest["reproducibility"])
    write_json(evidence / "explainability_validation.json", manifest["explainability"])
    write_json(evidence / "demo_sample_ids.json", manifest["demo"])
    write_json(evidence / "runtime_environment.json", manifest["runtime"])
    write_json(evidence / "test_results.json", manifest["tests"])
    write_json(evidence / "full_suite_results.json", manifest["full_suite"])
    write_json(evidence / "phase9_10_manifest.json", manifest)
    (root / "docs/FINAL_ACCEPTANCE_REPORT.md").write_text(render_acceptance_report(root, manifest), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    result = run(args.root, skip_tests=args.skip_tests)
    print(result["FINAL_PROJECT_VERDICT"])


if __name__ == "__main__":
    main()
