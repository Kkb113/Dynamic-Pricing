# Dynamic Pricing — Local AI Pricing Application (Phases 1–10)

This repository contains a read-only, frozen dynamic-pricing intelligence stack and a local Streamlit application for business demonstration. The application exposes accepted Phase 4–8 artifacts through governed recommendation, simulation, audit, and model-intelligence views. It does not retrain models, write to SQL Server, or write prices back to an operational system.

## React/FastAPI application track — Phase 3 complete

The new product track is a local-only React + FastAPI application with one natural-language pricing chat screen. The browser renders the natural-language answer, backend-authored charts, warnings, and an expandable raw JSON response viewer. FastAPI owns all OpenAI calls, local ML/service access, request validation, chart construction, and response normalization; React is presentation-only. There is no authentication, hosting, deployment, persistence, or price writeback.

Phase 1 delivers the implementation-ready application contract and local architecture. Read [docs/PHASE1_APPLICATION_ACCEPTANCE_REPORT.md](docs/PHASE1_APPLICATION_ACCEPTANCE_REPORT.md), [docs/PHASE1_APPLICATION_ARCHITECTURE.md](docs/PHASE1_APPLICATION_ARCHITECTURE.md), [docs/PHASE1_API_CONTRACT.md](docs/PHASE1_API_CONTRACT.md), and [contracts/application/README.md](contracts/application/README.md). Phase 2 implements the runnable FastAPI boundary, read-only ML tool wrappers, deterministic fallback, optional OpenAI Agents SDK narrative adapter, chart builder, and SSE stream. See [docs/PHASE2_FASTAPI_RUNTIME.md](docs/PHASE2_FASTAPI_RUNTIME.md) and the Phase 2 acceptance manifest under `artifacts/phase2_application/`. Phase 3 now implements the bounded React chat surface in [frontend/](frontend/), including POST-SSE consumption, validated charts, accessible table fallbacks, and the expandable raw JSON response viewer. Its acceptance manifest is under `artifacts/phase3_application/`.

`OPENAI_API_KEY` is supplied only to FastAPI through the ignored local `.env` file. It must never appear in React, browser storage, prompts, responses, logs, artifacts, or Git. Copy [.env.example](.env.example) without adding a real key to source control. Deterministic local tools remain available when the key/model is absent.

Validate the Phase 1 contract foundation with:

```powershell
$env:TEST_EVIDENCE_PATH = "artifacts/phase1_application/pytest_hook_results.json"
python -m pytest -q tests/application_contract
```

The existing Streamlit application remains the validated Phase 9–10 demonstration surface; it is not part of the React/FastAPI runtime handoff.

## Run the local React + FastAPI pricing chat

```powershell
python -m pip install -e ".[test]"
Copy-Item .env.example .env
$env:PYTHONPATH = "src"
python -m pricing_api
```

In a second terminal, start the Phase 3 frontend:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev -- --host 127.0.0.1
```

The backend listens on loopback (`127.0.0.1:8000`) and serves `/api/v1/healthz`, `/api/v1/pricing/chat`, and `/api/v1/pricing/chat/stream`. The frontend defaults to that same loopback base; `VITE_API_BASE_URL` may only point to `127.0.0.1`, `localhost`, or `::1`. Leave the backend OpenAI values blank to exercise the deterministic local fallback. The convenience launcher [scripts/run_local_react_app.ps1](scripts/run_local_react_app.ps1) starts both processes and stops its children when the launcher exits.

Frontend checks run from `frontend/` with `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build`. The browser never reads `OPENAI_API_KEY`, makes provider calls, persists transcripts, or computes pricing values; FastAPI remains the sole owner of tools, OpenAI access, and response normalization.

## Run the local application

1. Create and activate a virtual environment.

2. Install the project and test dependencies:

```powershell
python -m pip install -e ".[test]"
```

3. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` and `OPENAI_MODEL` if conversational explanations are wanted. The dashboard and frozen pricing tools work without an API key.

4. Start Streamlit:

```powershell
streamlit run app/streamlit_app.py
```

When `OPENAI_API_KEY` or `OPENAI_MODEL` is missing, the AI page displays **AI Agent unavailable — configure OPENAI_API_KEY to enable conversational pricing intelligence** and all non-agent pages remain available. The key is never rendered, logged, or written to artifacts.

The model and candidate surfaces are loaded from accepted artifacts once per process/session. Recommendation tools use Phase 7 decisions exactly; custom prices are scored only inside the frozen Phase 6 support envelope. All alternative-price values are model-implied scenario estimates, not observed or causal outcomes.

See [docs/LOCAL_AI_PRICING_APPLICATION.md](docs/LOCAL_AI_PRICING_APPLICATION.md), [docs/AI_PRICING_AGENT.md](docs/AI_PRICING_AGENT.md), and [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for architecture and the suggested walkthrough.

Create the ignored `.env` file with `SQL_SERVER_DATABASE`, `SQL_SERVER_USER_NAME`, and `SQL_SERVER_PASSWORD`. The local default SQL Server instance is configured as `localhost`. Then run:

```powershell
$env:PYTHONPATH = "src"
python -m audit.validation_runner
```

The audit adds the installed ODBC Driver 18 name when the configuration omits it and normalizes boolean ODBC options. Credentials are never printed or written to artifacts.

The validation runner executes pytest first, writes machine-derived test evidence bound to the current source-tree hash, and only then runs the live read-only audit. Running the audit with missing or stale test evidence produces a blocked result.
