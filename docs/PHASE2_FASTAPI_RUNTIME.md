# Phase 2 — FastAPI ML Tooling & OpenAI Agent

Phase 2 turns the Phase 1 application contract into a runnable local backend. The implementation is under `src/pricing_api/` and exposes only:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/healthz` | loopback readiness and frozen-artifact integrity |
| `POST` | `/api/v1/pricing/chat` | validated JSON pricing response |
| `POST` | `/api/v1/pricing/chat/stream` | validated Server-Sent Events response |

## Runtime ownership

FastAPI owns configuration, `OPENAI_API_KEY`/`OPENAI_MODEL` access, the optional Agents SDK call, local deterministic service access, input validation, chart construction, and response normalization. React remains presentation-only and is not included in Phase 2. The backend has no authentication, persistence, SQL writes, training, hosting, deployment, or price writeback.

Startup creates one read-only `ServiceContainer`. It integrity-checks the accepted Phase 4–8 artifacts and constructs the existing `RecommendationService`, `SimulationService`, and `ModelPerformanceService` once. The container is reused for all requests and is discarded on shutdown. Integrity failure yields a safe blocked health response and prevents pricing claims.

## Authority and agent policy

The ten governed tool names are unchanged:

`get_pricing_recommendation`, `explain_pricing_recommendation`, `simulate_price`, `compare_price_scenarios`, `search_recommendations`, `get_model_performance`, `get_business_rule_details`, `get_current_inventory_insight`, `get_use_case_summary`, and `get_agent_capabilities`.

`GovernedToolset` wraps the existing deterministic service layer; it does not duplicate ML calculations. Inputs and result sizes are bounded, errors are reduced to stable codes, and tool traces contain names/status/counts only. All numeric pricing fields are normalized from tool results and independently validated against `contracts/application/pricing_chat_response_v1.schema.json`. Charts are rebuilt by `charts.py` from those normalized fields; the model cannot submit executable chart code or arbitrary field mappings.

When both environment values are configured and `openai-agents` is available, `OpenAIAgentAdapter` uses the current `Agent`, `Runner`, and `function_tool` pattern. It supplies an allowlisted, bounded context and sets a maximum turn count and timeout. The adapter returns narrative text only. Numeric-looking narrative text is accepted only when its values occur in the authoritative deterministic projection; otherwise deterministic fallback text is used. A missing key/model, SDK absence, timeout, rate limit, provider failure, or invalid output never fabricates a price.

The key is read only by the FastAPI configuration/adapter path. It is not returned, logged, stored in browser state, written to fixtures/evidence, or sent to React. Hidden reasoning, raw tool arguments, and provider headers are never returned.

## Request limits and errors

- loopback bind by default (`127.0.0.1`); non-loopback configuration is rejected;
- CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`, with credentials disabled;
- request bodies are capped at 64 KiB before FastAPI parsing, including chunked requests;
- Pydantic v2 rejects unknown fields and the outbound document is revalidated against the checked-in schema;
- public failures use `pricing.chat.error.v1` with stable error codes and no exception detail.

## SSE behavior

The stream emits `chat.started`, optional `chat.tool` records, a fixed non-numeric `chat.delta` fragment, and exactly one terminal `chat.completed` or `chat.error`. Sequence values begin at zero and increase monotonically. Authoritative numeric values appear only in the validated completed response. Disconnects cancel the generator without producing a second terminal event.

## Local run

```powershell
python -m pip install -e ".[test]"
Copy-Item .env.example .env
# Set OPENAI_API_KEY and OPENAI_MODEL only in the ignored local .env if desired.
$env:PYTHONPATH = "src"
python -m pricing_api
```

The deterministic fallback works with blank `OPENAI_API_KEY` and `OPENAI_MODEL`. Phase 3 can consume the JSON response and SSE contract, render the allowlisted charts, and show the validated response object in its expandable raw-JSON viewer.
