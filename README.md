# Dynamic Pricing — Local AI Pricing Application (Phases 1–10)

This repository contains a read-only, frozen dynamic-pricing intelligence stack and a local Streamlit application for business demonstration. The application exposes accepted Phase 4–8 artifacts through governed recommendation, simulation, audit, and model-intelligence views. It does not retrain models, write to SQL Server, or write prices back to an operational system.

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
