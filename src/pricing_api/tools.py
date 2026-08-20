"""Governed Agents SDK tools backed by the existing deterministic services."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from app_services.simulation_service import SimulationError

from .normalization import json_value
from .services import ServiceContainer

try:  # Optional until a server-side key/model is configured.
    from agents import function_tool
except Exception:  # pragma: no cover - exercised when the optional SDK is absent
    def function_tool(function=None, **_kwargs):
        if function is None:
            return lambda wrapped: wrapped
        return function


TOOL_NAMES = (
    "get_pricing_recommendation",
    "explain_pricing_recommendation",
    "simulate_price",
    "compare_price_scenarios",
    "search_recommendations",
    "get_model_performance",
    "get_business_rule_details",
    "get_current_inventory_insight",
    "get_use_case_summary",
    "get_agent_capabilities",
)


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    status: str
    record_count: int
    error_code: str | None = None


class GovernedToolset:
    """A bounded tool registry shared by deterministic routing and the agent."""

    def __init__(self, services: ServiceContainer):
        self.services = services
        self._trace: list[ToolCallRecord] = []
        self._raw = self._build_raw()
        self._sdk_tools = self._build_sdk_tools()

    @staticmethod
    def _identifier(value: str) -> str:
        value = str(value or "").strip()
        if not value or len(value) > 128 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-" for char in value):
            raise ValueError("Identifier is invalid or exceeds the 128-character limit")
        return value

    @staticmethod
    def _optional_text(value: str | None, *, limit: int = 128) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        result = str(value).strip()
        return result[:limit]

    @staticmethod
    def _price(value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise SimulationError("INVALID_CANDIDATE_PRICE", "CandidatePrice must be finite and greater than zero") from exc
        if not math.isfinite(result) or result <= 0 or result > 1_000_000_000:
            raise SimulationError("INVALID_CANDIDATE_PRICE", "CandidatePrice must be finite and greater than zero")
        return round(result, 2)

    @staticmethod
    def _limit(value: Any, *, default: int = 20) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            result = default
        return min(max(result, 1), 100)

    @classmethod
    def _bound(cls, value: Any, *, depth: int = 0) -> Any:
        value = json_value(value)
        if depth > 5:
            return None
        if isinstance(value, dict):
            return {str(key)[:128]: cls._bound(item, depth=depth + 1) for key, item in list(value.items())[:80]}
        if isinstance(value, list):
            return [cls._bound(item, depth=depth + 1) for item in value[:100]]
        if isinstance(value, str):
            return value[:2000]
        return value

    def _record(self, name: str, status: str, value: Any = None, *, error_code: str | None = None) -> None:
        count = len(value) if isinstance(value, list) else (0 if value is None else 1)
        self._trace.append(ToolCallRecord(name, status, min(count, 100), error_code))

    def drain_trace(self) -> list[ToolCallRecord]:
        trace, self._trace = self._trace, []
        return trace

    def _call(self, name: str, fn: Callable[[], Any]) -> Any:
        try:
            value = self._bound(fn())
            self._record(name, "called", value)
            return value
        except SimulationError as exc:
            self._record(name, "failed", error_code=exc.code)
            return {"error_code": exc.code, "error": exc.message, "model_implied": True}
        except KeyError:
            self._record(name, "failed", error_code="UNKNOWN_PRICING_DECISION")
            return {"error_code": "UNKNOWN_PRICING_DECISION", "error": "The requested pricing decision is not available in the frozen local evidence."}
        except ValueError:
            self._record(name, "failed", error_code="TOOL_VALIDATION_FAILED")
            return {"error_code": "TOOL_VALIDATION_FAILED", "error": "The tool input is outside the supported local contract."}
        except Exception:
            self._record(name, "failed", error_code="TOOL_FAILURE")
            return {"error_code": "TOOL_FAILURE", "error": "The deterministic pricing tool could not complete."}

    def _build_raw(self) -> dict[str, Callable[..., Any]]:
        recommendations = self.services.recommendations
        simulation = self.services.simulation
        performance = self.services.performance

        def get_pricing_recommendation(PricingDecisionID: str, split: str = "validation") -> Any:
            decision_id = self._identifier(PricingDecisionID)
            selected_split = split if split in {"validation", "current"} else "validation"
            return self._call("get_pricing_recommendation", lambda: recommendations.get_pricing_recommendation(decision_id, split=selected_split))

        def explain_pricing_recommendation(PricingDecisionID: str, split: str = "validation") -> Any:
            decision_id = self._identifier(PricingDecisionID)
            selected_split = split if split in {"validation", "current"} else "validation"
            return self._call("explain_pricing_recommendation", lambda: recommendations.explain_pricing_recommendation(decision_id, split=selected_split))

        def simulate_price(PricingDecisionID: str, CandidatePrice: float, split: str = "validation") -> Any:
            decision_id = self._identifier(PricingDecisionID)
            price = self._price(CandidatePrice)
            selected_split = split if split in {"validation", "current"} else "validation"
            return self._call("simulate_price", lambda: simulation.simulate_price(decision_id, price, split=selected_split))

        def compare_price_scenarios(PricingDecisionID: str, split: str = "validation") -> Any:
            decision_id = self._identifier(PricingDecisionID)
            selected_split = split if split in {"validation", "current"} else "validation"
            return self._call("compare_price_scenarios", lambda: simulation.compare_price_scenarios(decision_id, split=selected_split))

        def search_recommendations(
            ProductID: str | None = None,
            StoreID: str | None = None,
            Channel: str | None = None,
            CategoryID: str | None = None,
            FinalAction: str | None = None,
            manual_review_flag: bool | None = None,
            limit: int = 20,
            split: str = "validation",
        ) -> Any:
            values = {
                "ProductID": self._optional_text(ProductID),
                "StoreID": self._optional_text(StoreID),
                "Channel": self._optional_text(Channel, limit=64),
                "CategoryID": self._optional_text(CategoryID),
                "FinalAction": self._optional_text(FinalAction, limit=80),
                "manual_review_flag": manual_review_flag,
                "limit": self._limit(limit),
            }
            values["split"] = split if split in {"validation", "current"} else "validation"
            return self._call("search_recommendations", lambda: recommendations.search_recommendations(**values))

        def get_model_performance() -> Any:
            return self._call("get_model_performance", performance.get_model_performance)

        def get_business_rule_details(PricingDecisionID: str, split: str = "validation") -> Any:
            decision_id = self._identifier(PricingDecisionID)
            selected_split = split if split in {"validation", "current"} else "validation"
            return self._call("get_business_rule_details", lambda: recommendations.get_business_rule_details(decision_id, split=selected_split))

        def get_current_inventory_insight(
            ProductID: str | None = None,
            StoreID: str | None = None,
            CategoryID: str | None = None,
            action: str | None = None,
            limit: int = 20,
        ) -> Any:
            values = {
                "ProductID": self._optional_text(ProductID),
                "StoreID": self._optional_text(StoreID),
                "CategoryID": self._optional_text(CategoryID),
                "action": self._optional_text(action, limit=80),
                "limit": self._limit(limit),
            }
            return self._call("get_current_inventory_insight", lambda: recommendations.get_current_inventory_insight(**values))

        def get_use_case_summary() -> Any:
            return self._call(
                "get_use_case_summary",
                lambda: {
                    "use_case": "AI-Driven Dynamic Pricing & Promotion Optimization for Seasonal and Slow-Moving Retail Products",
                    "business_question": "What governed price should be offered for a product context to balance expected demand, revenue, and gross profit while respecting support and business rules?",
                },
            )

        def get_agent_capabilities() -> Any:
            return self._call(
                "get_agent_capabilities",
                lambda: {
                    "supported_questions": [
                        "What does this solution do?",
                        "How well is the model performing?",
                        "Why is this price recommended?",
                        "Compare current and final price.",
                        "What happens if I try another supported price?",
                        "Show current snapshot seasonal markdown recommendations.",
                    ]
                },
            )

        return {
            "get_pricing_recommendation": get_pricing_recommendation,
            "explain_pricing_recommendation": explain_pricing_recommendation,
            "simulate_price": simulate_price,
            "compare_price_scenarios": compare_price_scenarios,
            "search_recommendations": search_recommendations,
            "get_model_performance": get_model_performance,
            "get_business_rule_details": get_business_rule_details,
            "get_current_inventory_insight": get_current_inventory_insight,
            "get_use_case_summary": get_use_case_summary,
            "get_agent_capabilities": get_agent_capabilities,
        }

    def _build_sdk_tools(self) -> list[Any]:
        tools: list[Any] = []
        for name in TOOL_NAMES:
            raw = self._raw[name]
            # Assigning an explicit name keeps the SDK registry stable even
            # when a decorator implementation wraps the function object.
            raw.__name__ = name
            raw.__qualname__ = name
            tools.append(function_tool(raw))
        return tools

    @property
    def sdk_tools(self) -> list[Any]:
        return list(self._sdk_tools)

    @property
    def names(self) -> tuple[str, ...]:
        return TOOL_NAMES

    def execute(self, name: str, **kwargs: Any) -> Any:
        if name not in self._raw:
            raise ValueError("Unsupported tool")
        return self._raw[name](**kwargs)


__all__ = ["GovernedToolset", "TOOL_NAMES", "ToolCallRecord"]
