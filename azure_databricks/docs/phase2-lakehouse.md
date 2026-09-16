# Phase 2 — Lakehouse and business data contracts

## Scope and release

Pricing remains a separately versioned project in `intellify-databricks-demo`.
The Phase 0 sealed release and Phase 1 volumes are authoritative; no original is
modified. This phase does not retrain, change pricing policy, deploy the App, enable
combined tools, or create a service. It uses the existing 2X-Small SQL warehouse.

SQL cannot consume the original nanosecond Parquet timestamps. Separate content-
addressed compatibility files in the restricted volume normalize timestamps to
microseconds using safe casts, rejecting any precision loss. Null-only stock fields
and empty reason arrays receive explicit string types. Original and derived hashes
are both retained. No scoring values or original release files are overwritten.

Supported mode is **frozen historical snapshot**, not fresh pricing. Raw SQL Server
extraction is not part of this release and is not a runtime dependency. A future
snapshot requires a newly reviewed manifest, release configuration, validation and
immutable table version; source changes must never be hidden behind the old release ID.

## Data dictionary and access

All names have the manifest prefix `2e6c455737c6` as their version suffix.

| Dataset | Grain / count | Access |
|---|---|---|
| features | PricingDecisionID / 35,000 | preparation only; contains customer context and targets |
| splits | PricingDecisionID / 35,000 | preparation only |
| validation_candidates | PricingDecisionID + CandidatePrice / 47,250 | preparation only; modeled values |
| validation_model_decisions | PricingDecisionID / 5,250 | preparation only; not final business advice |
| validation_decisions | PricingDecisionID / 5,250 | preparation only; policy-adjusted source |
| test_decisions | PricingDecisionID / 5,250 | preparation only; held-out snapshot |
| inventory_decisions | PricingDecisionID / 1,829 | preparation only; inventory dated 2025-12-31 |
| validation_outcomes | PricingDecisionID / 5,250 | preparation only; factual targets and modeled values remain separate |
| cost_policy_context | inventory decision / 1,829 | preparation only; costs and effective policy boundaries |
| source_lineage | source dataset / 8 | preparation only; paths, hashes and expected counts |
| product_context | product ID | business; ID/category/brand comparison with retail |
| store_context | store ID | business; identifier label, not an invented store name |
| business_decisions | scenario + PricingDecisionID / 12,329 | App and business viewers; no cost/customer/target fields |
| action_summary | scenario + final action | App and business viewers; explicitly historical and modeled |

The last two datasets also have versioned `_view` projections. New schemas and
objects are owned by `retail_hp_admins`. `retail_hp_engineers` receives SELECT,
not write access. App/viewers receive SELECT only on explicit business objects;
there is no schema-wide SELECT. Costs and labels are excluded from public projections.

## Semantics

- Original scoring doubles remain unchanged. Business monetary presentation is
  DECIMAL(18,2), ROUND_HALF_UP. Source currency is **UNVERIFIED_SOURCE_UNIT**;
  currency code is NULL. No symbol, conversion, or cross-currency total is valid.
- Source timestamps are preserved as TIMESTAMP_NTZ; the runtime contract interprets
  them as UTC. No timezone is inferred from the operator's computer.
- Training/validation/test retain 24,500 / 5,250 / 5,250 rows, strictly chronological.
  Timestamp/key membership and available temporal audit columns are checked locally.
  This does not claim independent reconstruction of unavailable raw history.
- Historical replay cannot use December inventory: those inventory columns must
  remain null. Inventory scenarios disclose 2025-12-31 rather than calling it current.
- Missing recommended prices require review; no price is substituted. Missing or
  non-positive cost fails release validation. There is no automatic writeback.
- Review reasons, data/model/policy hashes and release ID travel with business rows.
- Store IDs present in retail inventory do not establish matching store semantics.
  Combined tools remain disabled until their required mappings are accepted.
- Product display names are borrowed only for matching ID, category and brand.
  Attribute conflicts and unmatched IDs are reported; names are never matching keys.

## Validation / deployment

```powershell
python -m unittest discover -s azure_databricks/tests -v
python azure_databricks/scripts/phase2.py plan --output build/phase2-plan.json
# Requires a fresh explicit approved validation window:
python azure_databricks/scripts/phase2_live.py --approved-inr 250 --output azure_databricks/evidence/phase_02/live.json
```

The live command checks the workspace and stopped compute, verifies every remote
release hash, arms the existing independent shutdown controller, and only then starts
the warehouse. It refuses a second allowance automatically. Do not delete its ledger
to obtain another window. Statements have bounded waits and cancellation deadlines;
the warehouse is stopped in a finally block. The App is never started.
`--resume-window` permits recovery only under the original unexpired deadline with
its controller still Running; it neither increases the allowance nor extends time.

Predictive optimization is disabled on the **new pricing schemas** before tables
are created. Existing retail settings are unchanged. SQL full multiset differences
check every loaded row in both directions, not only counts. Existing table contents
are never overwritten. Publication grants follow successful data reconciliation.
The actual App identity must read curated data and be denied restricted features;
temporary OAuth credentials are revoked afterward.

Partial materialization stays versioned and can be inspected. Reruns of the same
contract compare source and destination and fail on content drift. A correction
requires an explicit new contract/release, not silent repair of a published version.
Consumers must not use a phase until its acceptance evidence is complete.

## Cost and operational boundary

One ₹250 estimated validation allowance, maximum 30 minutes, was approved on
2026-09-16; monthly planning budget remains ₹12,000. These are not invoice caps.
Managed storage/API costs persist when compute is stopped. No schedules, new
warehouse, model endpoint, cluster, or paid monitoring service are added. The
existing shutdown runbook is reused for this one bounded test.

## References

- [CREATE TABLE and explicit types](https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/sql-ref-syntax-ddl-create-table-using)
- [Predictive optimization and schema inheritance](https://learn.microsoft.com/en-us/azure/databricks/optimizations/predictive-optimization)

Implementation, deployment and live validation are separate statuses. See
`azure_databricks/evidence/phase_02` for observed results; this runbook alone is not
proof that cloud acceptance has passed.
