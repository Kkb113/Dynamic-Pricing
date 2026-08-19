from __future__ import annotations

import json
from pathlib import Path

import pytest

from application_contracts.validation import ContractValidationError, CONTRACT_DIR, load_schema, validate_document


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("fixture", "schema"),
    [
        ("request_recommendation.json", "pricing_chat_request_v1.schema.json"),
        ("response_recommendation.json", "pricing_chat_response_v1.schema.json"),
        ("error_unsupported.json", "pricing_chat_error_v1.schema.json"),
    ],
)
def test_representative_fixtures_validate(fixture: str, schema: str):
    validate_document(_json(FIXTURES / fixture), schema)


def test_all_representative_sse_events_validate():
    events = _json(FIXTURES / "sse_events.json")
    for event in events:
        validate_document(event, "pricing_chat_sse_event_v1.schema.json")
    validate_document(_json(FIXTURES / "sse_completed.json"), "pricing_chat_sse_event_v1.schema.json")

    grouped: dict[str, list[int]] = {}
    for event in events:
        grouped.setdefault(event["request_id"], []).append(event["sequence"])
    assert grouped["req_demo_stream"] == [0, 1, 2]


def test_contracts_are_json_schema_documents():
    schemas = sorted(CONTRACT_DIR.glob("*.schema.json"))
    assert len(schemas) == 5
    for path in schemas:
        schema = load_schema(path.name)
        assert schema["$schema"].startswith("https://json-schema.org/")
        assert schema["$id"].endswith(path.name)


def test_request_rejects_unknown_fields_and_unbounded_message():
    request = _json(FIXTURES / "request_recommendation.json")
    request["secret"] = "must not cross the boundary"
    with pytest.raises(ContractValidationError):
        validate_document(request, "pricing_chat_request_v1.schema.json")

    request = _json(FIXTURES / "request_recommendation.json")
    request["message"] = "x" * 4001
    with pytest.raises(ContractValidationError):
        validate_document(request, "pricing_chat_request_v1.schema.json")


def test_chart_requires_declared_series_fields():
    response = _json(FIXTURES / "response_recommendation.json")
    response["charts"][0]["points"][0]["values"][0]["field"] = "expected_revenue"
    with pytest.raises(ContractValidationError, match="not declared in series"):
        validate_document(response, "pricing_chat_response_v1.schema.json")


def test_response_separates_answer_from_authoritative_data():
    response = _json(FIXTURES / "response_recommendation.json")
    assert isinstance(response["answer"], str)
    assert response["authoritative"]["numeric_claims_source"] == "deterministic_local_tools"
    assert response["authoritative"]["recommendations"][0]["source_tool"] == "get_pricing_recommendation"
    assert response["tools_used"]
    assert all("arguments" not in item for item in response["tool_trace"])
    assert all("chain" not in key.lower() for key in response)


def test_no_real_openai_key_is_checked_in_to_phase1_assets():
    candidate_paths = [
        ROOT / "contracts/application",
        ROOT / "docs/PHASE1_APPLICATION_ARCHITECTURE.md",
        ROOT / "docs/PHASE1_AGENT_GOVERNANCE.md",
        ROOT / "tests/application_contract/fixtures",
        ROOT / ".env.example",
    ]
    for candidate in candidate_paths:
        paths = candidate.rglob("*") if candidate.is_dir() else [candidate]
        for path in paths:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                assert "sk-" not in text
                assert "OPENAI_API_KEY=sk-" not in text
