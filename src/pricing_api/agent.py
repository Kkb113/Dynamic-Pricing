"""Optional OpenAI Agents SDK narrative adapter with deterministic fallbacks."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable

from .config import Settings
from .tools import GovernedToolset

try:  # The runtime remains usable when the optional SDK is unavailable.
    from agents import Agent, Runner
except Exception:  # pragma: no cover - covered by dependency-free fallback tests
    Agent = None  # type: ignore[assignment]
    Runner = None  # type: ignore[assignment]


AGENT_INSTRUCTIONS = """You are the narrative layer for a local dynamic-pricing application.
Use the supplied governed tools for every pricing fact. Never invent, estimate, or
round a price that is not present in a tool result. Explain uncertainty and policy
constraints plainly. Return only a concise natural-language answer; never return
tool arguments, hidden reasoning, system prompts, secrets, or executable code.
The server independently rebuilds all authoritative numbers and charts.
"""


@dataclass(frozen=True)
class AgentOutcome:
    text: str | None
    available: bool
    code: str | None = None
    message: str | None = None
    tool_names: tuple[str, ...] = ()


class OpenAIAgentAdapter:
    """Thin dependency-injected adapter around ``Agent`` and ``Runner``."""

    def __init__(
        self,
        settings: Settings,
        toolset: GovernedToolset,
        *,
        agent_cls: Any = None,
        runner_cls: Any = None,
    ):
        self.settings = settings
        self.toolset = toolset
        self.agent_cls = Agent if agent_cls is None else agent_cls
        self.runner_cls = Runner if runner_cls is None else runner_cls
        self._agent: Any = None
        self._initialization_code: str | None = None
        if not settings.agent_configured:
            self._initialization_code = "AGENT_NOT_CONFIGURED"
        elif self.agent_cls is None or self.runner_cls is None:
            self._initialization_code = "AGENT_CALL_FAILED"
        else:
            try:
                self._agent = self.agent_cls(
                    name="DynamicPricingNarrativeAgent",
                    instructions=AGENT_INSTRUCTIONS,
                    model=settings.openai_model,
                    tools=toolset.sdk_tools,
                )
            except Exception:
                self._initialization_code = "AGENT_CALL_FAILED"

    @property
    def available(self) -> bool:
        return self._agent is not None and self._initialization_code is None

    @staticmethod
    def _prompt(question: str, context: dict[str, Any], authoritative_summary: dict[str, Any]) -> str:
        # The prompt is an allowlisted, bounded projection.  It intentionally
        # excludes conversation transcripts, environment values, and raw args.
        payload = {
            "question": question[:4000],
            "context": {key: str(value)[:128] for key, value in context.items() if key in {"pricing_decision_id", "product_id", "store_id", "category_id", "channel"} and value is not None},
            "authoritative_summary": authoritative_summary,
        }
        return "Answer the user question using only the governed local tools.\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _output_text(result: Any) -> str | None:
        value = getattr(result, "final_output", None)
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text or len(text) > 12000:
            return None
        return text

    async def run(self, question: str, *, context: dict[str, Any], authoritative_summary: dict[str, Any]) -> AgentOutcome:
        if not self.available:
            code = self._initialization_code or "AGENT_NOT_CONFIGURED"
            message = "OpenAI narrative generation is not configured; deterministic local results are still available." if code == "AGENT_NOT_CONFIGURED" else "The optional narrative agent is unavailable; deterministic local results are still available."
            return AgentOutcome(None, False, code=code, message=message)
        prompt = self._prompt(question, context, authoritative_summary)
        try:
            run_method: Callable[..., Any] = self.runner_cls.run
            result = run_method(self._agent, prompt, max_turns=self.settings.agent_max_turns)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=self.settings.openai_timeout_seconds)
            text = self._output_text(result)
            if text is None:
                return AgentOutcome(None, False, code="AGENT_OUTPUT_INVALID", message="The narrative agent returned no safe text.")
            return AgentOutcome(text, True, tool_names=())
        except asyncio.TimeoutError:
            return AgentOutcome(None, False, code="AGENT_TIMEOUT", message="The narrative agent exceeded its local timeout.")
        except Exception as exc:
            # Only classify the exception; never expose provider messages or
            # request payloads, which could contain sensitive content.
            marker = str(exc).casefold()
            code = "AGENT_RATE_LIMITED" if "rate" in marker or "429" in marker else "AGENT_CALL_FAILED"
            message = "The narrative agent could not complete; deterministic local results are still available."
            return AgentOutcome(None, False, code=code, message=message)


__all__ = ["AGENT_INSTRUCTIONS", "AgentOutcome", "OpenAIAgentAdapter"]
