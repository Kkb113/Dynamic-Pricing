# Phase 1 — Governance and immutable transfer

The deployment targets the existing `intellify-databricks-demo` workspace and
`intellify_databricks_demo` catalog, within the `Databricks` resource group.
The baseline is merged PR #10, commit `975aad7006c2bde099729570b442f2d0bd371c90`.
Its original Phase 0 seal references `f35a7a7326e03f9a6b759358c9a43b0608f4cb95`.
Subsequent merge/CI-only commits do not change any of the 204 sealed files.
Phase 1 preserves that seal and records both source revisions.

## Storage and access

Only two schemas are needed now. Silver/gold tables and schemas belong to Phase 2.
The 204-file inventory is partitioned without duplicating its data or models:

| Location | Contents | Authorized readers |
| --- | --- | --- |
| `pricing_bronze.release_inputs` | Eight Parquet datasets, including feature contexts, split assignments, decisions and backtest rows | Deployment admins and preparation engineers |
| `pricing_ml.release_runtime` | 196 model, specification, policy, configuration, source, frontend and lock files | Deployment admins, preparation engineers and the actual existing App principal |

Release folder: `pricing-f35a7a7326e0-2e6c455737c60c1b`.
Total artifact bytes: 16,267,703 (about 15.5 MiB), plus small manifests and pointer.
Original manifests remain intact. Paths below each release folder retain their
repository-relative names. The transfer plan provides the root for each partition.
Later ingestion must resolve those roots explicitly rather than assuming one flat
filesystem. Phase 3 will expose curated inference contexts without granting the
App direct access to the raw feature volume.

| Role | Existing identity | Phase 1 privileges |
| --- | --- | --- |
| Deployment | `retail_hp_admins` | Owns only the new pricing schemas/volumes; can publish release files |
| Data preparation | `retail_hp_engineers` | USE SCHEMA and READ VOLUME on pricing inputs and runtime; no file-write privilege |
| App runtime | Service principal of `retail-hp-poc-app` | USE SCHEMA on pricing_ml and READ VOLUME on runtime only |
| Business analytics | `retail_hp_viewers` | No pricing raw-volume access; curated SELECT access is deferred to Phase 2 |
| Read-only review | Repository reviewers | Sanitized manifest, reconciliation and acceptance records; no implicit data grant |

All roles already have catalog usage through existing grants. Phase 1 does not
modify catalog grants, group membership, or retail schemas. Existing catalog and
workspace administrators retain their administrative authority.

## Repeatable commands

Use Python 3.12 and an authenticated Azure CLI session for the configured
subscription. Install `azure_databricks/requirements-operator.txt` in the operator
environment. The scripts do not import the retail repository or hidden worktrees.

```powershell
python -m unittest discover -s azure_databricks/tests -v
python azure_databricks/scripts/phase1.py plan --output azure_databricks/evidence/phase_01/plan.json
python azure_databricks/scripts/phase1.py inspect --output azure_databricks/evidence/phase_01/inspection.json
python azure_databricks/scripts/phase1.py apply --output azure_databricks/evidence/phase_01/apply.json
python azure_databricks/scripts/phase1.py verify --output azure_databricks/evidence/phase_01/verification.json
python azure_databricks/scripts/phase1.py identity-test --output azure_databricks/evidence/phase_01/identity.json
```

`plan` validates all sealed local files. `inspect` is read-only. `apply` creates
only marked pricing objects, adds missing specified grants, uploads files with
`overwrite=False`, and reads back every byte. It rejects unexpected pricing grants
instead of revoking someone else's access. `verify` checks the full remote
inventory, original source manifests and verified pointer. `identity-test` uses
short-lived OAuth credentials held in memory and revoked in `finally`. It reads
the native CatBoost model as the actual App principal and confirms that both the
App and the existing lower-privilege test principal are denied restricted input
reads. Only an explicit permission-denied response counts as a successful denial.
Missing credentials, service errors and missing files do not count as proof of
access isolation. No query, model inference, App start or warehouse start is used.

## Immutability and recovery

The release ID includes the original commit and SHA-256 of the canonical source
manifest. Binary files preserve exact bytes. Text files are uploaded as canonical
UTF-8 LF bytes, matching the cross-platform Phase 0 seal. Remote verification
checks exact uploaded bytes and SHA-256, without normalizing downloaded data.

Each partition gets an identical `_source_manifest.json`. Partial uploads can be
resumed: identical existing files are skipped, missing files are uploaded, and a
different-content collision fails without replacement. `_VERIFIED.json` is
written only after all 204 files pass readback. Once published, missing or changed
files fail verification and are not silently repaired by `apply`.

This provides write-once application behavior and read-only consumer permissions;
it is **not** a regulatory WORM lock. Administrators can modify or delete Unity
Catalog files, so consumers must verify the seal before loading a release. A
future release uses a new folder and explicit pointer; old folders are retained.
There is no mutable `latest` pointer or automatic promotion. A failed upload has
no publish pointer, and can safely remain unreferenced until resumed. No cleanup
or deletion is performed automatically.

## Cost and operational scope

Metadata/Files APIs avoid starting compute. Existing managed storage holds the
small release and incurs ordinary storage/API charges; this does not mean a zero
Azure invoice. No paid service, endpoint, job, scheduled workload or App deployment
is created. Before/after evidence compares retail schema grants, catalog grants,
App deployment/resources, Azure resource inventory and shutdown configuration.

At inspection, App and warehouse were stopped, warehouse size was 2X-Small with
one-minute auto-stop and one-cluster maximum. The old September 11 and 15 demo
shutdown schedules had expired; a new approved demo window is required before a
future compute-based validation. Phase 1 does not extend those schedules.

The existing catalog inherits enabled predictive optimization. Phase 1 creates
no tables, so this does not initiate an optimization workload here. Phase 2 must
explicitly review or disable that setting for new pricing tables before ingestion
to keep maintenance compute within its approved cost plan.

The live identity test validates the existing App principal's Files API permissions;
it does not establish that dynamic pricing is enabled in the App. App integration,
curated contexts and serving validation remain later phases.

## Research

Reviewed 16 September 2026:

- [Unity Catalog volume privileges](https://learn.microsoft.com/en-us/azure/databricks/volumes/privileges): read requires USE CATALOG, USE SCHEMA and READ VOLUME; schema/catalog grants may be inherited; group ownership is supported.
- [Volumes in Databricks Apps](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/uc-volumes): grant read access where sufficient and separate volumes by sensitivity. Phase 1 grants the existing principal directly; App resource wiring is deferred to Phase 4.
- [Files in volumes](https://learn.microsoft.com/en-us/azure/databricks/volumes/volume-files): file transfer is supported through the Files API. SDK 0.81.0 signatures were checked locally before implementation.
