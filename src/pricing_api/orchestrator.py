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


# Standalone numeric claims only. Digits embedded in business identifiers such
# as PDL000000000029917 or RULE01 are labels, not prices or metrics.
_DIGIT_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z0-9])")


@dataclass(frozen=True)
class OrchestrationResult:
    response: PricingChatResponse
    traces: tuple[ToolCallRecord, ...]
    # Redacted internal release metadata.  These fields never enter the
    # Phase 1 response envelope, but let live validation prove which tools the
    # model actually requested instead of conflating them with pre-routing.
    pre_routing_tools: tuple[str, ...] = ()
    agent_tool_names: tuple[str, ...] = ()
    agent_sdk_success: bool = False


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

    def __init__(self, services: ServiceContainer, agent: Any, *, router: IntentRouter | None = None, toolset: GovernedToolset | None = None, runtime_mode: str = "local"):
        self.services = services
        self.toolset = toolset or GovernedToolset(services)
        self.agent = agent
        self.router = router or IntentRouter()
        self.runtime_mode = runtime_mode if runtime_mode in {"local", "databricks"} else "local"

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
        def money(value: float | None) -> str:
            return "not available" if value is None else f"${value:,.2f}"

        def label(value: str | None) -> str:
            if not value:
                return "standard business action"
            return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", value)).strip().lower()

        def recommendation_lines(items: list[Recommendation]) -> list[str]:
            lines: list[str] = []
            for item in items[:5]:
                review = "manual review is required" if item.manual_review_required else "it can continue through the normal approval process"
                reason = label(item.reason_codes[0]) if item.reason_codes else "the available demand, margin, and policy evidence"
                lines.append(f"- **{label(item.final_action).title()}** at **{money(item.final_recommended_price)}** (current price: {money(item.current_price)}). This is supported by {reason}; {review}.")
            return lines

        if decision.intent in {"capability_explanation", "help"}:
            questions = authoritative.capabilities.supported_questions if authoritative.capabilities else []
            bullets = "\n".join(f"- {question}" for question in questions[:8]) or "- Pricing recommendations and their business rationale\n- Price-scenario comparisons\n- Inventory and promotion opportunities\n- Pricing-rule and model-performance questions"
            return f"""### How the pricing assistant can help

This workspace turns approved pricing evidence into clear commercial decisions. It explains what action is recommended, why it is appropriate, what outcome is expected, and whether a decision needs review.

### Questions you can ask

{bullets}

### Recommended next step

Start with a product, store, category, sales channel, or pricing decision and ask for the best action and supporting business rationale."""
        if decision.intent == "model_performance":
            performance = authoritative.model_performance
            if performance:
                interpretations = "\n".join(f"- {item}" for item in performance.business_interpretation)
                return f"""### Executive assessment

The model has been evaluated for its ability to rank pricing opportunities and estimate commercial outcomes. The available measures should be considered together rather than treated as a single accuracy score.

### What the results mean

{interpretations or '- The available metrics describe ranking quality, probability calibration, and aggregate demand and financial estimation.'}

### Recommended next steps

Use the results to support controlled pricing decisions, continue monitoring demand and financial error after each refresh, and retain business-rule review for higher-risk actions.

**Important context:** {performance.caveat}"""
        if decision.intent == "inventory_insight":
            items = authoritative.inventory_insights
            examples = "\n".join(f"- **{label(item.final_action).title()}** at **{money(item.final_recommended_price)}** for a {label(item.stock_status)} stock position." for item in items[:5])
            return f"""### Inventory pricing assessment

The historical inventory snapshot contains **{len(items)}** relevant inventory opportunities. Seasonal and slow-moving signals illustrate where selling-window and carrying-cost risk can change the best commercial action.

### Priority opportunities

{examples or '- No matching inventory opportunity was returned for the requested scope.'}

### Recommended next steps

Prioritize time-sensitive seasonal and slow-moving stock, confirm operational availability, and monitor sell-through before applying a further price change. These are snapshot-based observations, not live inventory guarantees."""
        if decision.intent == "business_rule_explanation":
            rule = authoritative.business_rule
            if rule:
                status = "complies with the active rule" if rule.final_price_compliant else "requires manual review before implementation"
                next_step = "Continue through the normal approval process." if rule.final_price_compliant else "Review the exception with the pricing owner before changing the customer-facing price."
                return f"""### Business rule assessment

The selected pricing decision **{status}**. The permitted price range is **{money(rule.min_price)} to {money(rule.max_price)}**.

### Why this matters

The rule protects commercial boundaries such as price, margin, discount depth, and the size of a price movement. A model recommendation can only proceed when it remains inside those approved limits.

### Recommended next step

{next_step}"""
        if decision.intent == "recommendation_search":
            lines = "\n".join(recommendation_lines(authoritative.recommendations))
            review_count = sum(1 for item in authoritative.recommendations if item.manual_review_required)
            return f"""### Executive recommendation

The requested portfolio contains **{len(authoritative.recommendations)}** matched pricing opportunities. The strongest representative actions are:

{lines or '- No matching recommendation was found for the requested scope.'}

### Controls and considerations

**{review_count}** returned opportunities require manual review. Treat implementation-ready decisions separately from exceptions so review activity does not delay straightforward actions.

### Recommended next steps

Prioritize opportunities that combine a clear commercial action with no outstanding review requirement, then monitor customer response and margin performance before scaling the action across a wider assortment."""
        if decision.intent in {"scenario_simulation", "scenario_comparison"}:
            scenarios = authoritative.scenario_comparisons
            lines = "\n".join(f"- **{label(item.scenario).title()}** uses a price of **{money(item.candidate_price)}**, with expected revenue of **{money(item.expected_revenue)}** and expected gross profit of **{money(item.expected_gross_profit)}**." for item in scenarios[:5])
            return f"""### Price scenario comparison

The available options show the commercial trade-off between customer response, revenue, gross profit, and business-rule compliance.

{lines or '- No supported price scenarios were returned for this request.'}

### Recommended next steps

Select the option that best balances revenue and gross profit while remaining within model support and approved pricing rules. Route any non-compliant option for review rather than applying it automatically."""
        if authoritative.recommendations:
            rec = authoritative.recommendations[0]
            outcome = f"expected revenue of **{money(rec.expected_revenue)}** and expected gross profit of **{money(rec.expected_gross_profit)}**"
            reasons = ", ".join(label(code) for code in rec.reason_codes[:4]) or "the available demand, margin, inventory, and policy evidence"
            review = "A manual review is required before implementation." if rec.manual_review_required else "No manual review is required; the decision can continue through the normal business approval process."
            return f"""### Executive recommendation

The recommended action is to **{label(rec.final_action)}** at **{money(rec.final_recommended_price)}**, compared with the current price of **{money(rec.current_price)}**.

### Why this is the right action

The decision is supported by {reasons}. The recommendation balances customer response with revenue, gross-profit, inventory, and pricing-rule considerations.

### Expected business outcome

At the recommended price, the available estimates indicate {outcome}. These are decision-support estimates rather than guaranteed results.

### Controls and considerations

{review}

### Recommended next steps

Confirm the current operational context, complete any required approval, implement the price through the normal channel process, and monitor demand and margin response after the change."""
        if authoritative.capabilities:
            return "### Pricing assistant capabilities\n\n" + "\n".join(f"- {item}" for item in authoritative.capabilities.supported_questions)
        return "### Pricing assessment\n\nThe request completed, but no matching business evidence was returned. Broaden the question with a product, store, category, channel, or pricing-decision reference and try again."

    @staticmethod
    def _safe_agent_text(text: str, authoritative: AuthoritativeData, request: PricingChatRequest) -> str | None:
        lowered = text.casefold()
        if any(term in lowered for term in ("chain of thought", "system prompt", "api key", "secret", "password")):
            return None
        allowed = _numeric_tokens(authoritative.model_dump(mode="json"))
        safe_lines: list[str] = []
        for line in text.splitlines():
            # Markdown ordered-list markers are presentation syntax, not
            # pricing claims. Every other number must match tool evidence.
            claim_line = re.sub(r"^\s*\d+\.\s+", "- ", line)
            tokens = _DIGIT_RE.findall(claim_line)
            if any(token not in allowed and f"{float(token):.2f}" not in allowed for token in tokens):
                # Keep the useful narrative instead of rejecting the complete
                # answer when a provider adds an unsupported derived figure.
                continue
            safe_lines.append(line)
        safe_text = "\n".join(safe_lines).strip()
        return safe_text if len(safe_text) >= 20 else None

    @staticmethod
    def _agent_text_is_safe(text: str, authoritative: AuthoritativeData, request: PricingChatRequest) -> bool:
        return PricingOrchestrator._safe_agent_text(text, authoritative, request) == text.strip()

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
                    warnings.append(_warning("HISTORICAL_INVENTORY_SNAPSHOT", "Inventory insights use the sealed 2025-12-31 historical snapshot and are not live inventory.", severity="notice"))
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
        """Handle one request inside an isolated trace collector."""

        with self.toolset.trace_scope():
            return await self._handle(request, request_id)

    async def _handle(self, request: PricingChatRequest, request_id: str) -> OrchestrationResult:
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
            deterministic_traces = self.toolset.drain_trace(source="deterministic")
            if errors:
                status = "partial" if authoritative.recommendations or authoritative.scenario_comparisons or authoritative.inventory_insights else "failed"
            answer = self._answer(decision, authoritative)
            outcome = await self._agent_narrative(request, authoritative)
            agent_traces = self.toolset.drain_trace(source="agent")
            agent_called_names = {item.tool_name for item in agent_traces if item.status == "called"}
            safe_agent_text = self._safe_agent_text(outcome.text, authoritative, request) if outcome.text else None
            # The SDK result must be accompanied by a successful governed
            # wrapper trace.  A hand-constructed narrative or malformed SDK
            # item cannot claim a tool merely by naming it in metadata.
            if (
                outcome.available
                and outcome.text
                and outcome.sdk_success
                and outcome.tool_names_valid
                and outcome.tool_names
                and any(name in agent_called_names for name in outcome.tool_names)
                and safe_agent_text
            ):
                answer = safe_agent_text
                answer_source = "agent"
            elif outcome.available and outcome.text:
                # Optional prose rejection is not a pricing failure. The
                # governed result is already complete and remains visible.
                # ``answer_source`` records the fallback without presenting a
                # successful pricing request as a user-facing error banner.
                pass
            elif outcome.code == "AGENT_NOT_CONFIGURED":
                warnings.append(_warning("OPENAI_NOT_CONFIGURED", "OpenAI narrative generation is not configured; deterministic fallback is active.", severity="notice"))
            elif outcome.code:
                errors.append(_error(outcome.code, outcome.message or "The narrative agent was unavailable; deterministic fallback is active.", retryable=outcome.code in {"AGENT_TIMEOUT", "AGENT_RATE_LIMITED"}))
                warnings.append(_warning("OPENAI_UNAVAILABLE", "Deterministic local results remain authoritative while narrative generation is unavailable.", severity="notice"))
                status = "partial" if status == "completed" else status
            if not errors and status == "partial":
                warnings.append(_warning("RESPONSE_PARTIAL", "The response contains all available deterministic evidence but one optional path did not complete.", severity="notice"))
        if "deterministic_traces" not in locals():
            deterministic_traces = self.toolset.drain_trace(source="deterministic")
            outcome = None
            agent_traces = self.toolset.drain_trace(source="agent")
        traces = deterministic_traces + agent_traces
        agent_tool_names = tuple(getattr(outcome, "tool_names", ()) or ()) if outcome is not None else tuple()
        names = self._dedupe_names(names + [item.tool_name for item in traces if item.status == "called"] + list(agent_tool_names))
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
            metadata=ResponseMetadata(runtime=self.runtime_mode, agent_available=self.agent_available, duration_ms=(time.perf_counter() - started) * 1000),
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
                metadata=ResponseMetadata(runtime=self.runtime_mode, agent_available=self.agent_available, duration_ms=(time.perf_counter() - started) * 1000),
            )
            validate_model(fallback, "pricing_chat_response_v1.schema.json")
            payload = fallback
            traces = tuple()
        return OrchestrationResult(
            payload,
            tuple(traces),
            pre_routing_tools=tuple(dict.fromkeys(item.tool_name for item in deterministic_traces if item.status == "called")),
            agent_tool_names=tuple(dict.fromkeys(agent_tool_names)),
            agent_sdk_success=bool(getattr(outcome, "sdk_success", False)) if outcome is not None else False,
        )


__all__ = ["OrchestrationResult", "PricingOrchestrator"]
