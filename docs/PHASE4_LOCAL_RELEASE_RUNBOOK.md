# Phase 4 — local live-AI release runbook

Phase 4 proves the local React → FastAPI → optional OpenAI Agents SDK →
governed deterministic tools path. It remains a loopback-only development
runtime: no authentication, hosting, deployment, persistence, SQL writes,
training, or price writeback.

## Prerequisites

- Windows PowerShell, Python 3.10+, Node/npm, and the repository's `.venv`.
- A clean install from the checked-in lockfile.
- Optional live mode: a server-only `OPENAI_API_KEY` and an explicit
  `OPENAI_MODEL` in the ignored root `.env`. Keep both blank for deterministic
  fallback. The browser and `frontend/.env.local` must never contain the key.

Install and verify locally:

```powershell
python -m pip install -e ".[test]"
Copy-Item .env.example .env
.\scripts\verify_local_release.ps1
```

The verification script uses `npm ci`, runs frontend lint/typecheck/tests/build,
checks Python dependencies, and emits a secret-safe preflight. It never prints
`.env` contents.

## Agents SDK boundary

The FastAPI process owns the provider call, the allowlisted context projection,
the ten `function_tool`s, bounded turns/timeouts, response validation, chart
construction, and fallback policy. The React process only sends the versioned
request and renders validated response data. The adapter follows the official
[OpenAI Agents SDK Python quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart)
(`Agent`, `Runner`, and `function_tool`); SDK tracing is disabled for this
local runtime. Tool arguments, provider responses, hidden reasoning, and key
material are never copied into response bodies, logs, or evidence.

## Start and stop

Run the preflight first:

```powershell
.\scripts\release_preflight.ps1
```

Start both loopback services with owned hidden child processes:

```powershell
.\scripts\start_local_pricing_app.ps1
```

The launcher defaults to backend port `8000` and frontend port `5173`. Both
ports are validated as integers in the `1..65535` range and must differ. If
the backend port is occupied, choose an alternate loopback port; the launcher
passes `FASTAPI_PORT` to FastAPI and `VITE_API_BASE_URL` to Vite for that
process only:

```powershell
.\scripts\start_local_pricing_app.ps1 -BackendPort 8001 -FrontendPort 5173
```

Open `http://127.0.0.1:5173`. With the default backend port, health is at
`http://127.0.0.1:8000/api/v1/healthz`; with the example above it is at
`http://127.0.0.1:8001/api/v1/healthz`. The chosen ports are recorded in the
owned state and stop uses that state rather than guessing. Stop only the PIDs
owned by the launcher:

```powershell
.\scripts\stop_local_pricing_app.ps1
```

Port conflicts are reported before startup; the scripts never terminate a
process by name or scan-and-kill unrelated Python/Node processes.

## Validation modes

With a configured key/model, run exactly one bounded capability prompt after
health readiness:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m pricing_api.live_validation --output artifacts/phase4_application/live_validation.json
```

The report contains only configuration booleans, an allowlisted model id,
status/codes, actual allowlisted agent tool names/count, schema and grounding
checks, latency, and redacted hashes. It does not contain a request id,
narrative, business number, prompt, tool argument/result, response header, or
secret. A failed live gate does not disable deterministic operation.

To prove deterministic fallback, start a separate bounded process with
`OPENAI_API_KEY` and `OPENAI_MODEL` explicitly blank and use the same health and
capability request. Do not modify the real `.env`; setting process-scoped blank
variables is sufficient because process variables win over dotenv values.

When rotating or removing a key, stop the owned services, remove the value from
the ignored `.env`, and restart. Never put it in Git, React configuration,
browser storage, screenshots, test fixtures, or evidence.

## Troubleshooting

- `ARTIFACT_INTEGRITY_BLOCKED`: use the exact clean checkout and inspect only
  the preflight status; no live provider call is attempted.
- `OPENAI_KEY_OR_MODEL_NOT_CONFIGURED`: deterministic fallback is expected and
  remains useful. Configure both server-only values to test live mode.
- `AGENT_CALL_FAILED`, `AGENT_RATE_LIMITED`, or `AGENT_TIMEOUT`: the backend
  keeps deterministic tool data/charts and labels the fallback. Correct the
  model/network/configuration, then rerun the bounded validator.
- `*_PORT_IN_USE`: stop the process that owns the reported loopback port or
  choose a clean local session; do not run broad process termination commands.

The frontend has no transcript persistence and makes no direct provider call.
Only the bounded, minimized question/context projection sent by FastAPI can be
sent to OpenAI when live mode is enabled; deterministic tool data remains the
numeric authority.
