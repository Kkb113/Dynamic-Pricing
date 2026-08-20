"""Small deterministic intent router used before any optional model call."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import PricingChatRequest


_DECISION_RE = re.compile(r"\b(?:pricing\s*decision|decision|pd)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"(?:\$\s*|(?:candidate|another|try|price(?:\s+of)?|at)\s+)([0-9]{1,12}(?:\.[0-9]{1,4})?)", re.IGNORECASE)
_UNSAFE_RE = re.compile(
    r"(?:openai[_\s-]*api[_\s-]*key|api\s*key|secret|password|chain[-\s]*of[-\s]*thought|system\s+prompt|retrain|train\s+the\s+model|write\s*back|write\s+price|update\s+price|delete|drop\s+table|\bsql\b|shell\s+command|execute\s+code)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    decision_id: str | None = None
    candidate_price: float | None = None
    split: str = "validation"
    filters: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class IntentRouter:
    """Classify only the contract's supported questions and required context."""

    @staticmethod
    def _decision_id(request: PricingChatRequest) -> str | None:
        if request.context and request.context.pricing_decision_id:
            return request.context.pricing_decision_id
        match = _DECISION_RE.search(request.message)
        return match.group(1) if match else None

    @staticmethod
    def _price(request: PricingChatRequest) -> float | None:
        match = _PRICE_RE.search(request.message)
        if not match:
            return None
        try:
            value = float(match.group(1))
        except ValueError:
            return None
        return value if value > 0 else None

    @staticmethod
    def _context_filters(request: PricingChatRequest) -> dict[str, Any]:
        context = request.context
        if not context:
            return {}
        return {
            "ProductID": context.product_id,
            "StoreID": context.store_id,
            "CategoryID": context.category_id,
            "Channel": context.channel,
        }

    def route(self, request: PricingChatRequest) -> IntentDecision:
        text = request.message.strip()
        lowered = text.casefold()
        if _UNSAFE_RE.search(text):
            return IntentDecision("policy_rejected", error_code="POLICY_REJECTED", error_message="This local pricing assistant cannot expose secrets, hidden reasoning, or perform write operations.")

        decision_id = self._decision_id(request)
        split = request.context.split if request.context else "validation"
        filters = self._context_filters(request)

        if any(term in lowered for term in ("what can you do", "capabilit", "help", "use case", "what does this solution")):
            return IntentDecision("capability_explanation", split=split)
        if any(term in lowered for term in ("model performance", "model performing", "how accurate", "auc", "brier", "lift", "metrics")):
            return IntentDecision("model_performance", split=split)
        if any(term in lowered for term in ("inventory", "stock", "slow-moving", "slow moving", "seasonal")):
            return IntentDecision("inventory_insight", decision_id=decision_id, split="current", filters=filters)
        if any(term in lowered for term in ("business rule", "pricing rule", "constraint", "floor", "ceiling", "compliant")):
            if not decision_id:
                return IntentDecision("business_rule_explanation", split=split, error_code="MISSING_PRICING_CONTEXT", error_message="Provide a pricing decision id so the frozen business rule can be inspected.")
            return IntentDecision("business_rule_explanation", decision_id=decision_id, split=split)
        if any(term in lowered for term in ("which products", "list recommendations", "search recommendations", "find recommendations", "show recommendations")):
            return IntentDecision("recommendation_search", split=split, filters=filters)
        if any(term in lowered for term in ("compare", "versus", "vs ", "current and final", "scenarios")):
            if not decision_id:
                return IntentDecision("scenario_comparison", split=split, error_code="MISSING_PRICING_CONTEXT", error_message="Provide a pricing decision id to compare its governed price scenarios.")
            return IntentDecision("scenario_comparison", decision_id=decision_id, split=split)
        if any(term in lowered for term in ("simulate", "what happens if", "try another", "candidate price")):
            candidate = self._price(request)
            if not decision_id:
                return IntentDecision("scenario_simulation", split=split, candidate_price=candidate, error_code="MISSING_PRICING_CONTEXT", error_message="Provide a pricing decision id and a supported candidate price to simulate.")
            if candidate is None:
                return IntentDecision("scenario_simulation", decision_id=decision_id, split=split, error_code="MISSING_PRICING_CONTEXT", error_message="Provide the candidate price you want to simulate.")
            return IntentDecision("scenario_simulation", decision_id=decision_id, candidate_price=candidate, split=split)
        if any(term in lowered for term in ("why", "explain", "reason", "justification")):
            if not decision_id:
                return IntentDecision("recommendation_explanation", split=split, error_code="MISSING_PRICING_CONTEXT", error_message="Provide a pricing decision id so the deterministic recommendation can be explained.")
            return IntentDecision("recommendation_explanation", decision_id=decision_id, split=split)
        if any(term in lowered for term in ("recommend", "recommended price", "what price", "pricing decision", "final price")):
            if not decision_id and not filters:
                return IntentDecision("recommendation_lookup", split=split, error_code="MISSING_PRICING_CONTEXT", error_message="Provide a pricing decision id or product context for a deterministic recommendation lookup.")
            return IntentDecision("recommendation_lookup", decision_id=decision_id, split=split, filters=filters)
        return IntentDecision("unsupported", split=split, error_code="UNSUPPORTED_INTENT", error_message="I support governed recommendation lookups, explanations, supported price scenarios, model performance, inventory, business rules, and capability questions.")


__all__ = ["IntentDecision", "IntentRouter"]
