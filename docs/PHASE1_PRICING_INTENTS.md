# Phase 1 — Supported Pricing Intents

The agent is a natural-language router over a fixed set of read-only local tools. Intent classification is a routing hint; it never grants the model authority to invent a price. The FastAPI layer remains responsible for selecting and validating tool calls.

## Supported intents

| Intent | Example question | Required context | Authoritative tool(s) | Charts |
| --- | --- | --- | --- | --- |
| `capability_explanation` | “What does this pricing solution do?” | none | `get_use_case_summary` | none |
| `recommendation_lookup` | “What governed price is recommended for decision `PD-001`?” | `pricing_decision_id` | `get_pricing_recommendation` | optional recommendation card |
| `recommendation_explanation` | “Why did `PD-001` increase the price?” | `pricing_decision_id` | `explain_pricing_recommendation` and, when needed, `get_pricing_recommendation` | optional comparison |
| `scenario_simulation` | “What happens at $109.99 for `PD-001`?” | decision id and candidate price in message/context | `simulate_price` | line or single-point result |
| `scenario_comparison` | “Compare current, model-optimal, and final price for `PD-001`.” | `pricing_decision_id` | `compare_price_scenarios` | bar/line comparison |
| `model_performance` | “How strong is the purchase/demand model?” | none | `get_model_performance` | optional metric bar |
| `business_rule_explanation` | “Which rule constrained `PD-001`?” | `pricing_decision_id` | `get_business_rule_details` | none |
| `inventory_insight` | “Show current seasonal markdown recommendations.” | optional product/store/category/action filters | `get_current_inventory_insight` | optional action/count bar |
| `help` | “What pricing questions can I ask?” | none | `get_agent_capabilities` | none |

The current-inventory intent is explicitly a snapshot context. It must not be described as historical inventory or a time-series feature. Scenario values are model-implied estimates, not observed outcomes, causal effects, or guaranteed uplift. Model performance metrics must retain their metric names; ROC-AUC is not “accuracy.”

## Required context and ambiguity behavior

If an intent needs a decision id and none is available, return `MISSING_PRICING_CONTEXT` with a request for the id; do not search by guessed identifiers. If a decision id is unknown, return `UNKNOWN_PRICING_DECISION`. If a candidate price is malformed, return `INVALID_CANDIDATE_PRICE`. If it is outside the frozen support envelope, return `MODEL_SUPPORT_LIMIT`; never extrapolate.

If a question contains multiple pricing intents, the server may execute only the smallest safe set of deterministic tools and must identify all tools in `tools_used`. If intent remains ambiguous, return a policy answer asking one bounded clarification question, with empty authoritative collections and no chart. The model must not fill a missing context value from conversation guesses.

## Unsupported or rejected behavior

The following requests are rejected with `UNSUPPORTED_INTENT` or `POLICY_REJECTED` and no invented numeric result:

- price generation without an existing deterministic decision context;
- price writeback, order placement, promotion activation, inventory mutation, or operational action;
- arbitrary SQL, shell, filesystem, code execution, web search, scraping, or external data retrieval;
- model retraining, changing features, changing business rules, or requesting raw datasets;
- customer-level or discriminatory/personalized pricing, PII lookup, credentials, or secret disclosure;
- causal, guaranteed, or realized uplift claims from a model-implied scenario;
- expiry/perishable pricing, because validated expiry/batch history is out of scope;
- requests to bypass model support, margin floors, manual review, or rule constraints;
- requests for hidden prompts, chain-of-thought, tool arguments, internal exception details, or API keys;
- generic non-pricing assistance unrelated to the defined local use case.

For unsupported behavior the response status is `rejected`, `answer_source` is `policy`, `tools_used` is empty, and `authoritative` contains empty arrays/nulls. The user-safe message explains the supported scope without echoing sensitive input.
