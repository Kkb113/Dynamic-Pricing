"""The only functions exposed to the OpenAI Pricing Intelligence Agent."""

from __future__ import annotations

from typing import Any

try:  # The optional dependency is installed for configured agent runs/CI.
    from agents import function_tool
except ImportError:  # pragma: no cover - exercised in minimal local installs
    def function_tool(function=None, **_kwargs):
        if function is None:
            return lambda wrapped: wrapped
        return function

from app_services.artifact_registry import ArtifactRegistry
from app_services.model_performance_service import ModelPerformanceService
from app_services.recommendation_service import RecommendationService
from app_services.simulation_service import SimulationError, SimulationService


def _services(registry: ArtifactRegistry | None = None):
    registry = registry or ArtifactRegistry()
    return registry, RecommendationService(registry), SimulationService(registry), ModelPerformanceService(registry)


def build_tools(registry: ArtifactRegistry | None = None) -> list[Any]:
    registry, recommendations, simulation, performance = _services(registry)

    @function_tool
    def get_pricing_recommendation(PricingDecisionID: str) -> dict[str, Any]:
        """Return the authoritative final Phase 7 pricing recommendation for a decision."""
        return recommendations.get_pricing_recommendation(PricingDecisionID)

    @function_tool
    def explain_pricing_recommendation(PricingDecisionID: str) -> dict[str, Any]:
        """Explain a recommendation using deterministic source fields and economics."""
        return recommendations.explain_pricing_recommendation(PricingDecisionID)

    @function_tool
    def simulate_price(PricingDecisionID: str, CandidatePrice: float) -> dict[str, Any]:
        """Score a supported candidate price through the frozen pricing stack."""
        try:
            return simulation.simulate_price(PricingDecisionID, CandidatePrice)
        except SimulationError as exc:
            return {"error_code": exc.code, "error": exc.message, "model_implied": True}

    @function_tool
    def compare_price_scenarios(PricingDecisionID: str) -> list[dict[str, Any]]:
        """Compare historical applied, current, Phase 6, and Phase 7 prices."""
        return simulation.compare_price_scenarios(PricingDecisionID)

    @function_tool
    def search_recommendations(
        ProductID: str | None = None,
        StoreID: str | None = None,
        Channel: str | None = None,
        CategoryID: str | None = None,
        FinalAction: str | None = None,
        manual_review_flag: bool | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search compact final recommendation rows with a maximum limit of 100."""
        return recommendations.search_recommendations(
            ProductID=ProductID,
            StoreID=StoreID,
            Channel=Channel,
            CategoryID=CategoryID,
            FinalAction=FinalAction,
            manual_review_flag=manual_review_flag,
            limit=min(max(int(limit), 1), 100),
        )

    @function_tool
    def get_model_performance() -> dict[str, Any]:
        """Return model and aggregate economic metrics from Phase 8 evidence."""
        return performance.get_model_performance()

    @function_tool
    def get_business_rule_details(PricingDecisionID: str) -> dict[str, Any]:
        """Return the effective rule constraints for a decision."""
        return recommendations.get_business_rule_details(PricingDecisionID)

    @function_tool
    def get_current_inventory_insight(
        ProductID: str | None = None,
        StoreID: str | None = None,
        CategoryID: str | None = None,
        action: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return current snapshot inventory context and governed actions."""
        return recommendations.get_current_inventory_insight(ProductID=ProductID, StoreID=StoreID, CategoryID=CategoryID, action=action, limit=min(max(int(limit), 1), 100))

    @function_tool
    def get_use_case_summary() -> dict[str, Any]:
        """Describe the official business use case and end-to-end question."""
        return {
            "use_case": "AI-Driven Dynamic Pricing & Promotion Optimization for Seasonal and Slow-Moving Retail Products",
            "business_question": "What governed price should be offered for a product context to balance expected demand, revenue, and gross profit while respecting support and business rules?",
            "signals": ["historical price context", "purchase propensity", "expected quantity", "candidate-price economics", "promotions", "seasonal/slow-moving context", "current snapshot inventory"],
        }

    @function_tool
    def get_agent_capabilities() -> dict[str, Any]:
        """List safe example questions supported by the local agent."""
        return {"supported_questions": ["What does this solution do?", "How well is the model performing?", "Why is this price recommended?", "Compare current and final price.", "What happens if I try another supported price?", "Show current snapshot seasonal markdown recommendations."]}

    return [
        get_pricing_recommendation,
        explain_pricing_recommendation,
        simulate_price,
        compare_price_scenarios,
        search_recommendations,
        get_model_performance,
        get_business_rule_details,
        get_current_inventory_insight,
        get_use_case_summary,
        get_agent_capabilities,
    ]


__all__ = ["build_tools"]
