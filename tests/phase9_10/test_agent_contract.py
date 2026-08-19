import inspect

from ai_agent.agent import build_agent, run_agent
from ai_agent.instructions import SYSTEM_INSTRUCTIONS
from ai_agent.tools import build_tools


def test_agent_tools_are_curated_and_have_schemas(registry):
    tools = build_tools(registry)
    names = [getattr(tool, "name", getattr(tool, "__name__", "")) for tool in tools]
    assert names == ["get_pricing_recommendation", "explain_pricing_recommendation", "simulate_price", "compare_price_scenarios", "search_recommendations", "get_model_performance", "get_business_rule_details", "get_current_inventory_insight", "get_use_case_summary", "get_agent_capabilities"]
    for tool in tools:
        target = getattr(tool, "func", tool)
        assert inspect.signature(target)


def test_system_instruction_contract():
    lowered = SYSTEM_INSTRUCTIONS.lower()
    for phrase in ["do not invent", "tool results", "causal", "manual review", "api keys", "unsupported price"]:
        assert phrase in lowered


def test_missing_openai_key_keeps_dashboard_available(registry, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    agent, tools, configured = build_agent(registry)
    assert agent is None and configured is False and len(tools) == 10
    result = run_agent("What does this solution do?", registry)
    assert result.available is False
    assert "unavailable" in result.text.lower()
