"""Strict Pydantic boundary models for the Phase 1 application contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class ConversationMessage(ContractModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class PricingContext(ContractModel):
    pricing_decision_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    product_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    store_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    category_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    channel: str | None = Field(default=None, min_length=1, max_length=64)
    split: Literal["validation", "current"] = "validation"


class RequestOptions(ContractModel):
    stream: bool = False
    include_raw_json: bool = True
    max_charts: int = Field(default=4, ge=0, le=4)


class PricingChatRequest(ContractModel):
    schema_version: Literal["pricing.chat.request.v1"]
    request_id: str | None = Field(default=None, pattern=r"^req_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    message: str = Field(min_length=1, max_length=4000)
    conversation: list[ConversationMessage] = Field(default_factory=list, max_length=20)
    context: PricingContext | None = None
    options: RequestOptions = Field(default_factory=RequestOptions)


class ErrorDetail(ContractModel):
    code: Literal[
        "INVALID_REQUEST",
        "UNSUPPORTED_INTENT",
        "MISSING_PRICING_CONTEXT",
        "POLICY_REJECTED",
        "UNKNOWN_PRICING_DECISION",
        "INVALID_CANDIDATE_PRICE",
        "MODEL_SUPPORT_LIMIT",
        "ARTIFACT_INTEGRITY_FAILURE",
        "AGENT_NOT_CONFIGURED",
        "AGENT_TIMEOUT",
        "AGENT_RATE_LIMITED",
        "AGENT_CALL_FAILED",
        "AGENT_OUTPUT_INVALID",
        "TOOL_FAILURE",
        "TOOL_VALIDATION_FAILED",
        "INTERNAL_ERROR",
    ]
    message: str = Field(min_length=1, max_length=500)
    field: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    retryable: bool = False


class WarningDetail(ContractModel):
    code: Literal[
        "OPENAI_NOT_CONFIGURED",
        "OPENAI_UNAVAILABLE",
        "HISTORICAL_INVENTORY_SNAPSHOT",
        "CURRENT_CONTEXT_STALENESS_HIGH",
        "MANUAL_REVIEW_REQUIRED",
        "RULE_VIOLATION_REVIEW",
        "MODEL_IMPLIED_SCENARIO",
        "OBSERVED_DATA_NOT_AVAILABLE",
        "COARSE_GRID_VALUE_WARNING",
        "RESPONSE_PARTIAL",
    ]
    message: str = Field(min_length=1, max_length=500)
    severity: Literal["info", "notice", "warning"] = "info"


class ToolTraceEntry(ContractModel):
    tool_name: Literal[
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
    ]
    status: Literal["called", "skipped", "failed"]
    record_count: int = Field(ge=0, le=100)
    error_code: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{1,80}$")


class Recommendation(ContractModel):
    source_tool: Literal["get_pricing_recommendation"] = "get_pricing_recommendation"
    decision_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    product_id: str | None = None
    store_id: str | None = None
    channel: str | None = None
    category_id: str | None = None
    decision_time: str | None = None
    current_price: float = Field(gt=0)
    model_optimal_candidate_price: float | None = None
    final_recommended_price: float | None = None
    final_action: str = Field(min_length=1, max_length=80)
    expected_units: float | None = None
    expected_revenue: float | None = None
    expected_gross_profit: float | None = None
    pricing_rule_id: str | None = None
    rule_name: str | None = None
    promotion_action: str | None = None
    markdown_action: str | None = None
    manual_review_required: bool
    reason_codes: list[str] = Field(default_factory=list, max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class Scenario(ContractModel):
    source_tool: Literal["simulate_price", "compare_price_scenarios"]
    scenario: str = Field(min_length=1, max_length=100)
    candidate_price: float | None = None
    purchase_probability: float | None = None
    expected_quantity_if_purchase: float | None = None
    expected_units: float | None = None
    expected_revenue: float | None = None
    expected_gross_profit: float | None = None
    candidate_margin_pct: float | None = None
    within_model_support: bool | None = None
    business_rule_compliance: bool | None = None
    rule_violations: list[str] = Field(default_factory=list, max_length=30)
    model_implied: bool


class ModelMetrics(ContractModel):
    roc_auc: float | None = None
    average_precision: float | None = None
    log_loss: float | None = None
    brier_score: float | None = None
    top_decile_lift: float | None = None
    demand_aggregate_error_pct: float | None = None
    revenue_aggregate_error_pct: float | None = None
    gp_aggregate_error_pct: float | None = None


class ModelPerformance(ContractModel):
    source_tool: Literal["get_model_performance"] = "get_model_performance"
    metrics: ModelMetrics
    business_interpretation: list[str] = Field(default_factory=list, max_length=10)
    caveat: str = Field(min_length=1, max_length=1000)


class InventoryInsight(ContractModel):
    source_tool: Literal["get_current_inventory_insight"] = "get_current_inventory_insight"
    decision_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    product_id: str | None = None
    store_id: str | None = None
    category_id: str | None = None
    available_qty: float | None = None
    stock_status: str | None = None
    slow_moving: bool
    seasonal: bool
    markdown_action: str | None = None
    final_recommended_price: float | None = None
    final_action: str = Field(min_length=1, max_length=80)
    model_implied_context: Literal[False] = False


class BusinessRule(ContractModel):
    source_tool: Literal["get_business_rule_details"] = "get_business_rule_details"
    pricing_rule_id: str | None = None
    rule_name: str | None = None
    priority: float | None = None
    specificity: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_margin_pct: float | None = None
    max_discount_pct: float | None = None
    max_price_change_pct: float | None = None
    final_price_compliant: bool


class Capabilities(ContractModel):
    source_tool: Literal["get_use_case_summary", "get_agent_capabilities"]
    supported_questions: list[str] = Field(min_length=1, max_length=20)
    use_case: str | None = Field(default=None, max_length=500)
    business_question: str | None = Field(default=None, max_length=500)


class AuthoritativeData(ContractModel):
    numeric_claims_source: Literal["deterministic_local_tools"] = "deterministic_local_tools"
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=100)
    scenario_comparisons: list[Scenario] = Field(default_factory=list, max_length=200)
    model_performance: ModelPerformance | None = None
    inventory_insights: list[InventoryInsight] = Field(default_factory=list, max_length=100)
    business_rule: BusinessRule | None = None
    capabilities: Capabilities | None = None


class ResponseMetadata(ContractModel):
    runtime: Literal["local", "databricks"] = "local"
    agent_available: bool
    contract_version: Literal["1"] = "1"
    duration_ms: float | None = Field(default=None, ge=0)


class PricingChatResponse(ContractModel):
    schema_version: Literal["pricing.chat.response.v1"] = "pricing.chat.response.v1"
    request_id: str = Field(pattern=r"^req_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    status: Literal["completed", "partial", "rejected", "failed"]
    answer: str = Field(max_length=12000)
    answer_source: Literal["agent", "deterministic_fallback", "policy"]
    authoritative: AuthoritativeData
    charts: list[dict[str, Any]] = Field(default_factory=list, max_length=4)
    tools_used: list[str] = Field(default_factory=list, max_length=10)
    tool_trace: list[ToolTraceEntry] = Field(default_factory=list, max_length=20)
    warnings: list[WarningDetail] = Field(default_factory=list, max_length=20)
    errors: list[ErrorDetail] = Field(default_factory=list, max_length=20)
    metadata: ResponseMetadata


class PricingChatError(ContractModel):
    schema_version: Literal["pricing.chat.error.v1"] = "pricing.chat.error.v1"
    request_id: str = Field(pattern=r"^req_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    status: Literal["error"] = "error"
    error: ErrorDetail
    warnings: list[WarningDetail] = Field(default_factory=list, max_length=20)


class HealthResponse(ContractModel):
    status: Literal["starting", "ready", "blocked"]
    runtime: Literal["local", "databricks"] = "local"
    contract_version: Literal["1"] = "1"
    agent_available: bool
    artifacts_integrity: Literal["pass", "blocked", "unknown"]


__all__ = [
    "AuthoritativeData",
    "BusinessRule",
    "Capabilities",
    "ConversationMessage",
    "ErrorDetail",
    "HealthResponse",
    "InventoryInsight",
    "ModelMetrics",
    "ModelPerformance",
    "PricingChatError",
    "PricingChatRequest",
    "PricingChatResponse",
    "PricingContext",
    "Recommendation",
    "RequestOptions",
    "ResponseMetadata",
    "Scenario",
    "ToolTraceEntry",
    "WarningDetail",
]
