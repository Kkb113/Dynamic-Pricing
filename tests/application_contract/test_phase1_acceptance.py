from __future__ import annotations

import json
from pathlib import Path

import yaml

from application_contracts.validation import validate_document


ROOT = Path(__file__).resolve().parents[2]


def test_application_contract_index_is_consistent():
    index = yaml.safe_load((ROOT / "contracts/application/application_contract_v1.yaml").read_text(encoding="utf-8"))
    assert index["version"] == 1
    assert index["runtime"]["mode"] == "local_only"
    assert index["runtime"]["frontend"] == "react"
    assert index["runtime"]["backend"] == "fastapi"
    assert index["secrets"]["openai_api_key"]["owner"] == "fastapi"
    assert index["secrets"]["openai_api_key"]["browser_visible"] is False
    assert index["api"]["chat"]["path"] == "/api/v1/pricing/chat"
    assert index["api"]["stream"]["path"] == "/api/v1/pricing/chat/stream"
    assert len(index["authority"]["tool_names"]) == 10


def test_required_phase1_docs_and_adrs_exist():
    required = [
        "docs/PHASE1_APPLICATION_ARCHITECTURE.md",
        "docs/PHASE1_API_CONTRACT.md",
        "docs/PHASE1_PRICING_INTENTS.md",
        "docs/PHASE1_AGENT_GOVERNANCE.md",
        "docs/PHASE1_REACT_STATE_CONTRACT.md",
        "docs/adr/ADR-001-react-fastapi-boundary.md",
        "docs/adr/ADR-002-server-only-openai-key.md",
        "docs/adr/ADR-003-structured-chart-specifications.md",
        "docs/adr/ADR-004-local-only-runtime.md",
        ".env.example",
    ]
    for relative in required:
        assert (ROOT / relative).exists(), relative


def test_phase1_docs_state_the_non_negotiable_boundaries():
    architecture = (ROOT / "docs/PHASE1_APPLICATION_ARCHITECTURE.md").read_text(encoding="utf-8").lower()
    governance = (ROOT / "docs/PHASE1_AGENT_GOVERNANCE.md").read_text(encoding="utf-8").lower()
    intents = (ROOT / "docs/PHASE1_PRICING_INTENTS.md").read_text(encoding="utf-8").lower()
    react = (ROOT / "docs/PHASE1_REACT_STATE_CONTRACT.md").read_text(encoding="utf-8").lower()
    for phrase in ["fastapi", "react", "trust boundary", "openai_api_key", "deterministic", "chain-of-thought", "local-only"]:
        assert phrase in architecture or phrase in governance
    for phrase in ["unsupported", "model_support_limit", "missing_pricing_context", "policy_rejected"]:
        assert phrase in intents
    for phrase in ["jsonresponsepanel", "in-memory", "localstorage", "model-implied"]:
        assert phrase in react


def test_health_fixture_is_secret_free():
    health = json.loads((ROOT / "tests/application_contract/fixtures/health_ready.json").read_text(encoding="utf-8"))
    assert health == {
        "status": "ready",
        "runtime": "local",
        "contract_version": "1",
        "agent_available": False,
        "artifacts_integrity": "pass",
    }


def test_checked_in_acceptance_manifest_records_passing_validation():
    manifest = json.loads((ROOT / "artifacts/phase1_application/phase1_application_manifest.json").read_text(encoding="utf-8"))
    assert manifest["result"] == "PASS_WITH_WARNINGS"
    assert all(manifest["gates"].values())
    assert manifest["targeted_tests"]["status"] == "PASS"
    assert manifest["full_suite"]["status"] == "PASS"
