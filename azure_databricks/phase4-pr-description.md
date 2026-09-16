## Phase 4: unified business pricing App

- Add a bounded adapter for the accepted MLflow pricing model and historical business policies.
- Package only allowlisted private inference contexts; no customer records or credentials in this PR.
- Record Linux startup compatibility adaptations separately from the unchanged registered model and weights.
- Add local and minimal-Linux tests, immutable manifests and a Linux CI workflow.
- Coordinate with the retail repository's unified agent integration; no new paid Azure service.

Validation: six actual-payload tests passed on minimal Linux; baseline business-policy replay passed
12,329 decisions across 49 fields. Final deployment acceptance is tracked in PHASE4_STATUS.md.
The owner explicitly deferred human browser acceptance. This is an advisory historical POC,
not automatic pricing writeback or a production-performance claim.
