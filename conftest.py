from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_STARTED = time.perf_counter()


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    stats = reporter.stats if reporter is not None else {}
    from audit.report_builder import source_tree_sha256

    evidence = {
        "source": "pytest_sessionfinish",
        "status": "PASS" if exitstatus == 0 else "FAIL",
        "exit_code": int(exitstatus),
        "total": int(session.testscollected),
        "passed": len(stats.get("passed", [])),
        "failed": len(stats.get("failed", [])) + len(stats.get("error", [])),
        "skipped": len(stats.get("skipped", [])),
        "xfailed": len(stats.get("xfailed", [])),
        "xpassed": len(stats.get("xpassed", [])),
        "duration_seconds": round(time.perf_counter() - _STARTED, 6),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "invocation": [Path(sys.argv[0]).name, *sys.argv[1:]],
        "source_tree_sha256": source_tree_sha256(),
    }
    configured_path = os.environ.get("TEST_EVIDENCE_PATH", "artifacts/phase1/test_results.json")
    path = Path(configured_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
