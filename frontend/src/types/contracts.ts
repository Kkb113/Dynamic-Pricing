export const REQUEST_SCHEMA = "pricing.chat.request.v1" as const;
export const RESPONSE_SCHEMA = "pricing.chat.response.v1" as const;
export const ERROR_SCHEMA = "pricing.chat.error.v1" as const;
export const SSE_SCHEMA = "pricing.chat.sse.v1" as const;
export const CHART_SCHEMA = "pricing.chart.v1" as const;

export const TOOL_NAMES = [
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
] as const;

export type ToolName = (typeof TOOL_NAMES)[number];
export type ResponseStatus = "completed" | "partial" | "rejected" | "failed";
export type AnswerSource = "agent" | "deterministic_fallback" | "policy";
export type WarningCode =
  | "OPENAI_NOT_CONFIGURED"
  | "OPENAI_UNAVAILABLE"
  | "CURRENT_SNAPSHOT_INVENTORY_CONTEXT"
  | "CURRENT_CONTEXT_STALENESS_HIGH"
  | "MANUAL_REVIEW_REQUIRED"
  | "RULE_VIOLATION_REVIEW"
  | "MODEL_IMPLIED_SCENARIO"
  | "OBSERVED_DATA_NOT_AVAILABLE"
  | "COARSE_GRID_VALUE_WARNING"
  | "RESPONSE_PARTIAL";
export type ErrorCode =
  | "INVALID_REQUEST"
  | "UNSUPPORTED_INTENT"
  | "MISSING_PRICING_CONTEXT"
  | "POLICY_REJECTED"
  | "UNKNOWN_PRICING_DECISION"
  | "INVALID_CANDIDATE_PRICE"
  | "MODEL_SUPPORT_LIMIT"
  | "ARTIFACT_INTEGRITY_FAILURE"
  | "AGENT_NOT_CONFIGURED"
  | "AGENT_TIMEOUT"
  | "AGENT_RATE_LIMITED"
  | "AGENT_CALL_FAILED"
  | "AGENT_OUTPUT_INVALID"
  | "TOOL_FAILURE"
  | "TOOL_VALIDATION_FAILED"
  | "INTERNAL_ERROR";

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
}

export interface PricingContext {
  pricing_decision_id?: string;
  product_id?: string;
  store_id?: string;
  category_id?: string;
  channel?: string;
  split?: "validation" | "current";
}

export interface RequestOptions {
  stream?: boolean;
  include_raw_json?: boolean;
  max_charts?: number;
}

export interface PricingChatRequest {
  schema_version: typeof REQUEST_SCHEMA;
  request_id?: string;
  message: string;
  conversation?: ConversationMessage[];
  context?: PricingContext;
  options?: RequestOptions;
}

export interface ErrorDetail {
  code: ErrorCode;
  message: string;
  field?: string;
  retryable: boolean;
}

export interface WarningDetail {
  code: WarningCode;
  message: string;
  severity: "info" | "notice" | "warning";
}

export interface ToolTraceEntry {
  tool_name: ToolName;
  status: "called" | "skipped" | "failed";
  record_count: number;
  error_code?: string;
}

export interface Recommendation {
  source_tool: "get_pricing_recommendation";
  decision_id: string;
  product_id?: string | null;
  store_id?: string | null;
  channel?: string | null;
  category_id?: string | null;
  decision_time?: string | null;
  current_price: number;
  model_optimal_candidate_price?: number | null;
  final_recommended_price?: number | null;
  final_action: string;
  expected_units?: number | null;
  expected_revenue?: number | null;
  expected_gross_profit?: number | null;
  pricing_rule_id?: string | null;
  rule_name?: string | null;
  promotion_action?: string | null;
  markdown_action?: string | null;
  manual_review_required: boolean;
  reason_codes: string[];
  warnings: string[];
}

export interface Scenario {
  source_tool: "simulate_price" | "compare_price_scenarios";
  scenario: string;
  candidate_price: number | null;
  purchase_probability?: number | null;
  expected_quantity_if_purchase?: number | null;
  expected_units?: number | null;
  expected_revenue?: number | null;
  expected_gross_profit?: number | null;
  candidate_margin_pct?: number | null;
  within_model_support?: boolean | null;
  business_rule_compliance?: boolean | null;
  rule_violations?: string[];
  model_implied: boolean;
}

export interface ModelPerformance {
  source_tool: "get_model_performance";
  metrics: {
    roc_auc: number | null;
    average_precision: number | null;
    log_loss: number | null;
    brier_score: number | null;
    top_decile_lift: number | null;
    demand_aggregate_error_pct: number | null;
    revenue_aggregate_error_pct: number | null;
    gp_aggregate_error_pct: number | null;
  };
  business_interpretation: string[];
  caveat: string;
}

export interface InventoryInsight {
  source_tool: "get_current_inventory_insight";
  decision_id: string;
  product_id?: string | null;
  store_id?: string | null;
  category_id?: string | null;
  available_qty?: number | null;
  stock_status?: string | null;
  slow_moving: boolean;
  seasonal: boolean;
  markdown_action?: string | null;
  final_recommended_price?: number | null;
  final_action: string;
  model_implied_context: false;
}

export interface BusinessRule {
  source_tool: "get_business_rule_details";
  pricing_rule_id?: string | null;
  rule_name?: string | null;
  priority?: number | null;
  specificity?: number | null;
  min_price?: number | null;
  max_price?: number | null;
  min_margin_pct?: number | null;
  max_discount_pct?: number | null;
  max_price_change_pct?: number | null;
  final_price_compliant: boolean;
}

export interface Capabilities {
  source_tool: "get_use_case_summary" | "get_agent_capabilities";
  supported_questions: string[];
  use_case?: string;
  business_question?: string;
}

export interface AuthoritativeData {
  numeric_claims_source: "deterministic_local_tools";
  recommendations: Recommendation[];
  scenario_comparisons: Scenario[];
  model_performance: ModelPerformance | null;
  inventory_insights: InventoryInsight[];
  business_rule: BusinessRule | null;
  capabilities: Capabilities | null;
}

export type ChartAxisField = "candidate_price" | "scenario" | "final_action";
export type ChartSeriesField =
  | "candidate_price"
  | "purchase_probability"
  | "expected_quantity_if_purchase"
  | "expected_units"
  | "expected_revenue"
  | "expected_gross_profit"
  | "candidate_margin_pct"
  | "price_change_percentage";

export interface ChartSpec {
  schema_version: typeof CHART_SCHEMA;
  chart_id: string;
  type: "line" | "bar";
  title: string;
  description: string;
  x_axis: {
    field: ChartAxisField;
    label: string;
    value_type: "number" | "string";
    unit?: "none" | "currency" | "count" | "percentage";
  };
  series: Array<{
    field: ChartSeriesField;
    label: string;
    unit: "number" | "currency" | "count" | "percentage";
    color?: string;
  }>;
  points: Array<{
    x: number | string;
    values: Array<{ field: ChartSeriesField; value: number | null }>;
  }>;
  source: {
    tool_name: Exclude<ToolName, "get_model_performance" | "get_use_case_summary" | "get_agent_capabilities">;
    record_path: string;
    data_status: "observed" | "model_implied" | "mixed";
  };
  model_implied: boolean;
}

export interface PricingChatResponse {
  schema_version: typeof RESPONSE_SCHEMA;
  request_id: string;
  status: ResponseStatus;
  answer: string;
  answer_source: AnswerSource;
  authoritative: AuthoritativeData;
  charts: ChartSpec[];
  tools_used: ToolName[];
  tool_trace: ToolTraceEntry[];
  warnings: WarningDetail[];
  errors: ErrorDetail[];
  metadata: {
    runtime: "local";
    agent_available: boolean;
    contract_version: "1";
    duration_ms?: number;
  };
}

export interface PricingChatError {
  schema_version: typeof ERROR_SCHEMA;
  request_id: string;
  status: "error";
  error: ErrorDetail;
  warnings?: WarningDetail[];
}

export interface HealthResponse {
  status: "starting" | "ready" | "blocked";
  runtime: "local";
  contract_version: "1";
  agent_available: boolean;
  artifacts_integrity: "pass" | "blocked" | "unknown";
}

export type SseEvent =
  | { schema_version: typeof SSE_SCHEMA; event: "chat.started"; request_id: string; sequence: number; payload: { status: "started" } }
  | { schema_version: typeof SSE_SCHEMA; event: "chat.tool"; request_id: string; sequence: number; payload: { tool_name: ToolName; status: "started" | "completed" | "failed"; record_count?: number; error_code?: string } }
  | { schema_version: typeof SSE_SCHEMA; event: "chat.delta"; request_id: string; sequence: number; payload: { text: string } }
  | { schema_version: typeof SSE_SCHEMA; event: "chat.completed"; request_id: string; sequence: number; payload: { response: PricingChatResponse } }
  | { schema_version: typeof SSE_SCHEMA; event: "chat.error"; request_id: string; sequence: number; payload: { error: ErrorDetail } };

