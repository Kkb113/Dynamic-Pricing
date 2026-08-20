import {
  CHART_SCHEMA,
  ERROR_SCHEMA,
  REQUEST_SCHEMA,
  RESPONSE_SCHEMA,
  SSE_SCHEMA,
  TOOL_NAMES,
  type ChartSpec,
  type HealthResponse,
  type PricingChatError,
  type PricingChatRequest,
  type PricingChatResponse,
  type SseEvent,
} from "../types/contracts";

export class ContractValidationError extends Error {
  readonly path: string;

  constructor(message: string, path = "$") {
    super(`${path}: ${message}`);
    this.name = "ContractValidationError";
    this.path = path;
  }
}

type JsonObject = Record<string, unknown>;

const ERROR_CODES = new Set([
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
]);
const WARNING_CODES = new Set([
  "OPENAI_NOT_CONFIGURED",
  "OPENAI_UNAVAILABLE",
  "CURRENT_SNAPSHOT_INVENTORY_CONTEXT",
  "CURRENT_CONTEXT_STALENESS_HIGH",
  "MANUAL_REVIEW_REQUIRED",
  "RULE_VIOLATION_REVIEW",
  "MODEL_IMPLIED_SCENARIO",
  "OBSERVED_DATA_NOT_AVAILABLE",
  "COARSE_GRID_VALUE_WARNING",
  "RESPONSE_PARTIAL",
]);
const CHART_AXIS_FIELDS = new Set(["candidate_price", "scenario", "final_action"]);
const CHART_SERIES_FIELDS = new Set([
  "candidate_price",
  "purchase_probability",
  "expected_quantity_if_purchase",
  "expected_units",
  "expected_revenue",
  "expected_gross_profit",
  "candidate_margin_pct",
  "price_change_percentage",
]);
const CHART_SOURCE_TOOLS = new Set([
  "get_pricing_recommendation",
  "explain_pricing_recommendation",
  "simulate_price",
  "compare_price_scenarios",
  "search_recommendations",
  "get_business_rule_details",
  "get_current_inventory_insight",
]);
const ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const REQUEST_ID_PATTERN = /^req_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const SENSITIVE_PATTERN = /(OPENAI_API_KEY|sk-[A-Za-z0-9_-]{12,}|BEGIN (?:RSA |EC )?PRIVATE KEY|system prompt|chain[- ]of[- ]thought|hidden reasoning)/i;

function object(value: unknown, path: string): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ContractValidationError("expected an object", path);
  }
  return value as JsonObject;
}

function exactKeys(value: JsonObject, allowed: readonly string[], path: string): void {
  const allowedSet = new Set(allowed);
  for (const key of Object.keys(value)) {
    if (!allowedSet.has(key)) {
      throw new ContractValidationError(`unknown property ${JSON.stringify(key)}`, path);
    }
  }
}

function required(value: JsonObject, keys: readonly string[], path: string): void {
  for (const key of keys) {
    if (!(key in value)) {
      throw new ContractValidationError(`missing required property ${JSON.stringify(key)}`, path);
    }
  }
}

function stringValue(value: unknown, path: string, min = 0, max = Number.POSITIVE_INFINITY): string {
  if (typeof value !== "string" || value.length < min || value.length > max) {
    throw new ContractValidationError("expected a bounded string", path);
  }
  return value;
}

function finiteNumber(value: unknown, path: string, minimum?: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || (minimum !== undefined && value < minimum)) {
    throw new ContractValidationError("expected a finite number in range", path);
  }
  return value;
}

function nullableNumber(value: unknown, path: string): number | null {
  return value === null ? null : finiteNumber(value, path);
}

function optionalNumber(value: unknown, path: string): number | null | undefined {
  return value === undefined ? undefined : nullableNumber(value, path);
}

function optionalString(value: unknown, path: string, max = 500): string | null | undefined {
  return value === undefined || value === null ? value : stringValue(value, path, 0, max);
}

function arrayValue(value: unknown, path: string, max: number): unknown[] {
  if (!Array.isArray(value) || value.length > max) {
    throw new ContractValidationError(`expected an array with at most ${max} items`, path);
  }
  return value;
}

function enumValue<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    throw new ContractValidationError(`expected one of ${allowed.join(", ")}`, path);
  }
  return value as T;
}

function safeIdentifier(value: unknown, path: string): string {
  const text = stringValue(value, path, 1, 128);
  if (!ID_PATTERN.test(text)) {
    throw new ContractValidationError("invalid identifier", path);
  }
  return text;
}

function requestId(value: unknown, path: string): string {
  const text = stringValue(value, path, 1, 64);
  if (!REQUEST_ID_PATTERN.test(text)) {
    throw new ContractValidationError("invalid request id", path);
  }
  return text;
}

function assertNoSensitiveText(value: string, path: string): void {
  if (SENSITIVE_PATTERN.test(value)) {
    throw new ContractValidationError("sensitive or hidden-reasoning content is not renderable", path);
  }
}

function scanSensitiveStrings(value: unknown, path: string): void {
  if (typeof value === "string") {
    assertNoSensitiveText(value, path);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => scanSensitiveStrings(item, `${path}[${index}]`));
    return;
  }
  if (typeof value === "object" && value !== null) {
    Object.entries(value).forEach(([key, item]) => scanSensitiveStrings(item, `${path}.${key}`));
  }
}

function validateErrorDetail(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, ["code", "message", "field", "retryable"], path);
  required(item, ["code", "message", "retryable"], path);
  if (!ERROR_CODES.has(stringValue(item.code, `${path}.code`))) {
    throw new ContractValidationError("unknown error code", `${path}.code`);
  }
  const message = stringValue(item.message, `${path}.message`, 1, 500);
  assertNoSensitiveText(message, `${path}.message`);
  if (item.field !== undefined && !/^[A-Za-z0-9_.-]{1,80}$/.test(stringValue(item.field, `${path}.field`))) {
    throw new ContractValidationError("invalid error field", `${path}.field`);
  }
  if (typeof item.retryable !== "boolean") {
    throw new ContractValidationError("expected boolean", `${path}.retryable`);
  }
}

function validateWarning(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, ["code", "message", "severity"], path);
  required(item, ["code", "message", "severity"], path);
  if (!WARNING_CODES.has(stringValue(item.code, `${path}.code`))) {
    throw new ContractValidationError("unknown warning code", `${path}.code`);
  }
  const message = stringValue(item.message, `${path}.message`, 1, 500);
  assertNoSensitiveText(message, `${path}.message`);
  enumValue(item.severity, ["info", "notice", "warning"], `${path}.severity`);
}

function validateToolTrace(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, ["tool_name", "status", "record_count", "error_code"], path);
  required(item, ["tool_name", "status", "record_count"], path);
  enumValue(item.tool_name, TOOL_NAMES, `${path}.tool_name`);
  enumValue(item.status, ["called", "skipped", "failed"], `${path}.status`);
  const recordCount = finiteNumber(item.record_count, `${path}.record_count`, 0);
  if (!Number.isInteger(recordCount) || recordCount > 100) {
    throw new ContractValidationError("record_count must be an integer <= 100", `${path}.record_count`);
  }
  if (item.error_code !== undefined) {
    stringValue(item.error_code, `${path}.error_code`, 1, 80);
  }
}

function validateRecommendation(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "source_tool", "decision_id", "product_id", "store_id", "channel", "category_id", "decision_time", "current_price",
    "model_optimal_candidate_price", "final_recommended_price", "final_action", "expected_units", "expected_revenue", "expected_gross_profit",
    "pricing_rule_id", "rule_name", "promotion_action", "markdown_action", "manual_review_required", "reason_codes", "warnings",
  ], path);
  required(item, ["source_tool", "decision_id", "current_price", "final_action", "expected_units", "expected_revenue", "expected_gross_profit", "manual_review_required", "reason_codes", "warnings"], path);
  if (item.source_tool !== "get_pricing_recommendation") throw new ContractValidationError("wrong source tool", `${path}.source_tool`);
  safeIdentifier(item.decision_id, `${path}.decision_id`);
  for (const key of ["product_id", "store_id", "channel", "category_id", "decision_time", "pricing_rule_id", "rule_name", "promotion_action", "markdown_action"]) optionalString(item[key], `${path}.${key}`);
  finiteNumber(item.current_price, `${path}.current_price`, Number.MIN_VALUE);
  for (const key of ["model_optimal_candidate_price", "final_recommended_price", "expected_units", "expected_revenue", "expected_gross_profit"]) optionalNumber(item[key], `${path}.${key}`);
  stringValue(item.final_action, `${path}.final_action`, 1, 80);
  if (typeof item.manual_review_required !== "boolean") throw new ContractValidationError("expected boolean", `${path}.manual_review_required`);
  for (const key of ["reason_codes", "warnings"]) {
    const codes = arrayValue(item[key], `${path}.${key}`, key === "reason_codes" ? 30 : 20);
    for (const [index, code] of codes.entries()) stringValue(code, `${path}.${key}[${index}]`, 1, 80);
  }
}

function validateScenario(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, ["source_tool", "scenario", "candidate_price", "purchase_probability", "expected_quantity_if_purchase", "expected_units", "expected_revenue", "expected_gross_profit", "candidate_margin_pct", "within_model_support", "business_rule_compliance", "rule_violations", "model_implied"], path);
  required(item, ["source_tool", "scenario", "candidate_price", "model_implied"], path);
  enumValue(item.source_tool, ["simulate_price", "compare_price_scenarios"], `${path}.source_tool`);
  stringValue(item.scenario, `${path}.scenario`, 1, 100);
  nullableNumber(item.candidate_price, `${path}.candidate_price`);
  for (const key of ["purchase_probability", "expected_quantity_if_purchase", "expected_units", "expected_revenue", "expected_gross_profit", "candidate_margin_pct"]) optionalNumber(item[key], `${path}.${key}`);
  for (const key of ["within_model_support", "business_rule_compliance"]) {
    if (item[key] !== undefined && item[key] !== null && typeof item[key] !== "boolean") throw new ContractValidationError("expected boolean or null", `${path}.${key}`);
  }
  if (item.rule_violations !== undefined) {
    const violations = arrayValue(item.rule_violations, `${path}.rule_violations`, 30);
    for (const [index, code] of violations.entries()) stringValue(code, `${path}.rule_violations[${index}]`, 1, 80);
  }
  if (typeof item.model_implied !== "boolean") throw new ContractValidationError("expected boolean", `${path}.model_implied`);
}

function validateChart(value: unknown, path: string): asserts value is ChartSpec {
  const item = object(value, path);
  exactKeys(item, ["schema_version", "chart_id", "type", "title", "description", "x_axis", "series", "points", "source", "model_implied"], path);
  required(item, ["schema_version", "chart_id", "type", "title", "description", "x_axis", "series", "points", "source", "model_implied"], path);
  if (item.schema_version !== CHART_SCHEMA) throw new ContractValidationError("wrong chart schema version", `${path}.schema_version`);
  if (!/^chart_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(stringValue(item.chart_id, `${path}.chart_id`))) throw new ContractValidationError("invalid chart id", `${path}.chart_id`);
  const type = enumValue(item.type, ["line", "bar"], `${path}.type`);
  stringValue(item.title, `${path}.title`, 1, 120);
  const description = stringValue(item.description, `${path}.description`, 1, 400);
  assertNoSensitiveText(description, `${path}.description`);
  const axis = object(item.x_axis, `${path}.x_axis`);
  exactKeys(axis, ["field", "label", "value_type", "unit"], `${path}.x_axis`);
  required(axis, ["field", "label", "value_type"], `${path}.x_axis`);
  const axisField = stringValue(axis.field, `${path}.x_axis.field`);
  if (!CHART_AXIS_FIELDS.has(axisField)) throw new ContractValidationError("unsupported x-axis field", `${path}.x_axis.field`);
  if (type === "line" && axisField !== "candidate_price") throw new ContractValidationError("line charts must use candidate_price", `${path}.x_axis.field`);
  if (type === "bar" && axisField === "candidate_price") throw new ContractValidationError("bar charts must use scenario or final_action", `${path}.x_axis.field`);
  enumValue(axis.value_type, ["number", "string"], `${path}.x_axis.value_type`);
  if (axis.unit !== undefined) enumValue(axis.unit, ["none", "currency", "count", "percentage"], `${path}.x_axis.unit`);
  const series = arrayValue(item.series, `${path}.series`, 3);
  if (series.length < 1) throw new ContractValidationError("at least one series is required", `${path}.series`);
  const declared = new Set<string>();
  for (const [index, rawSeries] of series.entries()) {
    const seriesItem = object(rawSeries, `${path}.series[${index}]`);
    exactKeys(seriesItem, ["field", "label", "unit", "color"], `${path}.series[${index}]`);
    required(seriesItem, ["field", "label", "unit"], `${path}.series[${index}]`);
    const field = stringValue(seriesItem.field, `${path}.series[${index}].field`);
    if (!CHART_SERIES_FIELDS.has(field) || declared.has(field)) throw new ContractValidationError("unsupported or duplicate series field", `${path}.series[${index}].field`);
    declared.add(field);
    stringValue(seriesItem.label, `${path}.series[${index}].label`, 1, 80);
    enumValue(seriesItem.unit, ["number", "currency", "count", "percentage"], `${path}.series[${index}].unit`);
    if (seriesItem.color !== undefined && !/^#[0-9A-Fa-f]{6}$/.test(stringValue(seriesItem.color, `${path}.series[${index}].color`))) throw new ContractValidationError("invalid series color", `${path}.series[${index}].color`);
  }
  const points = arrayValue(item.points, `${path}.points`, 200);
  if (points.length < 1) throw new ContractValidationError("at least one point is required", `${path}.points`);
  for (const [index, rawPoint] of points.entries()) {
    const point = object(rawPoint, `${path}.points[${index}]`);
    exactKeys(point, ["x", "values"], `${path}.points[${index}]`);
    required(point, ["x", "values"], `${path}.points[${index}]`);
    if (typeof point.x !== "string" && typeof point.x !== "number") throw new ContractValidationError("x must be a string or number", `${path}.points[${index}].x`);
    if (typeof point.x === "number" && !Number.isFinite(point.x)) throw new ContractValidationError("x must be finite", `${path}.points[${index}].x`);
    const values = arrayValue(point.values, `${path}.points[${index}].values`, 3);
    if (values.length < 1) throw new ContractValidationError("point values cannot be empty", `${path}.points[${index}].values`);
    for (const [valueIndex, rawValue] of values.entries()) {
      const pointValue = object(rawValue, `${path}.points[${index}].values[${valueIndex}]`);
      exactKeys(pointValue, ["field", "value"], `${path}.points[${index}].values[${valueIndex}]`);
      required(pointValue, ["field", "value"], `${path}.points[${index}].values[${valueIndex}]`);
      const field = stringValue(pointValue.field, `${path}.points[${index}].values[${valueIndex}].field`);
      if (!declared.has(field)) throw new ContractValidationError("point field is not declared by a series", `${path}.points[${index}].values[${valueIndex}].field`);
      nullableNumber(pointValue.value, `${path}.points[${index}].values[${valueIndex}].value`);
    }
  }
  const source = object(item.source, `${path}.source`);
  exactKeys(source, ["tool_name", "record_path", "data_status"], `${path}.source`);
  required(source, ["tool_name", "record_path", "data_status"], `${path}.source`);
  const sourceTool = stringValue(source.tool_name, `${path}.source.tool_name`);
  if (!CHART_SOURCE_TOOLS.has(sourceTool)) throw new ContractValidationError("chart source tool is not allowlisted", `${path}.source.tool_name`);
  if (!/^[A-Za-z0-9_.[\]-]{1,160}$/.test(stringValue(source.record_path, `${path}.source.record_path`))) throw new ContractValidationError("invalid chart record path", `${path}.source.record_path`);
  enumValue(source.data_status, ["observed", "model_implied", "mixed"], `${path}.source.data_status`);
  if (typeof item.model_implied !== "boolean") throw new ContractValidationError("expected boolean", `${path}.model_implied`);
  if (source.data_status === "model_implied" && item.model_implied !== true) throw new ContractValidationError("model-implied data must be labelled", `${path}.model_implied`);
}

function validateAuthoritative(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, ["numeric_claims_source", "recommendations", "scenario_comparisons", "model_performance", "inventory_insights", "business_rule", "capabilities"], path);
  required(item, ["numeric_claims_source", "recommendations", "scenario_comparisons", "model_performance", "inventory_insights", "business_rule", "capabilities"], path);
  if (item.numeric_claims_source !== "deterministic_local_tools") throw new ContractValidationError("numeric authority must be deterministic local tools", `${path}.numeric_claims_source`);
  for (const [index, recommendation] of arrayValue(item.recommendations, `${path}.recommendations`, 100).entries()) validateRecommendation(recommendation, `${path}.recommendations[${index}]`);
  for (const [index, scenario] of arrayValue(item.scenario_comparisons, `${path}.scenario_comparisons`, 200).entries()) validateScenario(scenario, `${path}.scenario_comparisons[${index}]`);
  if (item.model_performance !== null) {
    const performance = object(item.model_performance, `${path}.model_performance`);
    exactKeys(performance, ["source_tool", "metrics", "business_interpretation", "caveat"], `${path}.model_performance`);
    required(performance, ["source_tool", "metrics", "business_interpretation", "caveat"], `${path}.model_performance`);
    if (performance.source_tool !== "get_model_performance") throw new ContractValidationError("wrong performance source", `${path}.model_performance.source_tool`);
    const metrics = object(performance.metrics, `${path}.model_performance.metrics`);
    const metricKeys = ["roc_auc", "average_precision", "log_loss", "brier_score", "top_decile_lift", "demand_aggregate_error_pct", "revenue_aggregate_error_pct", "gp_aggregate_error_pct"] as const;
    exactKeys(metrics, metricKeys, `${path}.model_performance.metrics`);
    required(metrics, metricKeys, `${path}.model_performance.metrics`);
    for (const key of metricKeys) nullableNumber(metrics[key], `${path}.model_performance.metrics.${key}`);
    const interpretations = arrayValue(performance.business_interpretation, `${path}.model_performance.business_interpretation`, 10);
    for (const [index, statement] of interpretations.entries()) stringValue(statement, `${path}.model_performance.business_interpretation[${index}]`, 1, 500);
    stringValue(performance.caveat, `${path}.model_performance.caveat`, 1, 1000);
  }
  for (const [index, insight] of arrayValue(item.inventory_insights, `${path}.inventory_insights`, 100).entries()) {
    const inventory = object(insight, `${path}.inventory_insights[${index}]`);
    exactKeys(inventory, ["source_tool", "decision_id", "product_id", "store_id", "category_id", "available_qty", "stock_status", "slow_moving", "seasonal", "markdown_action", "final_recommended_price", "final_action", "model_implied_context"], `${path}.inventory_insights[${index}]`);
    required(inventory, ["source_tool", "decision_id", "available_qty", "stock_status", "slow_moving", "seasonal", "final_action", "model_implied_context"], `${path}.inventory_insights[${index}]`);
    if (inventory.source_tool !== "get_current_inventory_insight") throw new ContractValidationError("wrong inventory source", `${path}.inventory_insights[${index}].source_tool`);
    safeIdentifier(inventory.decision_id, `${path}.inventory_insights[${index}].decision_id`);
    for (const key of ["product_id", "store_id", "category_id", "stock_status", "markdown_action"]) optionalString(inventory[key], `${path}.inventory_insights[${index}].${key}`);
    nullableNumber(inventory.available_qty, `${path}.inventory_insights[${index}].available_qty`);
    optionalNumber(inventory.final_recommended_price, `${path}.inventory_insights[${index}].final_recommended_price`);
    for (const key of ["slow_moving", "seasonal"]) if (typeof inventory[key] !== "boolean") throw new ContractValidationError("expected boolean", `${path}.inventory_insights[${index}].${key}`);
    stringValue(inventory.final_action, `${path}.inventory_insights[${index}].final_action`, 1, 80);
    if (inventory.model_implied_context !== false) throw new ContractValidationError("inventory context must be observed", `${path}.inventory_insights[${index}].model_implied_context`);
  }
  if (item.business_rule !== null) {
    const rule = object(item.business_rule, `${path}.business_rule`);
    exactKeys(rule, ["source_tool", "pricing_rule_id", "rule_name", "priority", "specificity", "min_price", "max_price", "min_margin_pct", "max_discount_pct", "max_price_change_pct", "final_price_compliant"], `${path}.business_rule`);
    required(rule, ["source_tool", "pricing_rule_id", "rule_name", "final_price_compliant"], `${path}.business_rule`);
    if (rule.source_tool !== "get_business_rule_details") throw new ContractValidationError("wrong rule source", `${path}.business_rule.source_tool`);
    optionalString(rule.pricing_rule_id, `${path}.business_rule.pricing_rule_id`);
    optionalString(rule.rule_name, `${path}.business_rule.rule_name`);
    for (const key of ["priority", "specificity", "min_price", "max_price", "min_margin_pct", "max_discount_pct", "max_price_change_pct"]) optionalNumber(rule[key], `${path}.business_rule.${key}`);
    if (typeof rule.final_price_compliant !== "boolean") throw new ContractValidationError("expected boolean", `${path}.business_rule.final_price_compliant`);
  }
  if (item.capabilities !== null) {
    const capabilities = object(item.capabilities, `${path}.capabilities`);
    exactKeys(capabilities, ["source_tool", "supported_questions", "use_case", "business_question"], `${path}.capabilities`);
    required(capabilities, ["source_tool", "supported_questions"], `${path}.capabilities`);
    enumValue(capabilities.source_tool, ["get_use_case_summary", "get_agent_capabilities"], `${path}.capabilities.source_tool`);
    const questions = arrayValue(capabilities.supported_questions, `${path}.capabilities.supported_questions`, 20);
    if (questions.length < 1) throw new ContractValidationError("at least one supported question is required", `${path}.capabilities.supported_questions`);
    for (const [index, question] of questions.entries()) stringValue(question, `${path}.capabilities.supported_questions[${index}]`, 1, 300);
    optionalString(capabilities.use_case, `${path}.capabilities.use_case`);
    optionalString(capabilities.business_question, `${path}.capabilities.business_question`);
  }
}

export function validateResponse(value: unknown): PricingChatResponse {
  const item = object(value, "$response");
  exactKeys(item, ["schema_version", "request_id", "status", "answer", "answer_source", "authoritative", "charts", "tools_used", "tool_trace", "warnings", "errors", "metadata"], "$response");
  required(item, ["schema_version", "request_id", "status", "answer", "answer_source", "authoritative", "charts", "tools_used", "tool_trace", "warnings", "errors", "metadata"], "$response");
  if (item.schema_version !== RESPONSE_SCHEMA) throw new ContractValidationError("wrong response schema version", "$response.schema_version");
  requestId(item.request_id, "$response.request_id");
  enumValue(item.status, ["completed", "partial", "rejected", "failed"], "$response.status");
  const answer = stringValue(item.answer, "$response.answer", 0, 12000);
  assertNoSensitiveText(answer, "$response.answer");
  enumValue(item.answer_source, ["agent", "deterministic_fallback", "policy"], "$response.answer_source");
  validateAuthoritative(item.authoritative, "$response.authoritative");
  const charts = arrayValue(item.charts, "$response.charts", 4);
  for (const [index, chart] of charts.entries()) validateChart(chart, `$response.charts[${index}]`);
  const toolsUsed = arrayValue(item.tools_used, "$response.tools_used", 10);
  const uniqueTools = new Set<string>();
  for (const [index, tool] of toolsUsed.entries()) {
    const name = enumValue(tool, TOOL_NAMES, `$response.tools_used[${index}]`);
    if (uniqueTools.has(name)) throw new ContractValidationError("tools_used must be unique", "$response.tools_used");
    uniqueTools.add(name);
  }
  const traces = arrayValue(item.tool_trace, "$response.tool_trace", 20);
  for (const [index, trace] of traces.entries()) validateToolTrace(trace, `$response.tool_trace[${index}]`);
  const warnings = arrayValue(item.warnings, "$response.warnings", 20);
  for (const [index, warning] of warnings.entries()) validateWarning(warning, `$response.warnings[${index}]`);
  const errors = arrayValue(item.errors, "$response.errors", 20);
  for (const [index, error] of errors.entries()) validateErrorDetail(error, `$response.errors[${index}]`);
  const metadata = object(item.metadata, "$response.metadata");
  exactKeys(metadata, ["runtime", "agent_available", "contract_version", "duration_ms"], "$response.metadata");
  required(metadata, ["runtime", "agent_available", "contract_version"], "$response.metadata");
  if (metadata.runtime !== "local" || metadata.contract_version !== "1" || typeof metadata.agent_available !== "boolean") throw new ContractValidationError("invalid response metadata", "$response.metadata");
  if (metadata.duration_ms !== undefined) finiteNumber(metadata.duration_ms, "$response.metadata.duration_ms", 0);
  for (const [index, chart] of charts.entries()) {
    const chartObject = chart as JsonObject;
    const source = chartObject.source as JsonObject;
    if (!uniqueTools.has(String(source.tool_name))) throw new ContractValidationError("chart source tool must be listed in tools_used", `$response.charts[${index}].source.tool_name`);
  }
  scanSensitiveStrings(item, "$response");
  return value as PricingChatResponse;
}

export function validateErrorEnvelope(value: unknown): PricingChatError {
  const item = object(value, "$error");
  exactKeys(item, ["schema_version", "request_id", "status", "error", "warnings"], "$error");
  required(item, ["schema_version", "request_id", "status", "error"], "$error");
  if (item.schema_version !== ERROR_SCHEMA || item.status !== "error") throw new ContractValidationError("invalid error envelope constants", "$error");
  requestId(item.request_id, "$error.request_id");
  validateErrorDetail(item.error, "$error.error");
  if (item.warnings !== undefined) for (const [index, warning] of arrayValue(item.warnings, "$error.warnings", 20).entries()) validateWarning(warning, `$error.warnings[${index}]`);
  return value as PricingChatError;
}

export function validateHealth(value: unknown): HealthResponse {
  const item = object(value, "$health");
  exactKeys(item, ["status", "runtime", "contract_version", "agent_available", "artifacts_integrity"], "$health");
  required(item, ["status", "runtime", "contract_version", "agent_available", "artifacts_integrity"], "$health");
  enumValue(item.status, ["starting", "ready", "blocked"], "$health.status");
  if (item.runtime !== "local" || item.contract_version !== "1" || typeof item.agent_available !== "boolean") throw new ContractValidationError("invalid health constants", "$health");
  enumValue(item.artifacts_integrity, ["pass", "blocked", "unknown"], "$health.artifacts_integrity");
  return value as HealthResponse;
}

export function validateRequest(value: PricingChatRequest): PricingChatRequest {
  const item = object(value, "$request");
  exactKeys(item, ["schema_version", "request_id", "message", "conversation", "context", "options"], "$request");
  required(item, ["schema_version", "message"], "$request");
  if (item.schema_version !== REQUEST_SCHEMA) throw new ContractValidationError("wrong request schema version", "$request.schema_version");
  if (item.request_id !== undefined) requestId(item.request_id, "$request.request_id");
  const message = stringValue(item.message, "$request.message", 1, 4000);
  assertNoSensitiveText(message, "$request.message");
  if (item.conversation !== undefined) {
    const conversation = arrayValue(item.conversation, "$request.conversation", 20);
    for (const [index, rawMessage] of conversation.entries()) {
      const chatMessage = object(rawMessage, `$request.conversation[${index}]`);
      exactKeys(chatMessage, ["role", "content"], `$request.conversation[${index}]`);
      required(chatMessage, ["role", "content"], `$request.conversation[${index}]`);
      enumValue(chatMessage.role, ["user", "assistant"], `$request.conversation[${index}].role`);
      const content = stringValue(chatMessage.content, `$request.conversation[${index}].content`, 1, 4000);
      assertNoSensitiveText(content, `$request.conversation[${index}].content`);
    }
  }
  if (item.context !== undefined) {
    const context = object(item.context, "$request.context");
    exactKeys(context, ["pricing_decision_id", "product_id", "store_id", "category_id", "channel", "split"], "$request.context");
    for (const key of ["pricing_decision_id", "product_id", "store_id", "category_id"]) if (context[key] !== undefined) safeIdentifier(context[key], `$request.context.${key}`);
    if (context.channel !== undefined) stringValue(context.channel, "$request.context.channel", 1, 64);
    if (context.split !== undefined) enumValue(context.split, ["validation", "current"], "$request.context.split");
  }
  if (item.options !== undefined) {
    const options = object(item.options, "$request.options");
    exactKeys(options, ["stream", "include_raw_json", "max_charts"], "$request.options");
    if (options.stream !== undefined && typeof options.stream !== "boolean") throw new ContractValidationError("expected boolean", "$request.options.stream");
    if (options.include_raw_json !== undefined && typeof options.include_raw_json !== "boolean") throw new ContractValidationError("expected boolean", "$request.options.include_raw_json");
    if (options.max_charts !== undefined && (typeof options.max_charts !== "number" || !Number.isInteger(options.max_charts) || options.max_charts < 0 || options.max_charts > 4)) throw new ContractValidationError("max_charts must be an integer from 0 to 4", "$request.options.max_charts");
  }
  return value;
}

export function validateSseEvent(value: unknown, expectedRequestId?: string): SseEvent {
  const item = object(value, "$sse");
  exactKeys(item, ["schema_version", "event", "request_id", "sequence", "payload"], "$sse");
  required(item, ["schema_version", "event", "request_id", "sequence", "payload"], "$sse");
  if (item.schema_version !== SSE_SCHEMA) throw new ContractValidationError("wrong SSE schema version", "$sse.schema_version");
  const id = requestId(item.request_id, "$sse.request_id");
  if (expectedRequestId !== undefined && id !== expectedRequestId) throw new ContractValidationError("event request id does not match stream", "$sse.request_id");
  if (typeof item.sequence !== "number" || !Number.isInteger(item.sequence) || item.sequence < 0) throw new ContractValidationError("sequence must be a non-negative integer", "$sse.sequence");
  const payload = object(item.payload, "$sse.payload");
  switch (item.event) {
    case "chat.started":
      exactKeys(payload, ["status"], "$sse.payload");
      if (payload.status !== "started") throw new ContractValidationError("invalid started payload", "$sse.payload.status");
      break;
    case "chat.tool":
      exactKeys(payload, ["tool_name", "status", "record_count", "error_code"], "$sse.payload");
      required(payload, ["tool_name", "status"], "$sse.payload");
      enumValue(payload.tool_name, TOOL_NAMES, "$sse.payload.tool_name");
      enumValue(payload.status, ["started", "completed", "failed"], "$sse.payload.status");
      if (payload.record_count !== undefined) finiteNumber(payload.record_count, "$sse.payload.record_count", 0);
      if (payload.error_code !== undefined) stringValue(payload.error_code, "$sse.payload.error_code", 1, 80);
      break;
    case "chat.delta": {
      exactKeys(payload, ["text"], "$sse.payload");
      const text = stringValue(payload.text, "$sse.payload.text", 1, 2000);
      assertNoSensitiveText(text, "$sse.payload.text");
      if (/\d/.test(text)) throw new ContractValidationError("numeric deltas are not renderable", "$sse.payload.text");
      break;
    }
    case "chat.completed":
      exactKeys(payload, ["response"], "$sse.payload");
      required(payload, ["response"], "$sse.payload");
      validateResponse(payload.response);
      break;
    case "chat.error":
      exactKeys(payload, ["error"], "$sse.payload");
      required(payload, ["error"], "$sse.payload");
      validateErrorDetail(payload.error, "$sse.payload.error");
      break;
    default:
      throw new ContractValidationError("unsupported SSE event", "$sse.event");
  }
  return value as SseEvent;
}

export function containsSensitiveText(value: string): boolean {
  return SENSITIVE_PATTERN.test(value);
}
