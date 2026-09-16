# Phase 3 — MLflow pricing and serving

Status: local implementation, optimizer acceptance, full business-policy replay, policy sensitivity checks and clean MLflow package load passed. Linux CI, Unity Catalog registration and promotion remain pending. This is not a completed production release.

## Decision unit

`src/pricing_mlflow/pipeline.py` executes the accepted CatBoost scorer, frozen conditional-quantity estimator, supported candidate grid, monotonic response guard, economic selection, pricing rules, promotions and inventory policy. It does not serve a lookup of previously selected final prices. Batch and interactive callers use the same implementation.

The MLflow Models-from-Code adapter is `azure_databricks/scripts/phase3_model.py`. Input/output signatures are string columns `request_json` and `response_json`; the JSON contract is `pricing.scoring.v1`. The inference bundle contains six frozen model/contract/policy files and canonical Python source, never customer datasets, outcomes, credentials or database connection settings. Pricing remains advisory-only with no automatic price writeback.

Text metadata and source are packaged as canonical LF bytes. Binary trained weights are unchanged. The Phase 3 release fingerprint covers all six inference files and is stable across Windows/Linux; the original frozen scorer's internal cache fingerprint is left untouched. Linux acceptance records the complete canonical inference plan, entrypoint and dependency hashes, and registration refuses scoring-code drift after CI.

Requests explicitly supply full point-in-time model features, product/store/channel/decision identity, decision time, cost and the governed business source projections. Empty business sources must be explicit, not inferred. All six observed channels are supported. Requests reject unknown fields, customer/outcome fields, invalid prices, future feature context, unsupported simulation prices and stale current-inventory context. Current-inventory mode refers only to the frozen 2025-12-31 snapshot and a maximum 30-day context age; it is not live inventory.

`PricingService` resolves explicit product/store/channel/as-of requests against caller-authorized precomputed contexts, without accessing customer data or outcomes. It selects the latest available preceding context, labels the actual source/policy date, rejects contexts older than 30 days and dates beyond the accepted snapshot, and never pretends features have been recomputed for today. Its batch adapter uses the same pipeline, 500 contexts at a time. `persist_decisions` provides immutable, idempotent JSON outputs with SHA-256 readback and collision rejection.

Policy sensitivity tests cover explicit ceilings, rejected simulations, conflicting bounds, overlapping promotions, missing inventory and out-of-stock outcomes. An all-null final-price attachment bug found by these tests was corrected in the new adapter; the frozen accepted source pipeline and expected business outputs were not changed. Simulations are marked simulation-only and distinguish eligibility from hypothetical, uncapped model economics.

Responses distinguish raw probability/demand/economics, guarded estimates and final stock-capped decision economics. Candidate simulations report rule compliance separately and do not replace the recommendation. Currency remains unverified: Azure billing in INR does not establish the source product-price currency. Estimated uplift is model-implied, not realized revenue.

An arbitrary simulation passing price rules is not automatically approved under all promotion/markdown/inventory policies. `eligible_for_action`/`all_business_policies_approved` is true only when it matches the actual governed final price, has nonnegative margin and the decision does not require review. Other simulations retain hypothetical uncapped economics for comparison, explicitly labelled simulation-only and not stock-capped.

## Local acceptance

Use Python 3.12 and `azure_databricks/requirements-mlflow.txt`.

```powershell
python -m unittest discover -s azure_databricks/tests -v
python azure_databricks/scripts/phase3.py plan
python azure_databricks/scripts/phase3.py validate-local --evidence azure_databricks/evidence/phase_03/local_replay.json
python azure_databricks/scripts/phase3.py validate-package --evidence azure_databricks/evidence/phase_03/package_roundtrip.json
```

Both 5,250-row optimizer replays have zero monetary or price differences against the accepted Phase 6 outputs (predeclared economic tolerance 1e-8). A clean process loads the saved MLflow package without repository imports and produces the same output. The local runtime envelope is startup <60 seconds and RSS <1.5 GB. Concurrent calls are serialized around the frozen scorer's cache to prevent cross-request contamination; CatBoost uses two threads. No test-set tuning or retraining occurs.

The optimizer-only checks do not prove full Phase 7 business-policy parity. A separate replay with recovered rules, promotions and inventory subsequently passed all 12,329 decisions: validation 5,250, test 5,250 and current inventory 1,829. All 49 accepted output columns matched, with prices exact and numeric tolerance 1e-8. Evidence is `azure_databricks/evidence/phase_03/business_replay.json`. The source capture's original manifest remains unchanged and correctly records that it was not the original export; the separate successful replay establishes output equivalence.

## Required source recovery

The Windows administrator has started the local SQL Server instance `MSSQLSERVER`. Read-only recovery succeeded: 200 pricing rules, 200 promotions and 15,000 inventory rows were captured under ignored `build/phase3-policy-capture`. This capture is a newly recovered snapshot, not automatically the original export. Full equivalence is established only by replay acceptance.

Once available, `phase3_policy_snapshot.py` can export only the three business-policy projections, using the existing local environment file without logging its values. It writes a new, ignored, non-overwriting snapshot with hashes and counts. Recovered rows must reproduce every final decision for validation/test (5,250 each) and all 1,829 current-inventory scenarios, including status, policy/promotion identifiers, fallback/reason codes, stock caps and monetary fields. A new extraction is not assumed to equal the original extraction: acceptance must demonstrate equivalence. If it differs, recover the original backup rather than modifying expected results.

```powershell
python azure_databricks/scripts/phase3.py validate-business --policy-snapshot build/phase3-policy-capture --evidence azure_databricks/evidence/phase_03/business_replay.json
```

The replay reconstructs latest eligible current contexts using the original product/store/channel ordering and normalized 30-day age policy. It compares every accepted decision column, prices exactly and numeric economics within 1e-8; capture hashes are checked before reading. Inventory is narrowed to relevant product/store pairs per batch so unrelated source rows do not enter interactive requests.

## Cloud release gates

September 16 live validation passed: immutable model version 1 registered, operator/App loads reproduced the package output, all six actual/negative identity checks passed, and Champion was promoted, deleted for first-release rollback, and restored to version 1. Read-only status independently confirmed Champion version 1. Ownership is `retail_hp_admins`; temporary identity credentials were revoked. Policy projections were transferred write-once into the existing governed runtime volume. No warehouse, App, cluster or endpoint was started; final audit confirmed stopped compute and unchanged retail configuration/Azure resources. Evidence: `azure_databricks/evidence/phase_03/cloud_registration.json`.

Local platform acceptance now has 68 passing tests, including registration resume drift and normalized-alias rollback. Unity Catalog version tags use underscores because dots are reserved; alias readback is case-insensitive because Databricks returns `champion`. App identity validation used fresh authenticated local processes, not the physical App image: App integration and native-library qualification remain Phase 4 work.

Linux acceptance passed on published scoring commit `f06cd247b531e8068373b6dbe4a535d671198bb6`, including the clean package and all optimizer/business replays. All PR checks were green. The registered scoring package is bound to that exact canonical inference-plan hash; deployment-control changes do not alter the inference package.

Boundary review found upper-candidate selection in 5,153/5,250 validation and 5,122/5,250 test decisions. This is not evidence of realized profit uplift or willingness to pay. Policy-sensitivity tests pass, but production pricing approval remains false, with business review required for operational changes. No retraining or test-set tuning was performed.

The first registration created version 1 before a Windows console encoding error. The bootstrap now uses UTF-8 and supports explicit `--resume`, checking the local ledger's release seal, model name, version and run ID against the registry before continuing. It does not duplicate registration. The scoped experiment parent folder is created idempotently.

1. Capture and seal equivalent policy projections; complete full business replay without altering frozen expected outputs.
2. Publish the branch with explicit public-repository approval and pass Linux CI, including real scorer replay and clean MLflow package load. Linux must resolve the accepted policy runner's import-only `pyodbc` dependency.
3. With the approved allowance of up to INR 250, log the complete package to `/Shared/dynamic-pricing/phase3-pricing` and register `intellify_databricks_demo.pricing_ml.pricing_decision_pipeline`. `phase3_live.py` uses metadata/artifact APIs and local in-process loading; it never starts a SQL warehouse, App, cluster or serving endpoint. The allowance need not be spent on compute. Use the existing governed catalog, schema and deployment identity, not broad new grants.
4. Load the registered immutable version with the runtime identity, verify signature/artifact hashes and batch/interactive parity. Verify that unauthorized identities cannot read restricted source datasets or modify the model.
5. Set `Champion` only after all acceptance evidence passes. Record the previous alias version and package/policy/data fingerprints. Rollback restores that previous immutable version; do not delete it. On first release, rollback means withholding availability rather than selecting an unvalidated version.
6. Integrate in-process into the existing App in the later integration phase. Do not create a dedicated endpoint or start the retail App for this phase. Restore stopped compute after the approved validation window.

`phase3_lifecycle.py status` reads the current Champion. `promote --expected-current N --target-version M` checks that M is READY and carries passed release acceptance tags before changing the alias. `rollback --expected-current N --target-version M` restores a previously accepted immutable version; omitting the target version deletes only the Champion alias to withhold first-release availability. No model versions are deleted. Alias operations refuse unexpected current-version drift; the control-plane API is not an atomic compare-and-swap, so operators must serialize releases.

Read-only Azure inspection found the App and existing 2X-Small SQL warehouse stopped and no clusters. No cloud compute or paid service was started during local Phase 3 work. This observation is not a live billing guarantee.

## Engineering basis

MLflow recommends [Models-from-Code](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.pyfunc.html) for custom Python models. [Explicit model signatures](https://mlflow.org/docs/latest/ml/model/signatures/) support inference validation. [Unity Catalog model lifecycle](https://learn.microsoft.com/en-us/azure/databricks/machine-learning/manage-model-lifecycle/) uses immutable versions and aliases rather than legacy stages. [MLflow release history](https://mlflow.org/releases/archive) identifies 3.16.0; the older 3.4.0 failed pandas 3 string-schema validation in local testing, so the dependency was upgraded and the clean roundtrip rerun successfully.
