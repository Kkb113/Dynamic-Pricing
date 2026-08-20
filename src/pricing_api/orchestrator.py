"""Deterministic routing, normalization, charting, and narrative fallback."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from .agent import AgentOutcome, OpenAIAgentAdapter
from .charts import build_charts
from .contracts import validate_model
from .intent import IntentDecision, IntentRouter
from .normalization import normalize_recommendation
from .models import (
    AuthoritativeData,
    BusinessRule,
    Capabilities,
    ErrorDetail,
    InventoryInsight,
    ModelPerformance,
    PricingChatRequest,
    PricingChatResponse,
    Recommendation,
    ResponseMetadata,
    Scenario,
    ToolTraceEntry,
    WarningDetail,
)
from .services import ServiceContainer
from .tools import GovernedToolset, ToolCallRecord


_DIGIT_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")


@dataclass(frozen=True)
class OrchestrationResult:
    response: PricingChatResponse
    traces: tuple[ToolCallRecord, ...]


def _error(code: str, message: str, *, retryable: bool = False, field: str | None = None) -> ErrorDetail:
    return ErrorDetail(code=code, message=message, retryable=retryable, field=field)


def _warning(code: str, message: str, *, severity: str = "info") -> WarningDetail:
    return WarningDetail(code=code, message=message, severity=severity)  # type: ignore[arg-type]


def _numeric_tokens(value: Any) -> set[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        tokens = {str(value), f"{value:.2f}"}
        if float(value).is_integer():
            tokens.add(str(int(value)))
        return tokens
    if isinstance(value, dict):
        result: set[str] = set()
        for item in value.values():
            result.update(_numeric_tokens(item))
        return result
    if isinstance(value, (list, tuple)):
        result: set[str] = set()
        for item in value:
            result.update(_numeric_tokens(item))
        return result
    return set()


class PricingOrchestrator:
    """Application use-case layer shared by JSON and SSE endpoints."""

    def __init__(self, services: ServiceContainer, agent: Any, *, router: IntentRouter | None = None, toolset: GovernedToolset | None = None):
        self.services = services
        self.toolset = toolset or GovernedToolset(services)
        self.agent = agent
        self.router = router or IntentRouter()

    @property
    def agent_available(self) -> bool:
        return bool(getattr(self.agent, "available", False))

    @staticmethod
    def _empty_authoritative() -> AuthoritativeData:
        return AuthoritativeData()

    @staticmethod
    def _dedupe_names(names: list[str]) -> list[str]:
        return list(dict.fromkeys(names))[:10]

    @staticmethod
    def _trace_models(records: list[ToolCallRecord]) -> list[ToolTraceEntry]:
        return [
            ToolTraceEntry(tool_name=item.tool_name, status=item.status, record_count=item.record_count, error_code=item.error_code)
            for item in records[:20]
        ]

    @staticmethod
    def _answer(decision: IntentDecision, authoritative: AuthoritativeData) -> str:
        if decision.intent in {"capability_explanation", "help"}:
            return "This local assistant answers governed pricing questions using deterministic frozen tools and can present validated chart data and raw JSON."
        if decision.intent == "model_performance":
            return "The validated model-performance evidence is available in the structured response, including ranking and aggregate economic metrics."
        if decision.intent == "inventory_insight":
            return "The current-snapshot inventory insight is available in the structured response; it is observed context and does not create a new price."
        if decision.intent == "business_rule_explanation":
            return "The effective business-rule constraints and compliance result are available in the structured response."
        if decision.intent == "recommendation_search":
            return "The deterministic recommendation search returned the matching governed records in the structured response."
        if decision.intent in {"scenario_simulation", "scenario_comparison"}:
            return "The supported candidate-price scenarios were evaluated by the frozen deterministic pricing tools; see the structured response and chart specifications."
        if authoritative.recommendations:
            rec = authoritative.recommendations[0]
            if rec.final_recommended_price is not None:
                return f"The governed recommendation is {rec.final_recommended_price:g} with action {rec.final_action}; the structured response contains the deterministic evidence."
            return f"The governed recommendation uses action {rec.final_action}; the structured response contains the deterministic evidence."
        if authoritative.capabilities:
            return "The supported capabilities are listed in the structured response."
        return "The deterministic pricing tools completed; see the structured response for authoritative details."

    @staticmethod
    def _agent_text_is_safe(text: str, authoritative: AuthoritativeData, request: PricingChatRequest) -> bool:
        lowered = text.casefold()
        if any(term in lowered for term in ("chain of thought", "system prompt", "api key", "secret", "password")):
            return False
        allowed = _numeric_tokens(authoritative.model_dump(mode="json"))
        if request.context:
            allowed.update(_numeric_tokens(request.context.model_dump(mode="json")))
        for token in _DIGIT_RE.findall(text):
            if token not in allowed and f"{float(token):.2f}" not in allowed:
                return False
        return True

    async def _agent_narrative(self, request: PricingChatRequest, authoritative: AuthoritativeData) -> AgentOutcome:
        context = request.context.model_dump(mode="json") if request.context else {}
        summary = {
            "recommendation_count": len(authoritative.recommendations),
            "scenario_count": len(authoritative.scenario_comparisons),
            "inventory_count": len(authoritative.inventory_insights),
            "has_model_performance": authoritative.model_performance is not None,
            "has_business_rule": authoritative.business_rule is not None,
            "has_capabilities": authoritative.capabilities is not None,
        }
        return await self.agent.run(request.message, context=context, authoritative_summary=summary)

    def _tool_error(self, raw: Any) -> ErrorDetail | None:
        if not isinstance(raw, dict):
            return None
        code = raw.get("error_code")
        if not isinstance(code, str):
            return None
        allowed = {
            "UNKNOWN_PRICING_DECISION",
            "INVALID_CANDIDATE_PRICE",
            "MODEL_SUPPORT_LIMIT",
            "TOOL_FAILURE",
            "TOOL_VALIDATION_FAILED",
        }
        if code not in allowed:
            code = "TOOL_FAILURE"
        return _error(code, str(raw.get("error") or "The deterministic tool could not complete."), retryable=False)

    def _deterministic(self, decision: IntentDecision) -> tuple[AuthoritativeData, list[str], list[ErrorDetail], list[WarningDetail]]:
        authoritative = AuthoritativeData()
        names: list[str] = []
        errors: list[ErrorDetail] = []
        warnings: list[WarningDetail] = []
        decision_id = decision.decision_id

        if decision.intent == "recommendation_lookup":
            if decision_id:
                raw = self.toolset.execute("get_pricing_recommendation", PricingDecisionID=decision_id, split=decision.split)
                names.append("get_pricing_recommendation")
                if error := self._tool_error(raw):
                    errors.append(error)
                else:
                    try:
                        authoritative.recommendations.append(normalize_recommendation(raw))
                    except (TypeError, ValueError):
                        errors.append(_error("TOOL_VALIDATION_FAILED", "The deterministic recommendation did not match the application contract."))
            else:
                raw = self.toolset.execute("search_recommendations", **decision.filters, split=decision.split, limit=20)
                names.append("search_recommendations")
                if error := self._tool_error(raw):
                    errors.append(error)
                elif isinstance(raw, list):
                    for item in raw[:100]:
                        try:
                            authoritative.recommendations.append(normalize_recommendation(item))
                        except (TypeError, ValueError):
                            continue
        elif decision.intent == "recommendation_explanation":
            raw = self.toolset.execute("explain_pricing_recommendation", PricingDecisionID=decision_id, split=decision.split)
            names.append("explain_pricing_recommendation")
            if error := self._tool_error(raw):
                errors.append(error)
            else:
                rec_raw = self.toolset.execute("get_pricing_recommendation", PricingDecisionID=decision_id, split=decision.split)
                names.append("get_pricing_recommendation")
                if error := self._tool_error(rec_raw):
                    errors.append(error)
                else:
                    try:
                        authoritative.recommendations.append(normalize_recommendation(rec_raw))
                    except (TypeError, ValueError):
                        errors.append(_error("TOOL_VALIDATION_FAILED", "The deterministic explanation context did not match the application contract."))
        elif decision.intent == "scenario_simulation":
            raw = self.toolset.execute("simulate_price", PricingDecisionID=decision_id, CandidatePrice=decision.candidate_price, split=decision.split)
            names.append("simulate_price")
            if error := self._tool_error(raw):
                errors.append(error)
            from .normalization import normalize_scenario

            authoritative.scenario_comparisons.append(normalize_scenario(raw if isinstance(raw, dict) else {}, source_tool="simulate_price", label="Candidate price"))
            if isinstance(raw, dict) and raw.get("model_implied"):
                warnings.append(_warning("MODEL_IMPLIED_SCENARIO", "Scenario metrics are model-implied outputs from the frozen local scorer.", severity="notice"))
        elif decision.intent == "scenario_comparison":
            raw = self.toolset.execute("compare_price_scenarios", PricingDecisionID=decision_id, split=decision.split)
            names.append("compare_price_scenarios")
            if error := self._tool_error(raw):
                errors.append(error)
            from .normalization import normalize_scenario

            if isinstance(raw, list):
                for item in raw[:200]:
                    authoritative.scenario_comparisons.append(normalize_scenario(item, source_tool="compare_price_scenarios"))
            if authoritative.scenario_comparisons:
                warnings.append(_warning("MODEL_IMPLIED_SCENARIO", "Scenario metrics are model-implied outputs from the frozen local scorer.", severity="notice"))
        elif decision.intent == "model_performance":
            raw = self.toolset.execute("get_model_performance")
            names.append("get_model_performance")
            if error := self._tool_error(raw):
                errors.append(error)
            else:
                from .normalization import normalize_model_performance

                authoritative.model_performance = normalize_model_performance(raw)
        elif decision.intent == "business_rule_explanation":
            raw = self.toolset.execute("get_business_rule_details", PricingDecisionID=decision_id, split=decision.split)
            names.append("get_business_rule_details")
            if error := self._tool_error(raw):
                errors.append(error)
            else:
                from .normalization import normalize_business_rule

                authoritative.business_rule = normalize_business_rule(raw)
        elif decision.intent == "inventory_insight":
            raw = self.toolset.execute("get_current_inventory_insight", **decision.filters, limit=100)
            names.append("get_current_inventory_insight")
            if error := self._tool_error(raw):
                errors.append(error)
            elif isinstance(raw, list):
                from .normalization import normalize_inventory

                for item in raw[:100]:
                    try:
                        authoritative.inventory_insights.append(normalize_inventory(item))
                    except (TypeError, ValueError):
                        continue
                if decision.split == "current":
                    warnings.append(_warning("CURRENT_SNAPSHOT_INVENTORY_CONTEXT", "Inventory insights come from the accepted current snapshot and are not persisted.", severity="notice"))
        elif decision.intent == "recommendation_search":
            raw = self.toolset.execute("search_recommendations", **decision.filters, limit=100, split=decision.split)
            names.append("search_recommendations")
            if error := self._tool_error(raw):
                errors.append(error)
            elif isinstance(raw, list):
                for item in raw[:100]:
                    try:
                        authoritative.recommendations.append(normalize_recommendation(item))
                    except (TypeError, ValueError):
                        continue
        elif decision.intent == "capability_explanation":
            raw = self.toolset.execute("get_agent_capabilities")
            names.append("get_agent_capabilities")
            if error := self._tool_error(raw):
                errors.append(error)
            else:
                from .normalization import normalize_capabilities

                authoritative.capabilities = normalize_capabilities(raw, source_tool="get_agent_capabilities")

        for rec in authoritative.recommendations:
            for code in rec.warnings:
                if code == "MANUAL_REVIEW_REQUIRED":
                    warnings.append(_warning("MANUAL_REVIEW_REQUIRED", "The deterministic decision requires manual review.", severity="warning"))
                elif code == "RULE_VIOLATION_REVIEW":
                    warnings.append(_warning("RULE_VIOLATION_REVIEW", "The deterministic decision includes a rule-review warning.", severity="warning"))
        return authoritative, self._dedupe_names(names), errors, warnings

    async def handle(self, request: PricingChatRequest, request_id: str) -> OrchestrationResult:
        started = time.perf_counter()
        decision = self.router.route(request)
        names: list[str] = []
        errors: list[ErrorDetail] = []
        warnings: list[WarningDetail] = []
        authoritative = self._empty_authoritative()
        answer_source = "deterministic_fallback"
        status = "completed"

        if not self.services.ready:
            errors.append(_error("ARTIFACT_INTEGRITY_FAILURE", "Frozen pricing artifacts failed integrity checks; pricing tools are unavailable."))
            answer = "The local pricing artifacts are not ready, so no pricing claim was produced."
            answer_source = "policy"
            status = "failed"
        elif decision.error_code:
            errors.append(_error(decision.error_code, decision.error_message or "The request cannot be completed.", field="message" if decision.error_code == "UNSUPPORTED_INTENT" else None))
            answer = decision.error_message or "The request cannot be completed."
            answer_source = "policy"
            status = "rejected"
        else:
            authoritative, names, errors, warnings = self._deterministic(decision)
            if errors:
                status = "partial" if authoritative.recommendations or authoritative.scenario_comparisons or authoritative.inventory_insights else "failed"
            answer = self._answer(decision, authoritative)
            outcome = await self._agent_narrative(request, authoritative)
            if outcome.available and outcome.text and self._agent_text_is_safe(outcome.text, authoritative, request):
                answer = outcome.text
                answer_source = "agent"
            elif outcome.available and outcome.text:
                errors.append(_error("AGENT_OUTPUT_INVALID", "The narrative agent returned text that could not be proven safe; deterministic fallback is active."))
                warnings.append(_warning("OPENAI_UNAVAILABLE", "Deterministic local results remain authoritative while the narrative output is rejected.", severity="notice"))
                status = "partial" if status == "completed" else status
            elif outcome.code == "AGENT_NOT_CONFIGURED":
                warnings.append(_warning("OPENAI_NOT_CONFIGURED", "OpenAI narrative generation is not configured; deterministic fallback is active.", severity="notice"))
            elif outcome.code:
                errors.append(_error(outcome.code, outcome.message or "The narrative agent was unavailable; deterministic fallback is active.", retryable=outcome.code in {"AGENT_TIMEOUT", "AGENT_RATE_LIMITED"}))
                warnings.append(_warning("OPENAI_UNAVAILABLE", "Deterministic local results remain authoritative while narrative generation is unavailable.", severity="notice"))
                status = "partial" if status == "completed" else status
            if not errors and status == "partial":
                warnings.append(_warning("RESPONSE_PARTIAL", "The response contains all available deterministic evidence but one optional path did not complete.", severity="notice"))

        traces = self.toolset.drain_trace()
        names = self._dedupe_names(names + [item.tool_name for item in traces if item.status == "called"])
        charts = build_charts(authoritative, max_charts=request.options.max_charts, tool_names=names)
        payload = PricingChatResponse(
            request_id=request_id,
            status=status,  # type: ignore[arg-type]
            answer=answer[:12000],
            answer_source=answer_source,  # type: ignore[arg-type]
            authoritative=authoritative,
            charts=[chart.model_dump(mode="json") for chart in charts],
            tools_used=names,
            tool_trace=self._trace_models(traces),
            warnings=warnings[:20],
            errors=errors[:20],
            metadata=ResponseMetadata(agent_available=self.agent_available, duration_ms=(time.perf_counter() - started) * 1000),
        )
        try:
            validate_model(payload, "pricing_chat_response_v1.schema.json")
        except Exception:
            # Contract violations are treated as an internal safe failure; do
            # not return the malformed payload or any provider details.
            fallback = PricingChatResponse(
                request_id=request_id,
                status="failed",
                answer="The local response failed contract validation; no unvalidated pricing data was returned.",
                answer_source="policy",
                authoritative=AuthoritativeData(),
                charts=[],
                tools_used=[],
                tool_trace=[],
                warnings=[],
                errors=[_error("TOOL_VALIDATION_FAILED", "The backend response failed its contract validation.")],
                metadata=ResponseMetadata(agent_available=self.agent_available, duration_ms=(time.perf_counter() - started) * 1000),
            )
            validate_model(fallback, "pricing_chat_response_v1.schema.json")
            payload = fallback
            traces = tuple()
        return OrchestrationResult(payload, tuple(traces))


__all__ = ["OrchestrationResult", "PricingOrchestrator"]
