# Phase 1 — Application Contract & Local Architecture

Status: accepted foundation for the React/FastAPI implementation track.

## Scope and non-goals

The application is a local-only, single-screen conversational pricing client. A React browser presents a chat, charts, warnings, and the complete validated JSON response. A FastAPI process owns request validation, access to the frozen pricing services, OpenAI orchestration, response normalization, and the only OpenAI credential. There is no authentication, hosting, deployment, writeback, database mutation, or persistent conversation store.

Phase 1 defines the contracts and boundaries. Phase 2 will implement FastAPI and the agent adapter; Phase 3 will implement the React components and chart renderer. This phase does not retrain models or alter Phase 1–10 evidence.

## Authoritative data flow

```text
Browser (React, presentation only)
  │  JSON request / JSON response or SSE events
  │  localhost:5173 → 127.0.0.1:8000
  ▼
FastAPI boundary
  ├─ validate request schema, size, identifiers, and intent
  ├─ assign request_id and enforce local CORS
  ├─ check frozen artifact integrity at startup
  ├─ call deterministic local services (authoritative numbers)
  ├─ send only minimized, allowlisted context to OpenAI (optional)
  ├─ validate agent output and build chart specs from tool data
  └─ normalize one response contract; omit internal reasoning
       │
       ├──────────────► OpenAI Agents SDK (optional external call)
       │                 OPENAI_API_KEY exists only here
       │
       └──────────────► frozen local artifacts/services
                         Phase 4–8 models, economics, rules, evidence
```

The trust boundary is the FastAPI process. React cannot read model files, invoke Python services, call OpenAI, choose a price, or provide executable chart code. OpenAI cannot access the filesystem, SQL, shell, web search, arbitrary tools, or secrets. Tool output is authoritative for every numeric pricing claim; the model supplies concise narrative only.

## Trust-boundary rules

| Boundary | Permitted | Explicitly prohibited |
| --- | --- | --- |
| React → FastAPI | Contract-valid message, bounded in-memory context, optional identifiers, UI options | API key, raw model artifacts, arbitrary SQL/code, local-storage persistence |
| FastAPI → local services | Allowlisted IDs and filters; read-only service calls | Retraining, artifact mutation, price writeback, outcome/PII projections |
| FastAPI → OpenAI | User question plus compact allowlisted tool results and policy instructions | API key in prompt, full datasets, PII, outcomes, chain-of-thought, shell/files/web access |
| FastAPI → React | Validated answer, typed authoritative records, safe chart specs, warnings/errors, tool names | Secrets, raw prompts, hidden reasoning, unvalidated model numbers, executable chart code |

The server must redact or reject a request that contains credentials, SQL, shell instructions, or attempts to override tool authority. It must never echo the rejected secret or prompt text in an error, log, fixture, or artifact.

## API and lifecycle decisions

The machine-readable source of truth is `contracts/application/`. The synchronous endpoint is `POST /api/v1/pricing/chat`; the optional streaming endpoint is `POST /api/v1/pricing/chat/stream` and emits `pricing.chat.sse.v1` JSON data payloads. Both accept the same request schema. The health endpoint is `GET /api/v1/healthz` and reports only local readiness state, never configuration values.

FastAPI startup performs a frozen-artifact integrity check and constructs the read-only registry/services. A failed check sets readiness to blocked and prevents recommendation or simulation tools from running. Shutdown closes the OpenAI client and releases model/service resources. The server does not persist request bodies, conversations, prompts, tool arguments, or responses. A request body is bounded to 64 KiB; `message` is at most 4,000 characters, conversation context is at most 20 messages, and a response contains at most four charts.

Local CORS is an explicit allowlist of `http://localhost:5173` and `http://127.0.0.1:5173`, with `GET` and `POST`, `Content-Type` and `Accept` headers, and credentials disabled. Wildcard origins and credentialed CORS are not allowed. The server binds to loopback by default (`127.0.0.1:8000`).

## Response authority model

`answer` is presentation text and is labelled with `answer_source`. `authoritative` is a typed object containing only normalized records from named deterministic tools. `charts` is built by FastAPI from those records and is separately schema-validated. `tools_used` and `tool_trace` expose names and status only; they do not expose arguments or hidden reasoning. `warnings` and `errors` are stable codes with user-safe messages. No response field represents chain-of-thought.

The response is valid even when the agent is unavailable. In that case `answer_source` is `deterministic_fallback` or `policy`, `metadata.agent_available` is false, and the response contains `OPENAI_NOT_CONFIGURED` or `OPENAI_UNAVAILABLE`. If a deterministic tool fails, the server returns no replacement number: it records a typed error and either keeps unrelated validated records or marks the response `failed`.

## Phase 2/3 handoff

Phase 2 must implement the endpoint and normalization layer against these schemas, preserve existing `src/ai_agent` tool names, and add contract tests before connecting a live key. Phase 3 must render only the `charts` allowlist, show `answer` separately from the JSON response panel, preserve the response in React memory only, and treat every `errors`/`warnings` code as user-visible state. Any contract change requires a new schema version and an ADR or amendment; silent shape changes are not permitted.
