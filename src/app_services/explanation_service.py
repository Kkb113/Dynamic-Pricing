"""Deterministic, business-readable explanations with an honest SHAP fallback."""

from __future__ import annotations

from typing import Any

from .recommendation_service import RecommendationService


class ExplanationService:
    def __init__(self, recommendations: RecommendationService):
        self.recommendations = recommendations

    def explain(self, decision_id: str, *, split: str = "validation") -> dict[str, Any]:
        result = self.recommendations.explain_pricing_recommendation(decision_id, split=split)
        result["explainability"] = {
            "type": "DETERMINISTIC_BUSINESS_FALLBACK",
            "status": "MODEL_SHAP_NOT_AVAILABLE",
            "positive_drivers": [],
            "negative_drivers": [],
            "warning": "MODEL_SHAP_NOT_AVAILABLE; explanation uses frozen economics, business rules, reason codes, price movement, and promotion/markdown context.",
        }
        return result


__all__ = ["ExplanationService"]
