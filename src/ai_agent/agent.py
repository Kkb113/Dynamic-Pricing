"""OpenAI Agents SDK orchestration with graceful offline behavior."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from app_services.artifact_registry import ArtifactRegistry

from .instructions import SYSTEM_INSTRUCTIONS
from .tools import build_tools

try:
    from agents import Agent, Runner
except ImportError:  # pragma: no cover - fallback for dashboard without extras
    class Agent:  # type: ignore[no-redef]
        def __init__(self, name: str, instructions: str, tools: list[Any], model: str | None = None):
            self.name, self.instructions, self.tools, self.model = name, instructions, tools, model

    class Runner:  # type: ignore[no-redef]
        @staticmethod
        def run_sync(*_args, **_kwargs):
            raise RuntimeError("OPENAI_AGENTS_NOT_INSTALLED")


@dataclass
class AgentRunResult:
    text: str
    available: bool
    tool_names: list[str] = field(default_factory=list)
    error: str | None = None
    usage: dict[str, Any] | None = None


def build_agent(registry: ArtifactRegistry | None = None) -> tuple[Any | None, list[Any], bool]:
    """Build the agent without making a network request."""

    registry = registry or ArtifactRegistry()
    tools = build_tools(registry)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip() or None
    if not api_key or not model:
        return None, tools, False
    try:
        agent = Agent(name="Retail Pricing Intelligence Agent", instructions=SYSTEM_INSTRUCTIONS, tools=tools, model=model)
    except TypeError:  # older SDKs may not accept model in constructor
        agent = Agent(name="Retail Pricing Intelligence Agent", instructions=SYSTEM_INSTRUCTIONS, tools=tools)
    return agent, tools, True


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", getattr(tool, "__name__", "tool")))


def run_agent(question: str, registry: ArtifactRegistry | None = None) -> AgentRunResult:
    agent, tools, configured = build_agent(registry)
    if not configured or agent is None:
        return AgentRunResult(
            text="AI Agent unavailable — configure OPENAI_API_KEY and OPENAI_MODEL to enable conversational pricing intelligence.",
            available=False,
            tool_names=[],
            error="OPENAI_KEY_OR_MODEL_NOT_CONFIGURED",
        )
    try:
        if hasattr(Runner, "run_sync"):
            result = Runner.run_sync(agent, question)
        else:
            result = asyncio.run(Runner.run(agent, question))
        text = str(getattr(result, "final_output", getattr(result, "output", result)))
        usage = None
        raw_usage = getattr(result, "usage", None)
        if raw_usage is not None:
            usage = {key: getattr(raw_usage, key) for key in ("requests", "input_tokens", "output_tokens", "total_tokens") if hasattr(raw_usage, key)}
        tool_names = [_tool_name(tool) for tool in tools if _tool_name(tool) in text]
        return AgentRunResult(text=text, available=True, tool_names=tool_names, usage=usage)
    except Exception:
        return AgentRunResult(
            text="The AI explanation service is temporarily unavailable. The pricing engine and dashboard remain available.",
            available=False,
            error="AGENT_CALL_FAILED",
        )


__all__ = ["AgentRunResult", "build_agent", "run_agent"]
