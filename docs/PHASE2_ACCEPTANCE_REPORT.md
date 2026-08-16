# Phase 2 Acceptance Report

## 1. Executive verdict

**PASS_WITH_WARNINGS** — All hard Phase 2 checks passed; known sparse optional context remains quantified as warnings.

## 2. Source snapshot verification

- Phase 1 source status: **MATCH**
- Source row count: **328420** across **24** tables and **224** columns.
- Pricing decisions: **35000**; decision range: `2025-01-01T08:12:26` through `2025-12-31T23:59:39`.

## 3. Canonical dataset grain

- Expected rows: 35,000
- Actual rows: 35,000
- Duplicate decision IDs: 0

## 4. Target reconciliation

- Purchases: 6,492
- Non-purchases: 28,508
- Quantity population: 6,492
- Target nulls: 0

## 5. Feature groups

The contract contains explicit CORE_FEATURES, CONDITIONAL_CUSTOMER_FEATURES, CONDITIONAL_HIGH_CARDINALITY_FEATURES, OPTIONAL_COMPETITOR_FEATURES, and BEHAVIORAL_FEATURES. No one-hot, target, frequency, or learned transformations are applied.

## 6. Price features

`CurrentPrice`, `AppliedPrice`, `BasePrice`, safe price deltas/ratios, and reusable candidate-price calculations are present. Cost and margin remain optimizer-only.

## 7. Price-history features

Active intervals use `[EffectiveFrom, EffectiveTo)` with deterministic specificity and tie-breaking. Previous prices are null when no prior interval exists; current/history discrepancies are diagnostic only.

## 8. Historical-sales features

Separate Product×Store, Product×Region, Product, Category×Store, and Category windows are retained. Date-only sales use `OrderDate < CAST(DecisionTime AS date)` and eligible statuses are explicitly configured.

## 9. Competitor features and fallback usage

Exact, generic-region, region, and product fallback values are separate. Final selected match counts: {"EXACT": 2299, "NONE": 10456, "PRODUCT_FALLBACK": 12637, "REGION_FALLBACK": 9608}.

## 10. Promotion features

Promotion activity requires an active price interval, a resolved promotion, and `StartDate <= DecisionDate <= EndDate`; stale associations are not active.

## 11. Holiday/weather features

Holiday joins use decision date plus store region/general holiday rules. Weather joins use store region and decision date only.

## 12. Behavioral features

Browsing, validated cart additions, and clicked-product searches use `EventTime <= DecisionTime` and explicit 1h/24h/168h/720h windows.

## 13. Conditional customer context

Customer segment, loyalty, preferred channel, sensitivity, and affinity fields are isolated as conditional features and are not automatically approved for final training.

## 14. Feature coverage

See `feature_coverage.csv`, `feature_distribution.csv`, and `feature_schema.json`. Infinite values: 0. Phase 1 regression: `{"competitor": [{"delta_pp": -4.285714290119813e-07, "metric": "exact_30d_pct", "phase1_pct": 6.568571428571429, "phase2_pct": 6.568571, "within_1pp": true}, {"delta_pp": 0.0, "metric": "region_30d_pct", "phase1_pct": 34.02, "phase2_pct": 34.02, "within_1pp": true}, {"delta_pp": -2.857142931134149e-07, "metric": "product_30d_pct", "phase1_pct": 70.1257142857143, "phase2_pct": 70.125714, "within_1pp": true}], "logical_relationship_orphans_phase1": 0, "promotion": {"delta_pp": 0.0, "phase1_pct": 8.72, "phase2_pct": 8.72, "within_3pp": true}, "sales": [{"delta_pp": -1.5371424285714284, "metric": "product_store_sales_30d", "phase1_pct": 24.948571428571427, "phase2_pct": 23.411429, "within_3pp": true}, {"delta_pp": -1.6799995714285707, "metric": "product_region_sales_30d", "phase1_pct": 29.451428571428572, "phase2_pct": 27.771429, "within_3pp": true}, {"delta_pp": -2.4028575714285765, "metric": "product_sales_30d", "phase1_pct": 60.371428571428574, "phase2_pct": 57.968571, "within_3pp": true}, {"delta_pp": -2.4971432857142872, "metric": "category_store_sales_30d", "phase1_pct": 52.425714285714285, "phase2_pct": 49.928571, "within_3pp": true}, {"delta_pp": -0.005714714285716127, "metric": "category_sales_30d", "phase1_pct": 99.73428571428572, "phase2_pct": 99.728571, "within_3pp": true}, {"delta_pp": -1.7228567142857187, "metric": "product_sales_7d", "phase1_pct": 27.434285714285718, "phase2_pct": 25.711429, "within_3pp": true}, {"delta_pp": -1.8542861428571484, "metric": "product_sales_90d", "phase1_pct": 83.82285714285715, "phase2_pct": 81.968571, "within_3pp": true}], "source_fingerprint_unchanged": true, "status": "PASS_WITH_WARNINGS", "tolerance_policy": "sales and promotion <=3 percentage points; competitor fallback <=1 percentage point"}`.

## 15. Null/infinite-value validation

Legitimate optional context remains null, valid absent event counts are zero, and no model-eligible numeric field contains NaN-derived infinity.

## 16. Point-in-time validation

{
  "behavior_temporal_rule": "EventTime <= DecisionTime",
  "competitor_temporal_rule": "DecisionTime-30 days <= ObservedDateTime <= DecisionTime",
  "future_behavioral_events_used": 0,
  "future_competitor_observations_used": 0,
  "future_price_intervals_used": 0,
  "future_sales_used": 0,
  "historical_inventory_features": 0,
  "price_history_temporal_rule": "EffectiveFrom <= DecisionTime AND (EffectiveTo IS NULL OR DecisionTime < EffectiveTo)",
  "sales_temporal_rule": "OrderDate >= DATEADD(day,-N,CAST(DecisionTime AS date)) AND OrderDate < CAST(DecisionTime AS date)",
  "same_day_date_only_sales_used": 0,
  "stale_promotion_associations_treated_active": 0
}

## 17. Leakage-policy validation

Targets, post-outcome values, recommendation outputs, inventory, cost/rules, and direct PII are excluded from every model feature list by deny-by-default contract validation.

## 18. Inventory prohibition validation

No Inventory table is fetched by the feature builder and `historical_inventory_features` is measured as 0.

## 19. Deterministic regeneration

- Build 1 hash: `dabd7e11bf73d4e108bd0c9a1a10b45a5394344374a117d5c980d39cd63a4a9b`
- Build 2 hash: `dabd7e11bf73d4e108bd0c9a1a10b45a5394344374a117d5c980d39cd63a4a9b`
- Match: **True**

## 20. Tests / CI

- Tests: 72 total, 72 passed, 0 failed.
- CI workflow: `.github/workflows/phase2-tests.yml` runs deterministic tests without SQL Server.

## 21–22. Known limitations and Phase 3 risks

- Competitor exact history is sparse; fallback level is preserved and quantified.
- Product×Store sales history is sparse; separate hierarchy features are retained.
- Customer and high-cardinality identifiers are conditional, not automatically approved for final model training.
- Phase 3 must own chronological train/validation/holdout construction; no random split or model training occurs here.

## 23–24. Recommendation

**PASS_WITH_WARNINGS**

**PROCEED_TO_PHASE_3** after review of the measured sparsity warnings.
