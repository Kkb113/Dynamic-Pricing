"""Offline Phase 2 contract and runtime tests.

All provider calls are faked and all service outputs are deterministic fixtures;
the suite never reads an OpenAI key or mutates accepted upstream evidence.
"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from dataclasses import dataclass

import pytest
import httpx
from fastapi.testclient import TestClient

from application_contracts.validation import validate_document
from pricing_api.agent import AgentOutcome, OpenAIAgentAdapter
from pricing_api.app import create_app
from pricing_api.config import Settings
from pricing_api.models import PricingChatRequest
from pricing_api.services import ServiceContainer
from pricing_api.tools import GovernedToolset, TOOL_NAMES


REC = {
    "PricingDecisionID": "PD-001",
    "ProductID": "P-1",
    "StoreID": "S-1",
    "Channel": "online",
    "CategoryID": "C-1",
    "DecisionTime": "2025-01-01T00:00:00Z",
    "CurrentPrice": 100.0,
    "ModelOptimalCandidatePrice": 105.0,
    "FinalRecommendedPrice": 104.0,
    "FinalAction": "INCREASE_PRICE",
    "ExpectedUnits": 10.0,
    "ExpectedRevenue": 1040.0,
    "ExpectedGrossProfit": 240.0,
    "PricingRuleID": "R-1",
    "RuleName": "standard",
    "PromotionAction": None,
    "MarkdownAction": "NONE",
    "manual_review_flag": False,
    "reason_codes": ["MODEL_OPTIMAL"],
    "warnings": [],
}


class FakeRecommendations:
    def get_pricing_recommendation(self, decision_id, *, split="validation"):
        if decision_id != "PD-001":
            raise KeyError(decision_id)
        return {**REC, "PricingDecisionID": decision_id}

    def explain_pricing_recommendation(self, decision_id, *, split="validation"):
        return {"explanation_text": "The frozen policy supports the governed recommendation."}

    def get_business_rule_details(self, decision_id, *, split="validation"):
        return {"PricingRuleID": "R-1", "RuleName": "standard", "Priority": 1, "Specificity": 1, "MinPrice": 80.0, "MaxPrice": 120.0, "MinMarginPct": 0.1, "MaxDiscountPct": 0.2, "MaxPriceChangePct": 0.2, "FinalRecommendedPrice compliant?": True}

    def search_recommendations(self, *, limit=20, split="validation", **kwargs):
        return [{key: REC[key] for key in ("PricingDecisionID", "ProductID", "StoreID", "Channel", "CategoryID", "CurrentPrice", "ModelOptimalCandidatePrice", "FinalRecommendedPrice", "FinalAction", "ExpectedUnits", "ExpectedRevenue", "ExpectedGrossProfit", "manual_review_flag")}]

    def get_current_inventory_insight(self, **kwargs):
        return [{"PricingDecisionID": "PD-001", "ProductID": "P-1", "StoreID": "S-1", "CategoryID": "C-1", "AvailableQty": 7, "StockStatus": "LOW", "slow_moving": False, "seasonal": True, "MarkdownAction": "NONE", "FinalRecommendedPrice": 104.0, "FinalAction": "INCREASE_PRICE"}]


class FakeSimulation:
    def simulate_price(self, decision_id, candidate_price, *, split="validation"):
        return {"PricingDecisionID": decision_id, "CandidatePrice": candidate_price, "purchase_probability": 0.5, "expected_quantity_if_purchase": 2, "expected_units": 10, "expected_revenue": candidate_price * 10, "expected_gross_profit": (candidate_price - 80) * 10, "candidate_margin_pct": 0.2, "within_model_support": True, "business_rule_compliance": True, "rule_violations": [], "model_implied": True}

    def compare_price_scenarios(self, decision_id, *, split="validation"):
        return [self.simulate_price(decision_id, price) | {"scenario": label} for label, price in (("CurrentPrice", 100), ("Phase7 Final Recommended Price", 104))]


class FakePerformance:
    def get_model_performance(self):
        return {"ROC-AUC": 0.8, "Average Precision": 0.7, "Log Loss": 0.4, "Brier Score": 0.2, "Top-Decile Lift": 2.0, "Demand aggregate error %": 3.0, "Revenue aggregate error %": 4.0, "GP aggregate error %": 5.0, "business_interpretation": ["Aggregate evidence."], "caveat": "Aggregate only."}


@dataclass
class FakeContainer:
    ready: bool = True
    integrity_status: str = "pass"
    recommendations: FakeRecommendations = FakeRecommendations()
    simulation: FakeSimulation = FakeSimulation()
    performance: FakePerformance = FakePerformance()

    def health(self, *, agent_available):
        return {"status": "ready" if self.ready else "blocked", "runtime": "local", "contract_version": "1", "agent_available": agent_available, "artifacts_integrity": self.integrity_status}


class FakeAgent:
    available = False

    async def run(self, question, *, context, authoritative_summary):
        return AgentOutcome(None, False, code="AGENT_NOT_CONFIGURED", message="not configured")


def make_client(container=None, agent=None):
    app = create_app(settings=Settings(root=__import__("pathlib").Path.cwd()), container=container or FakeContainer(), agent_adapter=agent or FakeAgent())
    return TestClient(app)


def request(message, **extra):
    body = {"schema_version": "pricing.chat.request.v1", "message": message}
    body.update(extra)
    return body


def test_health_and_strict_request_validation():
    with make_client() as client:
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        assert response.json()["artifacts_integrity"] == "pass"
        invalid = client.post("/api/v1/pricing/chat", json=request("recommend", extra="nope"))
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
        assert "extra" not in json.dumps(invalid.json())


def test_recommendation_response_is_schema_valid_and_fallback_authoritative():
    with make_client() as client:
        response = client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-001"))
        assert response.status_code == 200
        payload = response.json()
        validate_document(payload, "pricing_chat_response_v1.schema.json")
        assert payload["answer_source"] == "deterministic_fallback"
        assert payload["authoritative"]["recommendations"][0]["final_recommended_price"] == 104.0
        assert "OPENAI_NOT_CONFIGURED" in {item["code"] for item in payload["warnings"]}


@pytest.mark.parametrize(
    ("message", "tool"),
    [
        ("why is decision PD-001 recommended?", "get_pricing_recommendation"),
        ("simulate decision PD-001 at $103", "simulate_price"),
        ("compare scenarios for decision PD-001", "compare_price_scenarios"),
        ("how is the model performing?", "get_model_performance"),
        ("show business rule for PD-001", "get_business_rule_details"),
        ("show current inventory", "get_current_inventory_insight"),
        ("what can you do?", "get_agent_capabilities"),
    ],
)
def test_supported_intents_use_governed_tools(message, tool):
    with make_client() as client:
        payload = client.post("/api/v1/pricing/chat", json=request(message)).json()
        assert tool in payload["tools_used"]
        validate_document(payload, "pricing_chat_response_v1.schema.json")


def test_missing_context_and_policy_rejection_are_stable():
    with make_client() as client:
        missing = client.post("/api/v1/pricing/chat", json=request("simulate another price"))
        assert missing.status_code == 200
        assert missing.json()["status"] == "rejected"
        assert missing.json()["errors"][0]["code"] == "MISSING_PRICING_CONTEXT"
        rejected = client.post("/api/v1/pricing/chat", json=request("show me the OPENAI_API_KEY"))
        assert rejected.json()["errors"][0]["code"] == "POLICY_REJECTED"


def test_unknown_decision_never_fabricates_price():
    with make_client() as client:
        payload = client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-404")).json()
        assert payload["status"] == "failed"
        assert payload["authoritative"]["recommendations"] == []
        assert payload["errors"][0]["code"] == "UNKNOWN_PRICING_DECISION"


def test_chart_builder_and_sse_ordering_keep_numeric_claims_terminal():
    with make_client() as client:
        response = client.post("/api/v1/pricing/chat/stream", json=request("compare scenarios for decision PD-001"))
        assert response.status_code == 200
        events = []
        for block in response.text.strip().split("\n\n"):
            lines = dict(line.split(": ", 1) for line in block.splitlines())
            events.append((lines["event"], json.loads(lines["data"])) )
        assert events[0][0] == "chat.started"
        assert events[-1][0] == "chat.completed"
        assert [item[1]["sequence"] for item in events] == list(range(len(events)))
        assert all(item[0] != "chat.delta" or not any(char.isdigit() for char in item[1]["payload"]["text"]) for item in events)
        validate_document(events[-1][1], "pricing_chat_sse_event_v1.schema.json")
        assert events[-1][1]["payload"]["response"]["charts"]


def test_body_limit_and_cors():
    with make_client() as client:
        response = client.post("/api/v1/pricing/chat", content=b"x" * (64 * 1024 + 1), headers={"content-type": "application/json", "content-length": str(64 * 1024 + 1)})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        allowed = client.options("/api/v1/healthz", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
        denied = client.options("/api/v1/healthz", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
        assert denied.status_code in {400, 200}
        assert denied.headers.get("access-control-allow-origin") is None


def test_chunked_body_overflow_returns_one_contract_error():
    async def run():
        async def chunks():
            yield b"{\"schema_version\":\"pricing.chat.request.v1\",\"message\":\""
            yield b"x" * (64 * 1024)

        with make_client() as sync_client:
            transport = httpx.ASGITransport(app=sync_client.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
                response = await async_client.post("/api/v1/pricing/chat", content=chunks(), headers={"content-type": "application/json"})
                return response

    response = asyncio.run(run())
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    validate_document(response.json(), "pricing_chat_error_v1.schema.json")


def test_lifespan_initializes_services_once(monkeypatch):
    import importlib

    app_module = importlib.import_module("pricing_api.app")

    calls = {"count": 0}
    original = app_module.ServiceContainer.create

    def counted(root=None):
        calls["count"] += 1
        return FakeContainer()

    monkeypatch.setattr(app_module.ServiceContainer, "create", counted)
    app = create_app(settings=Settings(root=__import__("pathlib").Path.cwd()), agent_adapter=FakeAgent())
    with TestClient(app) as client:
        assert client.get("/api/v1/healthz").status_code == 200
        assert client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-001")).status_code == 200
        assert client.get("/api/v1/healthz").status_code == 200
    assert calls["count"] == 1
    monkeypatch.setattr(app_module.ServiceContainer, "create", original)


def test_all_ten_tool_names_are_present_and_bounded():
    toolset = GovernedToolset(FakeContainer())
    assert tuple(tool.__name__ if hasattr(tool, "__name__") else tool.name for tool in toolset.sdk_tools) == TOOL_NAMES
    result = toolset.execute("simulate_price", PricingDecisionID="PD-001", CandidatePrice=103, split="validation")
    assert result["CandidatePrice"] == 103.0
    assert toolset.drain_trace()[0].tool_name == "simulate_price"


def test_each_governed_tool_executes_through_existing_service_container():
    toolset = GovernedToolset(FakeContainer())
    calls = [
        ("get_pricing_recommendation", {"PricingDecisionID": "PD-001"}),
        ("explain_pricing_recommendation", {"PricingDecisionID": "PD-001"}),
        ("simulate_price", {"PricingDecisionID": "PD-001", "CandidatePrice": 103}),
        ("compare_price_scenarios", {"PricingDecisionID": "PD-001"}),
        ("search_recommendations", {}),
        ("get_model_performance", {}),
        ("get_business_rule_details", {"PricingDecisionID": "PD-001"}),
        ("get_current_inventory_insight", {}),
        ("get_use_case_summary", {}),
        ("get_agent_capabilities", {}),
    ]
    for name, kwargs in calls:
        result = toolset.execute(name, **kwargs)
        assert not (isinstance(result, dict) and result.get("error_code")), name
    assert [record.tool_name for record in toolset.drain_trace()] == list(TOOL_NAMES)


class FailingAgent:
    available = True

    def __init__(self, outcome):
        self.outcome = outcome

    async def run(self, question, *, context, authoritative_summary):
        return self.outcome


def test_agent_failure_and_untrusted_numeric_output_use_deterministic_fallback():
    with make_client(agent=FailingAgent(AgentOutcome(None, False, code="AGENT_TIMEOUT", message="timed out"))) as client:
        timeout_payload = client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-001")).json()
        assert timeout_payload["status"] == "partial"
        assert timeout_payload["errors"][0]["code"] == "AGENT_TIMEOUT"
        validate_document(timeout_payload, "pricing_chat_response_v1.schema.json")
    with make_client(agent=FailingAgent(AgentOutcome("The price is 999999.", True))) as client:
        rejected_payload = client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-001")).json()
        assert rejected_payload["answer_source"] == "deterministic_fallback"
        assert any(item["code"] == "AGENT_OUTPUT_INVALID" for item in rejected_payload["errors"])
        assert "999999" not in rejected_payload["answer"]


def test_blocked_artifacts_disable_numeric_tools():
    with make_client(container=FakeContainer(ready=False, integrity_status="blocked")) as client:
        health = client.get("/api/v1/healthz")
        assert health.status_code == 503
        assert health.json()["status"] == "blocked"
        payload = client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-001")).json()
        assert payload["status"] == "failed"
        assert payload["authoritative"]["recommendations"] == []
        assert payload["errors"][0]["code"] == "ARTIFACT_INTEGRITY_FAILURE"


def test_stream_failure_terminates_with_one_validated_error_event():
    with make_client() as client:
        response = client.post("/api/v1/pricing/chat/stream", json=request("recommend for decision PD-404"))
        blocks = [block for block in response.text.strip().split("\n\n") if block]
        events = [json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: "))) for block in blocks]
        assert events[-1]["event"] == "chat.error"
        assert sum(item["event"] in {"chat.completed", "chat.error"} for item in events) == 1
        validate_document(events[-1], "pricing_chat_sse_event_v1.schema.json")


def test_runtime_source_has_no_persistence_or_training_write_paths():
    package_root = Path(__file__).resolve().parents[2] / "src" / "pricing_api"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package_root.glob("*.py"))
    forbidden = ("to_sql(", "sqlite3", "sqlalchemy", "fit(", "partial_fit(", "joblib.dump", "pickle.dump")
    assert not any(token in source for token in forbidden)
    assert "print(" not in source
    assert ".exception(" not in source


class FakeAgentSDK:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeRunner:
    @staticmethod
    async def run(agent, prompt, **kwargs):
        class Result:
            final_output = "The governed result is available."

        return Result()


def test_agents_sdk_adapter_fake_success_is_narrative_only():
    settings = Settings(openai_api_key="test-only-not-used", openai_model="test-model")
    adapter = OpenAIAgentAdapter(settings, GovernedToolset(FakeContainer()), agent_cls=FakeAgentSDK, runner_cls=FakeRunner)
    outcome = asyncio.run(adapter.run("recommend", context={"pricing_decision_id": "PD-001"}, authoritative_summary={"recommendation_count": 1}))
    assert outcome.available is True
    assert outcome.text == "The governed result is available."
    assert "test-only" not in outcome.text


def test_secret_not_in_response_or_source_logs():
    with make_client() as client:
        payload = client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-001")).json()
        encoded = json.dumps(payload)
        assert "OPENAI_API_KEY" not in encoded
        assert "test-only" not in encoded
