# Phase 4 — Unified business agent and App

## Completion run update

The owner has now authorized public PRs and merges, and one additional INR 250
estimated live window (cumulative reservation ceiling INR 500; no ledger reset).
The prior local-only publication instruction is superseded. Human browser acceptance
remains pending by the owner's explicit choice; no browser pass is claimed.

The registered model and sealed source remain unchanged. The derived App package
has an explicit `LAZY_DATABASE_DRIVER_IMPORT_V1` source adaptation with original
and adapted hashes. Only the audited database driver's import timing changes;
database calls still require the real driver, and trained weights are untouched.
The actual package passed all six tests in a minimal Linux container with no native
ODBC and no network. Full baseline replay passed 12,329 decisions and all 49 fields
with no mismatches. Final live tests and CI are still pending at this checkpoint.

Status: IN PROGRESS — LIVE PRICING ACCEPTANCE FAILED (2026-09-16).
The unified App snapshot deployed, but pricing initialization remains unavailable.
Phase 3's registered model version and weights remain unchanged. Do not advance
to Phase 5 or describe this release as accepted.

## Latest validation and publication decision

- Both coordinated branches remain local, as explicitly requested by the owner.
  No push, PR or GitHub Linux CI was performed.
- Retail regression: 380 passed, four skipped. Ruff passed; mypy passed for 42
  source files. Six actual frozen-model integration tests passed on Windows,
  including a POSIX entry-point check. These are not Linux deployment acceptance.
- One INR 250 estimated validation reservation was used. No additional paid
  service was created. The original deadline was not extended.
- Initial and corrected deployments both started, but pricing requests returned
  unavailable. Retail returned five recommendations; unauthorized customer access
  was refused. Five concurrent pricing requests did not succeed. Latency acceptance
  therefore has not passed. Temporary test credentials were revoked.
- The App, SQL warehouse and recommendation endpoint were independently confirmed
  STOPPED after validation. Storage and other baseline charges can still apply;
  the reservation is not an Azure invoice cap.
- A Windows absolute `model_code_path` was found in registered MLflow metadata.
  The derived App copy now uses `phase3_model.py`, with before/after metadata hashes
  recorded in its manifest. Registry artifacts and model binaries were not changed.
  This correction alone did not resolve live startup; further diagnosis is required.
- The actual portable payload was subsequently tested in a temporary local
  `python:3.12-slim` container. It failed because `phase7.runner` imports
  `audit.database_profile`, which imports `pyodbc` at module load; the native
  `libodbc.so.2` library is absent. This reproduces an offline Linux startup
  failure consistent with the App symptom, but private App traceback evidence has
  not yet confirmed that it is the identical live exception. The container was
  removed automatically after the probe; no Azure compute was used for it.
- Durable remediation: isolate database-audit imports from the pure inference
  path, retaining explicit errors for real database operations; then rerun the
  accepted business-policy replay and actual-payload Linux tests. Any inference
  source change must receive a new recorded source fingerprint and parity evidence;
  do not silently rewrite the registered model or treat a code-modified package
  as byte-identical to model version 1. Private startup exception logging was added
  locally to the companion App and its two release tests passed; it is not deployed.
- Authenticated human browser acceptance was deferred by the owner. Automated
  identity tests do not replace this outstanding acceptance step.

The sections below record earlier implementation checkpoints; this latest status
takes precedence over earlier counts and pre-deployment statements.

## Implemented locally

- A separate `intellify-pricing-app` wheel wraps the accepted MLflow pipeline.
- An immutable private payload projects 10,500 supported historical contexts onto
  the 65 model features plus decision identifiers, dates and required product costs.
  Customer identities, sessions, customer affinities and observed outcomes are excluded.
- Bounded, serialized scoring and a 128-entry result cache; returned values are copied
  so one request cannot mutate another request's cached answer.
- Business-only output projection, historical-data disclosure, review requirements,
  exact candidate-price simulations and no automatic price writeback.
- The companion retail integration is on `codex/pricing-phase4-unified-app`, based
  on the current Genie release branch rather than the older retail default branch.
  It provides a default-off, server-owned pricing entitlement, deterministic pricing
  summaries, verified scenario follow-ups and combined recommendation/pricing answers.
- Pricing load failures withhold pricing while retaining retail chat functionality.

## Validation performed

- Five local frozen-model integration tests passed: business projection and cache
  isolation, candidate simulation, invalid inputs, five concurrent reads and private projection.
- Companion retail suite: 353 passed, four skipped before adding the separate
  24-case business matrix. The 24-case matrix also passed separately.
- The business matrix covers four cases each for recommendations, pricing, combined
  requests, follow-ups, manual review and unsupported scenarios. Routing is mocked:
  this does not establish live LLM routing quality or authenticated browser acceptance.
- Pricing wheel built successfully. No Azure compute was started.
- Read-only Azure check on 2026-09-16 found the existing App and warehouse STOPPED;
  warehouse idle auto-stop remained one minute.

## Remaining release gates

1. Complete source-seal verification, product-name hydration, unified dependency-lock
   resolution and packaging/rollback tests against the actual registered model.
2. Verify five concurrent HTTP sessions and measure uncached warm pricing p95 <=3s
   and end-to-end p95 <=30s. A five-thread cache test is not a substitute.
3. Run full type/lint checks and Linux CI for both coordinated branches.
4. Obtain a new bounded Phase 4 live validation allowance; prior phase allowances
   do not carry forward. No new paid service is required.
5. Deploy the existing App with the independent shutdown controller armed; verify
   real-user sign-in, entitlements, business scenarios, retail regression, rollback
   and final compute shutdown. Never mark Phase 4 complete from API-only checks.

## Research basis

- [Databricks Apps authentication](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/auth):
  retain forwarded user OAuth and separate App service identity; never trust a browser-supplied role.
- [App dependencies](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/dependencies):
  use the existing Python 3.12 uv deployment with a resolved lock, not a second service.
- [App best practices](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/best-practices):
  preserve least privilege and explicit resource bindings.

The frozen pricing model remains advisory. Historical synthetic results are not live
prices or evidence of profit uplift. Model performance limitations accepted in Phase 3
are not corrected by adding a conversational interface.
