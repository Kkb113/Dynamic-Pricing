# Phase 1 — React Chat, Chart, and JSON Viewer Contract

Phase 3 will implement one React screen. It consumes only `pricing.chat.request.v1`, `pricing.chat.response.v1`, `pricing.chat.error.v1`, and `pricing.chat.sse.v1`. It must not import Python modules, read artifacts, call OpenAI, or persist chat content.

## Component contract

```text
PricingChatPage
├── ChatHeader / ConnectionStatus
├── MessageList
│   └── ChatMessage (user | assistant)
│       ├── AnswerBlock (response.answer only)
│       ├── WarningBanner (response.warnings)
│       ├── ErrorBanner (response.errors)
│       └── ChartRenderer[] (response.charts allowlist)
├── JsonResponsePanel (read-only JSON.stringify(response, 2))
└── ChatComposer (message + optional bounded context)
```

`AnswerBlock` is visibly separate from `AuthoritativeDataSummary`, which may show recommendation/scenario cards sourced from `response.authoritative`. The expandable `JsonResponsePanel` shows the exact validated response object, including `request_id`, schema version, tool names, warnings, errors, and chart specs. It is read-only, escaped, and must not provide an edit or replay action.

## State shape

```ts
type ConnectionState = "idle" | "submitting" | "streaming" | "complete" | "error";

type PricingChatState = {
  messages: ChatMessage[];                 // in-memory only
  connection: ConnectionState;
  activeRequestId: string | null;
  latestResponse: PricingChatResponseV1 | null;
  latestError: PricingChatErrorV1 | null;
  jsonExpanded: boolean;
  draft: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: PricingChatResponseV1;
};
```

The reducer actions are `SUBMIT_STARTED`, `SSE_STARTED`, `SSE_TOOL`, `SSE_DELTA`, `RESPONSE_COMPLETED`, `REQUEST_FAILED`, `TOGGLE_JSON`, and `RESET`. A new request clears only the active error; earlier messages remain in memory for the current tab. Reloading the tab clears the conversation. No `localStorage`, `sessionStorage`, cookies, IndexedDB, analytics payload, or URL query string may contain the message, response, identifiers, or key.

## Rendering rules

- Render `answer` as text/markdown after sanitization; never render raw HTML from the model.
- Render recommendations and scenarios from `authoritative`, not by parsing numbers out of `answer`.
- Render only `charts[].type` values `line` and `bar`; use `x_axis.field`, `series[].field`, and `points` exactly as provided.
- Display `chart.source.data_status` and a “model-implied estimate” label whenever `model_implied` is true or data status is `mixed`.
- Treat every warning and error as user-visible. Do not hide `MANUAL_REVIEW_REQUIRED`, `MODEL_SUPPORT_LIMIT`, or `CURRENT_SNAPSHOT_INVENTORY_CONTEXT`.
- Show request id on the response details/debug affordance, but never show provider headers, prompts, tool arguments, or environment values.
- If schema validation fails in the client, discard the malformed chart/response and show a generic contract error; do not attempt to repair numeric data.

## SSE mapping

`POST /api/v1/pricing/chat/stream` yields `chat.started`, zero or more `chat.tool`, optional sanitized `chat.delta`, then exactly one `chat.completed` or `chat.error`. The final completed event contains the full response and is the only event that may contain validated numeric pricing claims. The client must ignore out-of-order or duplicate sequence numbers and close the stream after the terminal event.
