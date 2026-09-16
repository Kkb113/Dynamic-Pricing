# Azure Databricks dynamic pricing — Phase 0 release readiness

Status: Phase 0 complete with local and Linux CI validation; cloud deployment and live validation not started.

Linux CI passed on commit `08bf3194627bbc8c3fdee954fc998d934d46ecb8`: 280 Python tests, 30 frontend tests, lint, frontend production build, Python wheel, and all 204 release hashes. Evidence: https://github.com/Kkb113/Dynamic-Pricing/actions/runs/35057674763. The run emitted one upstream Starlette/AnyIO deprecation warning.

## Scope decision

The Phase 0 release supports a sealed historical-snapshot POC. It provides historical decision replay and bounded historical what-if simulations. Fresh-input pricing remains disabled until Phase 2 supplies and validates a complete fresh data context. The application is advisory-only and does not write prices to a retail system.

Source currency has not been established from authoritative retail metadata. All monetary values therefore use the label **source currency units**, without a symbol or conversion. Azure subscription billing in INR is unrelated to the currency of retail prices.

The inventory scenario uses a snapshot dated **2025-12-31**. It is not live inventory and is presented as historical throughout the service and UI.

## Consolidated source

Phase 0 was developed from the most complete reviewed working copy, `.app-phase4-work`, including its pre-existing uncommitted API, frontend, release, and test changes. The original root and all hidden worktrees were preserved. The implementation is consolidated on `codex/azure-phase0-remediation`; its final release commit and transfer manifest identify the authoritative source.

The stable Azure-facing package boundary is `dynamic_pricing`. Legacy internal modules remain temporarily available because renaming all historic training packages would introduce avoidable migration risk. New Databricks implementation code must import through the pricing namespace or an explicit service adapter; later phases must not create new generic top-level packages.

## Correctness fixes

- Off-grid simulation inserts the requested price into the complete historical candidate set and recomputes the cumulative-minimum response guard before economics are returned.
- Frozen-scoring cache keys include release identity, decision ID, feature/cost context identity, and candidate price.
- Recommendations and explanations keep raw probability, guarded demand, and inventory-capped demand separate. A purchase probability is no longer reverse-engineered from capped expected units.
- Currency symbols are suppressed until currency is verified. Backend results expose an unverified-currency status and the frontend uses source-unit labels.
- “Current” inventory language is replaced with an explicit historical snapshot label and date.
- Runtime configuration supports safe loopback local execution and prepares same-origin Databricks execution on `0.0.0.0:$DATABRICKS_APP_PORT`.
- Blanket rejection of ordinary SQL/business language was removed. Direct credential extraction, hidden-instruction requests, code execution, retraining, and live price changes remain rejected.
- A complete allowlisted release inventory covers source, contracts, configuration, UI source, prepared features/splits, model and estimator, optimizer/policy artifacts, decision snapshots, and the lazy validation feature context.

## Baseline and intentional differences

Original accepted model and decision artifacts are not rewritten. Historical on-grid candidate responses remain the parity baseline. Intentional Phase 0 differences are limited to:

1. corrected off-grid response safety;
2. truthful explanation semantics;
3. truthful currency and inventory-snapshot presentation;
4. release/context-aware caching;
5. portable deployment configuration and narrower policy rejection.

The selected purchase model remains modestly predictive (recorded test ROC AUC approximately 0.6093 and top-decile lift approximately 1.4918). The optimizer's historical test surface chooses its upper boundary approximately 97.6% of the time. Phase 0 does not conceal or tune away that behavior. Price output remains advisory and manual-review policy remains authoritative. These figures do not prove causal or realized profit uplift.

## Unsupported or controlled conditions

| Condition | Phase 0 behavior |
| --- | --- |
| Unknown pricing decision | Reject with a stable unknown-decision error |
| Missing feature context | Reject simulation without numeric advice |
| Candidate outside model support | Reject automatic scoring |
| Missing/invalid price | Reject validation |
| Missing cost | No supported fresh-input inference; Phase 2 contract must reject it |
| Missing inventory | Omit inventory claims; never imply live stock |
| Ambiguous product/store/channel | Ask for clarification; never choose a random historical record |
| Policy conflict or rule violation | Return manual-review status |
| Currency unverified | Use source currency units; no symbol or conversion |
| Snapshot stale | Disclose the 2025-12-31 date |

## Dependency and deployment approach

Runtime, testing, and optional training/extraction/legacy-UI dependencies are separated in `pyproject.toml`. The locally tested runtime and test versions are recorded in lock files. Linux installation, tests, frontend lint/test/build, and manifest construction are included in the Phase 0 CI workflow.

Official Databricks guidance confirms that Databricks Apps inject a runtime port, support same-origin application routing, and expect managed resource/secret references rather than hard-coded secrets. This phase prepares those boundaries only; it does not create an App resource or grant access.

## Phase 0 evidence and handoff

Sanitized evidence is stored under `artifacts/azure_databricks/phase0/`. The final acceptance record distinguishes local implementation from cloud deployment and live validation. Phase 1 may start only from the final clean commit and matching transfer manifest.

Rollback for Phase 0 is branch-level: leave the existing dynamic-pricing worktrees unchanged and discard the isolated consolidation branch if it is not accepted. No Azure rollback is needed because Phase 0 starts no Azure resources.
