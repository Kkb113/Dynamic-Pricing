# Phase 3 — React pricing chat

This is the local-only presentation surface for the Phase 2 FastAPI service. It contains one natural-language pricing chat route, backend-authored charts, accessible chart tables, and an expandable raw JSON response viewer.

## Local run

From the repository root, start FastAPI in one terminal:

```powershell
$env:PYTHONPATH = "src"
python -m pricing_api
```

Then start the frontend in another:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev -- --host 127.0.0.1
```

`VITE_API_BASE_URL` is optional and defaults to `http://127.0.0.1:8000`. The client rejects non-loopback HTTP(S) bases. `OPENAI_API_KEY` and `OPENAI_MODEL` belong only in the ignored repository `.env` consumed by FastAPI; they are not frontend configuration.

## Contract and trust boundary

The client validates the Phase 1 request, response, error, chart, health, and SSE schemas at runtime. A POST SSE stream must begin with `chat.started` sequence `0`; the stream id is learned from that event because FastAPI owns request-id generation. Sequences are contiguous, ids remain stable, and exactly one terminal event is required. Numeric deltas are rejected. A protocol failure may fall back to the JSON endpoint.

Charts accept only the `line`/`bar` chart allowlist and validated field mappings. The SVG is a presentation of the validated spec; the accessible table is the authoritative visual fallback. Raw JSON is the validated terminal response only—no headers, prompts, tool arguments, keys, or hidden reasoning are included. React does not call OpenAI, write SQL, retrain models, or persist transcripts.

## Checks

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```

Tests cover fixture parity, strict unknown-field rejection, unsafe loopback configuration, split-chunk SSE framing/order/cancellation, JSON fallback, health states, chart authority, raw JSON copy/expand, accessibility, and client-side secret/persistence boundaries.
