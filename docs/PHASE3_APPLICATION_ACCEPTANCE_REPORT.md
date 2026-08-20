# Phase 3 — React Conversational Pricing Interface Acceptance

Status: **PASS WITH WARNINGS**

Phase 3 adds the local React/TypeScript presentation surface required by the Phase 1 contracts and Phase 2 FastAPI runtime. The work is isolated on `codex/app-phase3-react-pricing-chat`, based on `53072eca341dd07e21a7fb1e511ff3c8537f0dbf`, with implementation commit `d8a312cf8b424a20e40cba16453ac79d0be31fd0` and evidence commit `81bfbcc759a67dca0f5b0ec9f032ebe4da3d7175`. The machine-readable evidence is in `artifacts/phase3_application/phase3_application_manifest.json`.

## Delivered boundary

- One responsive pricing chat route under `frontend/`; no dashboard, auth, hosting, persistence, SQL writeback, training, or model controls.
- Loopback-only API configuration, defaulting to `http://127.0.0.1:8000`. The frontend does not read `OPENAI_API_KEY`, call OpenAI, or include provider credentials in browser state.
- Phase 1 request, response, error, health, chart, and SSE runtime validation with strict unknown-field rejection and recursive sensitive-string scanning.
- POST SSE decoding across arbitrary UTF-8 chunks and frame boundaries. The client learns the server-generated stream id from `chat.started` sequence `0`, requires contiguous sequences and stable ids, rejects numeric deltas, handles cancellation, and requires exactly one terminal event.
- Charts are rendered only from validated `pricing.chart.v1` specs and allowlisted fields/types. Every chart includes an accessible data table fallback; React never recomputes pricing values.
- The raw JSON viewer is expandable, copyable, and limited to the validated terminal response payload. It does not expose headers, prompts, hidden reasoning, raw tool arguments, or secrets.
- Health, deterministic fallback, integrity-blocked, unavailable, tool-progress, error, retry, cancel, empty, keyboard, touch, and reduced-motion states are represented in the single chat surface.
- `scripts/run_local_react_app.ps1` starts FastAPI with `PYTHONPATH=src` and the frontend on loopback, with hidden child windows and cleanup on exit.

## Verification

| Check | Result |
| --- | --- |
| Frontend unit/component/contract/safety tests | 26 passed, 0 failed |
| TypeScript strict typecheck | Passed |
| ESLint | Passed |
| Vite production build | Passed |
| Loopback route smoke | HTTP 200; root mount and Pricefield title present |
| Full Python repository suite | 234 passed, 0 failed |
| Upstream Phase 1/2 evidence | Byte-for-byte unchanged |

The frontend test evidence is `artifacts/phase3_application/frontend_test_results.json`; build and route evidence are `build_results.json` and `route_smoke.json`. The Python suite evidence was generated with `TEST_EVIDENCE_PATH` pointed into the Phase 3 directory, so `artifacts/phase1/test_results.json` was not mutated.

## Warnings and handoff

The Python environment emits one existing `asyncio_default_fixture_loop_scope` configuration warning. npm reports a jsdom 30.0.1 engine advisory against Node 24.14.0; the pinned lockfile, frontend tests, typecheck, lint, build, and route smoke all pass. No live provider key or browser preview was used.

Phase 4 can add optional browser-level QA or operational packaging without changing the Phase 2 server ownership boundary. The Phase 3 frontend is ready to consume the existing FastAPI JSON and SSE endpoints locally.
