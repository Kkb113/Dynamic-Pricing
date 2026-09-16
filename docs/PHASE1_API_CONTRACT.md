# Phase 1 — FastAPI and SSE Contract

## Endpoints

| Method | Path | Request | Success | Failure |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/healthz` | none | `200` readiness object | `503` readiness object |
| `POST` | `/api/v1/pricing/chat` | `pricing.chat.request.v1` | `200` `pricing.chat.response.v1` | `400/413/422` `pricing.chat.error.v1`; `500/503` safe error |
| `POST` | `/api/v1/pricing/chat/stream` | same request; `options.stream` must be true or omitted | `200 text/event-stream` with `pricing.chat.sse.v1` payloads | `400/413/422` JSON error before stream; in-stream `chat.error` after stream start |

All endpoints are under `/api/v1`. The backend creates a server request id matching `^req_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`; a client correlation id may be accepted but cannot replace the server id. The server sets `Cache-Control: no-store`, does not expose provider headers, and does not log request/response bodies.

## Health contract

The health response is intentionally small and secret-free:

```json
{
  "status": "ready",
  "runtime": "local",
  "contract_version": "1",
  "agent_available": false,
  "artifacts_integrity": "pass"
}
```

Allowed status values are `starting`, `ready`, and `blocked`. `blocked` is returned when frozen artifacts fail integrity; it disables recommendation/simulation tools. `agent_available` is a boolean and does not reveal whether a key is present. Phase 2 may add a dedicated health schema before implementation.

## SSE wire format

Each event is standard SSE with an event name and one JSON `data` line. The JSON payload validates against `pricing_chat_sse_event_v1.schema.json`.

```text
event: chat.started
data: {"schema_version":"pricing.chat.sse.v1","event":"chat.started","request_id":"req_demo","sequence":0,"payload":{"status":"started"}}

event: chat.tool
data: {"schema_version":"pricing.chat.sse.v1","event":"chat.tool","request_id":"req_demo","sequence":1,"payload":{"tool_name":"get_pricing_recommendation","status":"completed","record_count":1}}

event: chat.completed
data: {"schema_version":"pricing.chat.sse.v1","event":"chat.completed","request_id":"req_demo","sequence":2,"payload":{"response":{ "...": "pricing.chat.response.v1" }}}
```

The stream starts with `chat.started`, may report tool status, may emit sanitized narrative `chat.delta` fragments, and terminates exactly once with `chat.completed` or `chat.error`. Only `chat.completed` contains authoritative numeric data. A client must validate sequence monotonicity, ignore duplicate/out-of-order events, and stop reading after a terminal event.

## CORS, limits, and lifecycle

- Allowed origins: `http://localhost:5173`, `http://127.0.0.1:5173`.
- Allowed methods: `GET`, `POST`; allowed headers: `Content-Type`, `Accept`.
- Credentials: disabled. Wildcard origin: prohibited.
- Request body: maximum 64 KiB; message: maximum 4,000 characters; conversation: maximum 20 messages.
- Upstream OpenAI timeout: 20 seconds; server request timeout: 30 seconds; chart count: maximum 4.
- No authentication or persistent server session exists in this local product.
- Startup validates frozen artifacts and loads read-only services; shutdown closes clients/resources.
- A missing OpenAI configuration leaves deterministic services available. It never causes a fake answer or an API key to be returned.
