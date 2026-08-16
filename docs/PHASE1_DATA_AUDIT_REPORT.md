# Phase 1 Data Audit Report

## Execution summary

The audit connected to `Retail_Hyperpersonlaization` through the ignored local `.env` and requested ODBC read-only access. All source operations were guarded `SELECT`/metadata queries. No source rows, schema objects, credentials, or PII were written or exported.

The live database exactly matches the documented structural totals: **24 tables, 224 columns, 328,420 rows**. The pricing fact contains **35,000 decisions** from 2025-01-01 through 2025-12-31, with no missing `PurchasedFlag` values. There are **6,492 purchases**, **28,508 non-purchases**, and an **18.5486% purchase rate**.

## Target and outcome integrity

All purchased rows have positive quantity and revenue; all non-purchased rows have zero quantity and revenue. No outcome predates its decision. Purchased quantity has min 1, median 1, mean 1.3044, p90 2, p95 3, p99 4, and max 4. This supports a conditional quantity model on the 6,492 purchased rows.

The prohibited synthetic `PurchaseProbability` is strongly ordered with outcomes: observed purchase rate rises from **8.89%** in decile 1 to **32.74%** in decile 10. This confirms material generator encoding and reinforces its prohibition as a model input.

## Price-response learnability

The log covers 2,671 products. **2,409** products have at least two distinct applied prices, 2,101 have at least three, and 1,555 have at least five. The audit found 901 products with at least ten decisions and 393 with at least twenty. `RecommendedPrice` differs from `AppliedPrice` in **6,155 / 35,000 decisions (17.59%)**, with mean absolute difference 0.2931.

Price-history integrity is strong: 50,000 intervals, zero invalid orderings, zero overlaps at Product×Store×Channel, zero missing/nonpositive prices, and **100% pricing-decision coverage** under `[EffectiveFrom, EffectiveTo)`.

## Point-in-time context

- Strict Product×Region×Channel competitor coverage is 0.16% same-day, 0.75% within 3 days, 1.74% within 7 days, 3.29% within 14 days, and **6.57% within 30 days**. At 30 days, Product×Region with any channel reaches **34.02%** and Product-only reaches **70.13%**. Phase 2 must expose availability, age, and fallback-level indicators rather than requiring competitor context or silently mixing grains.
- Same-day date-only orders are excluded because their true time is unknown. Using completed prior calendar days only, 30-day historical-sales coverage is **24.95% Product×Store**, **29.45% Product×Region**, **60.37% Product**, **52.43% Category×Store**, and **99.73% Category**. Phase 2 should implement this hierarchy rather than discard sparse rows.
- Pre-decision behavioral coverage at 24 hours is 79.57% for product browsing, 27.68% for cart activity, and 30.91% for search-clicked-product activity.
- Active promotion coverage is 8.72%. There are 1,893 price-history promotion associations outside the promotion window; a non-null PromotionID is not sufficient.
- Weather covers all 365 days across the expected regional rows. Holidays cover 69 distinct dates. Inventory has exactly one date, 2025-12-31, and is prohibited as historical context.

## Sparsity and rules

ProductID has median 6 decisions, 257 singleton products, and 1,058 products below five decisions. StoreID has 49 values and median 708 decisions. ProductID and StoreID may be evaluated as conditional CatBoost categoricals, but ProductID requires global/hierarchical support.

All 200 rules have valid configured ranges and all 35,000 decisions reference a rule. Applied price satisfies the directly audited min/max/max-change constraints for **31,905 decisions (91.16%)**. The remaining 3,095 records require rule-semantics review; they were not repaired or excluded.

All 13 declared foreign keys and all 29 Phase-2-critical logical relationships were validated. The logical checks cover sales, product/category/brand, customer/store/region, browsing, cart, search, ratings, wishlist, recommendation, response, weather, and holiday joins. Total logical orphans: **0**.

## Generator and leakage finding

The available older generator source does not contain the pricing-decision generation fields, so the status is `GENERATOR_LOGIC_NOT_AVAILABLE`. No hidden formula is inferred. Empirical probability diagnostics show substantial synthetic-outcome encoding, so all policy outputs remain prohibited.

The leakage matrix is deny-by-default. Cost and all pricing-rule fields are optimizer-only; raw sales and event outcomes are derivation-only; recommendation model outputs are prohibited. Pytest produced source-bound evidence showing **59 passed, 0 failed**. SQL read-only validation explicitly rejects `SELECT ... INTO`.

## Result

**PASS_WITH_WARNINGS.** The data supports proceeding to Phase 2 under the locked leakage policy, point-in-time joins, hierarchical sales fallbacks, conditional competitor use, and the historical-inventory prohibition. No production model was trained.

See [PHASE1_ACCEPTANCE_REPORT.md](PHASE1_ACCEPTANCE_REPORT.md) and [phase1_manifest.json](../artifacts/phase1/phase1_manifest.json).
