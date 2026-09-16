"""Offline Phase 4 hardening tests.

No test in this module contacts OpenAI.  Provider behavior is represented by
small fakes and all evidence paths are temporary or explicitly injected.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pricing_api.agent import AgentOutcome, OpenAIAgentAdapter
from pricing_api.config import Settings
from pricing_api.contracts import dump_model
from pricing_api.live_validation import run_live_validation
from pricing_api.models import AuthoritativeData, HealthResponse, PricingChatResponse, ResponseMetadata
from pricing_api.orchestrator import PricingOrchestrator
from pricing_api.preflight import build_preflight
from pricing_api.services import ServiceContainer
from pricing_api.tools import GovernedToolset

from tests.phase2.test_pricing_api import FakeContainer, make_client, request


class _ToolItem:
    type = "tool_call_item"

    def __init__(self, name: str):
        self.tool_name = name


class _SDKAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _SuccessfulRunner:
    @staticmethod
    async def run(agent, prompt, **kwargs):
        class Result:
            final_output = "The governed capability result is available."
            new_items = [_ToolItem("get_agent_capabilities")]

        return Result()


def test_sdk_result_extracts_only_allowlisted_tool_names_and_preserves_success():
    adapter = OpenAIAgentAdapter(
        Settings(openai_api_key="test-only", openai_model="gpt-test"),
        GovernedToolset(FakeContainer()),
        agent_cls=_SDKAgent,
        runner_cls=_SuccessfulRunner,
    )
    outcome = asyncio.run(adapter.run("what can you do?", context={}, authoritative_summary={"has_capabilities": True}))
    assert outcome.available is True
    assert outcome.sdk_success is True
    assert outcome.tool_names == ("get_agent_capabilities",)
    assert outcome.tool_names_valid is True


def test_unknown_sdk_tool_name_invalidates_grounding_metadata():
    class BadResult:
        final_output = "Safe-looking narrative."
        new_items = [_ToolItem("delete_prices")]

    class BadRunner:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            return BadResult()

    adapter = OpenAIAgentAdapter(
        Settings(openai_api_key="test-only", openai_model="gpt-test"),
        GovernedToolset(FakeContainer()),
        agent_cls=_SDKAgent,
        runner_cls=BadRunner,
    )
    outcome = asyncio.run(adapter.run("what can you do?", context={}, authoritative_summary={}))
    assert outcome.sdk_success is True
    assert outcome.tool_names == ()
    assert outcome.tool_names_valid is False


def test_tool_provenance_distinguishes_pre_route_and_agent_scope():
    toolset = GovernedToolset(FakeContainer())
    toolset.execute("get_agent_capabilities")
    deterministic = toolset.drain_trace(source="deterministic")
    with toolset.source_scope("agent"):
        toolset._raw["get_agent_capabilities"]()  # SDK closure uses this same governed function.
    agent = toolset.drain_trace(source="agent")
    assert [record.source for record in deterministic] == ["deterministic"]
    assert [record.source for record in agent] == ["agent"]


def test_overlapping_async_requests_keep_trace_collectors_isolated():
    toolset = GovernedToolset(FakeContainer())

    class OverlapAgent:
        available = True

        async def run(self, question, *, context, authoritative_summary):
            await asyncio.sleep(0)
            with toolset.source_scope("agent"):
                toolset._raw["get_agent_capabilities"]()
            await asyncio.sleep(0)
            return AgentOutcome(
                "The supported capabilities are listed in the structured response.",
                True,
                sdk_success=True,
                tool_names=("get_agent_capabilities",),
            )

    orchestrator = PricingOrchestrator(FakeContainer(), OverlapAgent(), toolset=toolset)

    async def run_two():
        return await asyncio.gather(
            orchestrator.handle(__import__("pricing_api.models", fromlist=["PricingChatRequest"]).PricingChatRequest.model_validate(request("what can you do?")), "req_overlap_a"),
            orchestrator.handle(__import__("pricing_api.models", fromlist=["PricingChatRequest"]).PricingChatRequest.model_validate(request("what can you do?")), "req_overlap_b"),
        )

    first, second = asyncio.run(run_two())
    assert first.agent_tool_names == ("get_agent_capabilities",)
    assert second.agent_tool_names == ("get_agent_capabilities",)
    assert all(record.source in {"deterministic", "agent"} for record in first.traces + second.traces)
    assert len(first.traces) == len(second.traces)


class _NoToolNarrative:
    available = True

    async def run(self, question, *, context, authoritative_summary):
        return AgentOutcome("A safe narrative without a governed tool call.", True, sdk_success=True)


class _FabricatedNarrative:
    available = True

    async def run(self, question, *, context, authoritative_summary):
        return AgentOutcome(
            "The price is 999999.",
            True,
            sdk_success=True,
            tool_names=("get_pricing_recommendation",),
        )


def test_no_tool_or_fabricated_numeric_narrative_can_become_authoritative():
    with make_client(agent=_NoToolNarrative()) as client:
        payload = client.post("/api/v1/pricing/chat", json=request("what can you do?")).json()
        assert payload["answer_source"] == "deterministic_fallback"
        assert payload["errors"] == []
        assert payload["warnings"] == []
    with make_client(agent=_FabricatedNarrative()) as client:
        payload = client.post("/api/v1/pricing/chat", json=request("recommend for decision PD-001")).json()
        assert payload["answer_source"] == "deterministic_fallback"
        assert "999999" not in payload["answer"]


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (RuntimeError("401 provider rejected"), "AGENT_CALL_FAILED"),
        (RuntimeError("429 rate limit"), "AGENT_RATE_LIMITED"),
    ],
)
def test_provider_failures_are_stable_and_value_free(exc, code):
    class FailingRunner:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            raise exc

    adapter = OpenAIAgentAdapter(
        Settings(openai_api_key="test-only", openai_model="gpt-test"),
        GovernedToolset(FakeContainer()),
        agent_cls=_SDKAgent,
        runner_cls=FailingRunner,
    )
    outcome = asyncio.run(adapter.run("question", context={}, authoritative_summary={}))
    assert outcome.available is False
    assert outcome.code == code
    assert "401" not in (outcome.message or "")
    assert "429" not in (outcome.message or "")
    assert "provider" not in (outcome.message or "").casefold()


def test_agent_timeout_is_bounded():
    class SlowRunner:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            await asyncio.sleep(0.05)

    adapter = OpenAIAgentAdapter(
        Settings(openai_api_key="test-only", openai_model="gpt-test", openai_timeout_seconds=0.001),
        GovernedToolset(FakeContainer()),
        agent_cls=_SDKAgent,
        runner_cls=SlowRunner,
    )
    outcome = asyncio.run(adapter.run("question", context={}, authoritative_summary={}))
    assert outcome.code == "AGENT_TIMEOUT"


def test_preflight_is_redacted_and_reports_configuration_booleans(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    (frontend / "dist").mkdir(parents=True)
    (frontend / "dist" / "index.html").write_text("ok", encoding="utf-8")
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ServiceContainer, "create", lambda root=None: FakeContainer())
    report = build_preflight(
        Settings(root=tmp_path, openai_api_key="super-secret-test-key", openai_model="gpt-test"),
        repo_root=tmp_path,
        frontend_root=frontend,
    )
    encoded = json.dumps(report, sort_keys=True)
    assert report["configuration"]["openai_api_key_configured"] is True
    assert report["configuration"]["openai_model_configured"] is True
    assert report["configuration"]["model_id"] == "gpt-test"
    assert "super-secret-test-key" not in encoded
    assert "OPENAI_API_KEY" not in encoded
    assert report["artifacts"]["integrity"] == "pass"


def test_preflight_missing_key_is_deterministic_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(ServiceContainer, "create", lambda root=None: FakeContainer())
    report = build_preflight(Settings(root=tmp_path), repo_root=tmp_path, frontend_root=tmp_path / "frontend")
    assert report["mode"] == "deterministic_fallback"
    assert report["live_gate"] == "BLOCKED"
    assert "OPENAI_API_KEY_NOT_CONFIGURED" in report["blockers"]


class _HTTPResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class _FakeHTTPClient:
    def __init__(self, *args, **kwargs):
        self.calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, path):
        self.calls.append(path)
        return _HTTPResponse(200, HealthResponse(agent_available=True, artifacts_integrity="pass", status="ready").model_dump(mode="json"))

    def post(self, path, **kwargs):
        self.calls.append(path)
        payload = dump_model(PricingChatResponse(
            request_id="req_live_test",
            status="completed",
            answer="The supported capabilities are listed in the structured response.",
            answer_source="deterministic_fallback",
            authoritative=AuthoritativeData(),
            metadata=ResponseMetadata(agent_available=True),
        ))
        return _HTTPResponse(200, payload)


class _LiveSuccessHTTPClient(_FakeHTTPClient):
    def post(self, path, **kwargs):
        self.calls.append(path)
        payload = dump_model(PricingChatResponse(
            request_id="req_live_agent",
            status="completed",
            answer="The supported capabilities are listed in the structured response.",
            answer_source="agent",
            authoritative=AuthoritativeData(),
            tools_used=["get_agent_capabilities"],
            metadata=ResponseMetadata(agent_available=True),
        ))
        return _HTTPResponse(
            200,
            payload,
            {"X-Pricing-Agent-Tools": "get_agent_capabilities", "X-Pricing-Agent-SDK-Success": "true"},
        )


class _Health503HTTPClient(_FakeHTTPClient):
    def get(self, path):
        self.calls.append(path)
        return _HTTPResponse(503, HealthResponse(agent_available=True, artifacts_integrity="pass", status="ready").model_dump(mode="json"))


class _AgentUnavailableHTTPClient(_FakeHTTPClient):
    def get(self, path):
        self.calls.append(path)
        return _HTTPResponse(200, HealthResponse(agent_available=False, artifacts_integrity="pass", status="ready").model_dump(mode="json"))


class _Chat503HTTPClient(_FakeHTTPClient):
    def post(self, path, **kwargs):
        self.calls.append(path)
        return _HTTPResponse(503, {"error": "provider detail must not be surfaced"})


class _AgentHeaderMissingHTTPClient(_LiveSuccessHTTPClient):
    def post(self, path, **kwargs):
        response = super().post(path, **kwargs)
        response.headers = {"X-Pricing-Agent-Tools": "", "X-Pricing-Agent-SDK-Success": "false"}
        return response


def test_live_validator_records_only_redacted_structural_evidence(tmp_path):
    report = run_live_validation(
        settings=Settings(root=tmp_path, openai_api_key="test-key", openai_model="gpt-test"),
        client_factory=_FakeHTTPClient,
        output=tmp_path / "live.json",
    )
    assert report["status"] == "FALLBACK"
    assert report["api_calls"] == 2
    assert report["schema_validation"] is True
    assert report["response_hash"]
    encoded = (tmp_path / "live.json").read_text(encoding="utf-8")
    assert "test-key" not in encoded
    assert "req_live_test" not in encoded
    assert "Capabilities" not in encoded
    assert "OPENAI_API_KEY" not in encoded


def test_live_validator_blocks_without_key_without_calling_network(tmp_path):
    class ShouldNotCall:
        def __init__(self, *args, **kwargs):
            raise AssertionError("network must not be called without key/model")

    report = run_live_validation(settings=Settings(root=tmp_path), client_factory=ShouldNotCall)
    assert report["status"] == "BLOCKED"
    assert report["block_reason"] == "OPENAI_KEY_OR_MODEL_NOT_CONFIGURED"
    assert report["api_calls"] == 0


def test_live_validator_requires_real_agent_gate_for_pass(tmp_path):
    report = run_live_validation(
        settings=Settings(root=tmp_path, openai_api_key="test-key", openai_model="gpt-test"),
        client_factory=_LiveSuccessHTTPClient,
    )
    assert report["status"] == "PASS"
    assert report["live_gate"] == "PASS"
    assert report["health_http_status"] == 200
    assert report["chat_http_status"] == 200
    assert report["health_agent_available"] is True
    assert report["agent_tool_names"] == ["get_agent_capabilities"]


@pytest.mark.parametrize(
    ("client", "reason"),
    [
        (_Health503HTTPClient, "HEALTH_HTTP_NOT_READY"),
        (_AgentUnavailableHTTPClient, "AGENT_NOT_AVAILABLE"),
        (_Chat503HTTPClient, "CHAT_HTTP_FAILED"),
        (_AgentHeaderMissingHTTPClient, "GROUNDING_OR_LEAK_CHECK_FAILED"),
    ],
)
def test_live_validator_never_passes_invalid_health_chat_or_agent_gate(tmp_path, client, reason):
    report = run_live_validation(
        settings=Settings(root=tmp_path, openai_api_key="test-key", openai_model="gpt-test"),
        client_factory=client,
    )
    assert report["live_gate"] != "PASS"
    assert report["block_reason"] == reason


def test_release_scripts_are_loopback_hidden_and_owned_pid_only():
    root = Path(__file__).resolve().parents[2]
    start = (root / "scripts" / "start_local_pricing_app.ps1").read_text(encoding="utf-8")
    stop = (root / "scripts" / "stop_local_pricing_app.ps1").read_text(encoding="utf-8")
    assert start.count("-WindowStyle Hidden") == 2
    assert "127.0.0.1" in start
    assert "Stop-Process -Name" not in start + stop
    assert "owned-processes.json" in start + stop
    port_section = start.split("function Assert-PortFree", 1)[1].split("function Get-ProcessIdentity", 1)[0]
    assert "throw \"PORT_CHECK_UNAVAILABLE\"" in port_section
    assert "return $true" not in port_section
    assert "Get-CimInstance Win32_Process" in start + stop
    assert "CreationDate" in start + stop
    assert "PROCESS_IDENTITY_UNAVAILABLE" in start + stop
    assert "PROCESS_IDENTITY_MISMATCH" in stop
    assert "direct_backend_and_vite_root_processes" in start + stop
    assert "vite.js" in start
    assert "npm.cmd" not in start
    assert "Get-ListeningProcessId" in start
    assert "netstat -ano" in start
    assert "depth -Descending" in start + stop
    assert ".phase4-runtime" in start + stop
    assert "BackendPort = 8000" in start
    assert "FrontendPort = 5173" in start
    assert "ValidateRange(1, 65535)" in start
    assert "PORTS_MUST_DIFFER" in start
    assert "Assert-PortFree $BackendPort" in start
    assert "Assert-PortFree $FrontendPort" in start
    assert "Get-ListeningProcessId $BackendPort" in start
    assert "FASTAPI_PORT" in start
    assert "VITE_API_BASE_URL" in start
    assert "backend_port = $BackendPort" in start
    assert "frontend_port = $FrontendPort" in start
    assert "backend_port" in stop and "frontend_port" in stop


def test_phase4_runtime_has_no_raw_print_or_provider_transcript_paths():
    package_root = Path(__file__).resolve().parents[2] / "src" / "pricing_api"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package_root.glob("*.py"))
    assert "print(" not in source
    assert "OPENAI_API_KEY=" not in source
    assert "raw_responses" not in source
    assert "to_sql(" not in source
    assert "pickle.dump" not in source
