# Phase 1 Application Acceptance Report

## Scope

This report covers **Application Contract & Local Architecture** only. It establishes the implementation-ready React/FastAPI boundary for one natural-language pricing chat screen, deterministic charts, and an expandable raw JSON response viewer. It does not claim that the FastAPI or React runtimes have been implemented; those are Phase 2 and Phase 3 work.

## Acceptance gates

| Gate | Evidence | Acceptance |
| --- | --- | --- |
| Architecture and trust boundary | `docs/PHASE1_APPLICATION_ARCHITECTURE.md` | Pass |
| Explicit intents and rejection behavior | `docs/PHASE1_PRICING_INTENTS.md` | Pass |
| Request/response/error/chart/SSE schemas | `contracts/application/*.schema.json` | Pass |
| Representative fixtures | `tests/application_contract/fixtures/` | Pass |
| FastAPI endpoint, CORS, lifecycle | `docs/PHASE1_API_CONTRACT.md` | Pass |
| Agent authority, minimization, secret/fallback policy | `docs/PHASE1_AGENT_GOVERNANCE.md` | Pass |
| React state/component/JSON viewer contract | `docs/PHASE1_REACT_STATE_CONTRACT.md` | Pass |
| Required ADRs | `docs/adr/ADR-00*.md` | Pass |
| Secret-free local environment example | `.env.example` | Pass |
| Automated contract tests | `tests/application_contract/` | Pass — 14 targeted tests; 209 full-suite tests |

## Verification record

```text
pytest -q tests/application_contract  -> 14 passed
pytest -q                            -> 209 passed
```

Both runs used `TEST_EVIDENCE_PATH=artifacts/phase1_application/pytest_hook_results.json`; accepted upstream Phase 1 evidence was not rewritten. The only observed test warning is an existing pytest configuration warning for `asyncio_default_fixture_loop_scope` in the frozen environment.

## Handoff invariants

1. FastAPI owns OpenAI calls, local ML/service access, validation, response normalization, and chart generation.
2. React is presentation-only and keeps chat state in memory.
3. `OPENAI_API_KEY` exists only in FastAPI process configuration and is absent from frontend, browser storage, logs, artifacts, and Git.
4. Every numeric pricing claim comes from a named deterministic tool; the model cannot invent prices.
5. Model-implied scenarios are labelled and are never presented as causal or guaranteed outcomes.
6. Unsupported actions, missing context, support-envelope violations, tool failures, and artifact-integrity failures have stable codes and safe fallbacks.
7. Contract changes require a new schema version and an ADR/amended acceptance evidence.

## Deferred work

Phase 2 implements the FastAPI endpoints, OpenAI agent adapter, deterministic service calls, and live response normalization. Phase 3 implements the React chat, chart renderer, warnings/errors, and expandable JSON panel. Neither phase may bypass the contracts in `contracts/application/`.
