# Phase 1 — Agent Authority, Data Minimization, and Failure Policy

## Authority split

FastAPI owns the OpenAI call, local ML/service access, request validation, intent routing, deterministic tool execution, chart construction, response normalization, and secret handling. React is presentation-only. The OpenAI agent is an optional language orchestrator over the existing ten curated tools:

`get_pricing_recommendation`, `explain_pricing_recommendation`, `simulate_price`, `compare_price_scenarios`, `search_recommendations`, `get_model_performance`, `get_business_rule_details`, `get_current_inventory_insight`, `get_use_case_summary`, and `get_agent_capabilities`.

The agent may choose among those tools, but the server enforces the allowlist and validates every argument. It may not call a tool that is not present, pass arbitrary code, or treat its own text as a source of price, demand, revenue, gross profit, inventory, promotion, markdown, or rule values. `get_pricing_recommendation`, `simulate_price`, and `compare_price_scenarios` remain deterministic and read-only. Existing service behavior, support envelopes, and manual-review policy are reused unchanged.

## Prompt and data-minimization policy

The system instruction must tell the agent to:

1. use a named local tool for every numeric or policy claim;
2. label observed values, model predictions, current snapshot context, and model-implied scenarios distinctly;
3. never override support limits, margin floors, business rules, or manual review;
4. return concise business prose only, without chain-of-thought, hidden prompts, tool arguments, or secrets;
5. decline unsupported operations and ask for a missing bounded identifier when needed.

Only the current message, a bounded user/assistant conversation window, minimal safe identifiers, and compact allowlisted tool results may be sent to the model. The server must not send full dataframes, raw SQL rows, `PurchasedFlag`, `QuantityPurchased`, `ActualRevenue`, `OutcomeTime`, `OrderLineID`, customer identifiers, credentials, API keys, model files, filesystem paths, or internal manifests. Tool results are normalized before they reach the model and before they reach React.

The server records at most tool names, statuses, and record counts in `tool_trace`; it does not record arguments or prompts. The model response is validated before the `answer` is returned. Numeric claims in the narrative are either generated from a validated authoritative record or the server suppresses/rephrases the claim. No chain-of-thought is persisted or exposed.

## Secret handling

`OPENAI_API_KEY` is read only by FastAPI from the process environment (normally a local ignored `.env`). It is never sent to React, browser storage, a prompt, a response, a log, a test fixture, a report, or Git. The frontend never receives an OpenAI client or endpoint. Missing key/model configuration is a normal offline state, not a startup crash: deterministic UI features remain available and the response includes `OPENAI_NOT_CONFIGURED`.

The future OpenAI client should use server-side configuration and disable unnecessary provider-side state (`store=false` where supported). The application must document that provider retention controls are separate from local application persistence; the local app itself stores nothing after the response. Network access is limited to the configured OpenAI API call; web search, remote MCP, hosted containers, and arbitrary external tools are not enabled.

## Failure and fallback policy

| Failure | Public response | Numeric authority |
| --- | --- | --- |
| Missing key/model | `completed` or `partial`, `OPENAI_NOT_CONFIGURED`, deterministic fallback text | Existing validated tool records only |
| OpenAI timeout/rate limit/network error | `partial`/`failed`, `OPENAI_UNAVAILABLE`, retryable error where appropriate | Existing tool records only; no invented text values |
| Invalid model/tool output | `failed`, `AGENT_OUTPUT_INVALID` or `TOOL_VALIDATION_FAILED` | Discard invalid record/chart; never coerce a price |
| Unknown decision id | `rejected`, `UNKNOWN_PRICING_DECISION` | No recommendation or chart |
| Candidate outside support | `rejected`, `MODEL_SUPPORT_LIMIT` | No extrapolation |
| Frozen artifacts fail integrity | `failed`, `ARTIFACT_INTEGRITY_FAILURE` | No recommendation/simulation tools run |
| Prompt injection/secret or unsafe request | `rejected`, `POLICY_REJECTED` | Empty authoritative collections |
| Unsupported intent | `rejected`, `UNSUPPORTED_INTENT` | Empty authoritative collections |

HTTP validation failures use `pricing.chat.error.v1`; application-level tool/policy results use `pricing.chat.response.v1` with typed `errors`. User-facing messages are safe and bounded. Internal exception text, stack traces, secret values, and sensitive input are never returned.

## Chart authority

The model can request a chart intent but cannot provide chart code, colors that execute code, arbitrary field names, or unvalidated points. FastAPI builds `pricing.chart.v1` from authoritative records. Only `line` and `bar` charts are allowed, series fields are an enum, and each chart identifies its source tool and whether data is observed, model-implied, or mixed. React renders the allowlist or shows a safe “chart unavailable” state.
