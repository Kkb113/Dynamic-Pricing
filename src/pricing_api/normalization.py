"""Normalize legacy service dictionaries into the strict application contract."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .models import (
    BusinessRule,
    Capabilities,
    InventoryInsight,
    ModelMetrics,
    ModelPerformance,
    Recommendation,
    Scenario,
)


def json_value(value: Any) -> Any:
    """Convert numpy/pandas/decimal values without retaining framework objects."""

    if value is None:
        return None
    try:
        import pandas as pd

        if value is pd.NA:
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
    except Exception:  # pragma: no cover - pandas is a project dependency
        pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return json_value(float(value))
    if hasattr(value, "item") and not isinstance(value, (str, bytes, Mapping)):
        try:
            return json_value(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _value(raw: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw:
            return json_value(raw[key])
    return default


def _number(raw: Mapping[str, Any], *keys: str, default: float | None = None) -> float | None:
    value = _value(raw, *keys, default=default)
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _required_number(raw: Mapping[str, Any], *keys: str) -> float:
    value = _number(raw, *keys)
    if value is None:
        raise ValueError(f"Missing authoritative numeric field: {keys[0]}")
    return value


def _text(raw: Mapping[str, Any], *keys: str, default: str | None = None) -> str | None:
    value = _value(raw, *keys, default=default)
    if value is None:
        return default
    return str(value)[:500]


def _codes(value: Any) -> list[str]:
    value = json_value(value)
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        token = str(item).strip().upper().replace(" ", "_")
        if token and token not in result:
            result.append(token[:80])
    return result[:30]


def normalize_recommendation(raw: Mapping[str, Any]) -> Recommendation:
    decision_id = _text(raw, "PricingDecisionID", "decision_id")
    action = _text(raw, "FinalAction", "final_action")
    if not decision_id or not action:
        raise ValueError("Authoritative recommendation is missing decision_id or final_action")
    return Recommendation(
        decision_id=decision_id,
        product_id=_text(raw, "ProductID", "product_id"),
        store_id=_text(raw, "StoreID", "store_id"),
        channel=_text(raw, "Channel", "channel"),
        category_id=_text(raw, "CategoryID", "category_id"),
        decision_time=_text(raw, "DecisionTime", "decision_time"),
        current_price=_required_number(raw, "CurrentPrice", "current_price"),
        model_optimal_candidate_price=_number(raw, "ModelOptimalCandidatePrice", "Phase6ModelOptimalCandidatePrice", "model_optimal_candidate_price"),
        final_recommended_price=_number(raw, "FinalRecommendedPrice", "final_recommended_price"),
        final_action=action,
        expected_units=_number(raw, "ExpectedUnits", "expected_units", "inventory_capped_expected_units"),
        expected_revenue=_number(raw, "ExpectedRevenue", "expected_revenue", "inventory_capped_expected_revenue"),
        expected_gross_profit=_number(raw, "ExpectedGrossProfit", "expected_gross_profit", "inventory_capped_expected_gross_profit"),
        pricing_rule_id=_text(raw, "PricingRuleID", "pricing_rule_id"),
        rule_name=_text(raw, "RuleName", "rule_name"),
        promotion_action=_text(raw, "PromotionAction", "promotion_action"),
        markdown_action=_text(raw, "MarkdownAction", "markdown_action"),
        manual_review_required=bool(_value(raw, "manual_review_flag", "manual_review_required", default=False)),
        reason_codes=_codes(_value(raw, "reason_codes", "phase7_change_reason_codes")),
        warnings=_codes(_value(raw, "warnings", default=[])),
    )


def normalize_scenario(raw: Mapping[str, Any], *, source_tool: str, label: str | None = None) -> Scenario:
    scenario = _text(raw, "scenario", default=label or "Candidate scenario") or (label or "Candidate scenario")
    return Scenario(
        source_tool=source_tool,  # type: ignore[arg-type]
        scenario=scenario,
        candidate_price=_number(raw, "CandidatePrice", "candidate_price"),
        purchase_probability=_number(raw, "purchase_probability", "RawPurchaseProbability"),
        expected_quantity_if_purchase=_number(raw, "expected_quantity_if_purchase", "conditional_quantity"),
        expected_units=_number(raw, "expected_units", "safe_expected_units"),
        expected_revenue=_number(raw, "expected_revenue"),
        expected_gross_profit=_number(raw, "expected_gross_profit"),
        candidate_margin_pct=_number(raw, "candidate_margin_pct"),
        within_model_support=bool(_value(raw, "within_model_support")) if "within_model_support" in raw else None,
        business_rule_compliance=bool(_value(raw, "business_rule_compliance")) if "business_rule_compliance" in raw else None,
        rule_violations=_codes(_value(raw, "rule_violations", default=[])),
        model_implied=bool(_value(raw, "model_implied", default=True)),
    )


def normalize_model_performance(raw: Mapping[str, Any]) -> ModelPerformance:
    metrics = ModelMetrics(
        roc_auc=_number(raw, "ROC-AUC", "roc_auc"),
        average_precision=_number(raw, "Average Precision", "average_precision"),
        log_loss=_number(raw, "Log Loss", "log_loss"),
        brier_score=_number(raw, "Brier Score", "brier_score"),
        top_decile_lift=_number(raw, "Top-Decile Lift", "top_decile_lift"),
        demand_aggregate_error_pct=_number(raw, "Demand aggregate error %", "demand_aggregate_error_pct"),
        revenue_aggregate_error_pct=_number(raw, "Revenue aggregate error %", "revenue_aggregate_error_pct"),
        gp_aggregate_error_pct=_number(raw, "GP aggregate error %", "gp_aggregate_error_pct"),
    )
    interpretation = _value(raw, "business_interpretation", default=[])
    if not isinstance(interpretation, list):
        interpretation = [str(interpretation)]
    interpretation = [str(item)[:500] for item in interpretation if item is not None][:10]
    caveat = _text(raw, "caveat", default="Metrics are aggregate evaluation evidence and not individual-outcome guarantees.") or "Metrics are aggregate evaluation evidence and not individual-outcome guarantees."
    return ModelPerformance(metrics=metrics, business_interpretation=interpretation, caveat=caveat)


def normalize_inventory(raw: Mapping[str, Any]) -> InventoryInsight:
    decision_id = _text(raw, "PricingDecisionID", "decision_id")
    action = _text(raw, "FinalAction", "final_action")
    if not decision_id or not action:
        raise ValueError("Inventory insight is missing decision_id or final_action")
    return InventoryInsight(
        decision_id=decision_id,
        product_id=_text(raw, "ProductID", "product_id"),
        store_id=_text(raw, "StoreID", "store_id"),
        category_id=_text(raw, "CategoryID", "category_id"),
        available_qty=_number(raw, "AvailableQty", "available_qty"),
        stock_status=_text(raw, "StockStatus", "stock_status"),
        slow_moving=bool(_value(raw, "slow_moving", "slow_moving_flag", default=False)),
        seasonal=bool(_value(raw, "seasonal", "seasonal_product_flag", default=False)),
        markdown_action=_text(raw, "MarkdownAction", "markdown_action"),
        final_recommended_price=_number(raw, "FinalRecommendedPrice", "final_recommended_price"),
        final_action=action,
    )


def normalize_business_rule(raw: Mapping[str, Any]) -> BusinessRule:
    compliant = _value(raw, "FinalRecommendedPrice compliant?", "final_price_compliant", default=False)
    return BusinessRule(
        pricing_rule_id=_text(raw, "PricingRuleID", "pricing_rule_id"),
        rule_name=_text(raw, "RuleName", "rule_name"),
        priority=_number(raw, "Priority", "priority"),
        specificity=_number(raw, "Specificity", "specificity"),
        min_price=_number(raw, "MinPrice", "min_price", "effective_price_floor"),
        max_price=_number(raw, "MaxPrice", "max_price", "effective_price_ceiling"),
        min_margin_pct=_number(raw, "MinMarginPct", "min_margin_pct"),
        max_discount_pct=_number(raw, "MaxDiscountPct", "max_discount_pct"),
        max_price_change_pct=_number(raw, "MaxPriceChangePct", "max_price_change_pct"),
        final_price_compliant=bool(compliant),
    )


def normalize_capabilities(raw: Mapping[str, Any], *, source_tool: str) -> Capabilities:
    questions = _value(raw, "supported_questions", default=[])
    if not isinstance(questions, list):
        questions = [questions]
    questions = [str(item)[:300] for item in questions if item is not None][:20]
    if not questions:
        questions = ["Ask about governed pricing recommendations and supported scenarios."]
    return Capabilities(
        source_tool=source_tool,  # type: ignore[arg-type]
        supported_questions=questions,
        use_case=_text(raw, "use_case"),
        business_question=_text(raw, "business_question"),
    )


__all__ = [
    "json_value",
    "normalize_business_rule",
    "normalize_capabilities",
    "normalize_inventory",
    "normalize_model_performance",
    "normalize_recommendation",
    "normalize_scenario",
]
