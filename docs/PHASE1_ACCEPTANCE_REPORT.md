# Phase 1 Acceptance Report

## 1. Executive verdict

**PASS_WITH_WARNINGS** — Live mandatory checks passed; sparse short-window context and unavailable pricing generator logic require Phase 2 safeguards. No production model, optimizer, API, or dashboard was created.

## 2. Database reconciliation

The live read-only database contains **24 tables, 224 columns, and 328,420 rows**. This matches the documented 24 / 224 / 328,420 totals. Per-table documented/live/difference/status values are in `schema_reconciliation.json`.

## 3. Target health

There are **35,000** decisions and **35,000** usable outcomes, with 6,492 purchases and 28,508 non-purchases. Purchase rate is **18.55%**. Month/channel/store/region/category/brand/season/price-change profiles are in `target_segment_profile.csv`.

## 4. Quantity-target health

Purchased rows: **6,492**; quantity min/median/mean/p90/p95/p99/max: **1 / 1.0 / 1.3043746149106592 / 2.0 / 3.0 / 4.0 / 4**. Outcome-consistency violations: **0**. The conditional quantity target is usable.

## 5. Price variation / learnability

Products observed: **2,671**; products with at least 2 distinct applied prices: **2,409**; at least 3: **2,101**; at least 5: **1,555**. Products with at least 10/20 decisions: **901 / 393**. Observed price-response variation is adequate for a global model; bucket associations are diagnostic, not causal.

## 6. Temporal coverage

Pricing decisions span **2025-01-01 08:12:26 through 2025-12-31 23:59:39**, across 365 active dates. Every future derived feature must satisfy `feature_timestamp <= DecisionTime`.

## 7. Competitor coverage

Strict Product×Region×Channel point-in-time coverage is same-day **0.16%**, prior 3d **0.75%**, 7d **1.74%**, 14d **3.29%**, and 30d **6.57%**. At 30 days, Product×Region with any channel covers **34.02%** and Product-only covers **70.13%**. Phase 2 must retain availability/age/fallback indicators and never drop rows lacking competitor context.

## 8. Historical-sales feasibility

Only completed previous calendar days qualify; same-day date-only orders are excluded. At 30 days, prior-sale coverage is Product×Store **24.95%**, Product×Region **29.45%**, Product **60.37%**, Category×Store **52.43%**, and Category **99.73%**. Product-only coverage rises from 7d **27.43%** to 90d **83.82%**. Phase 2 should use this measured fallback hierarchy.

## 9. Promotion/calendar/weather feasibility

Active promotion coverage at decision time is **8.72%**. Of the price-history promotion associations, **1,893** are stale/inactive by window and must not be treated as active. Holiday and weather ranges are recorded in the temporal matrix and must join by date/region.

## 10. Product/store/category sparsity

ProductID has **2,671** observed values (median 6.0 decisions/entity; 1,058 below five). StoreID has **49** values (median 708.0). ProductID and StoreID remain conditional CatBoost categoricals, not blindly encoded identifiers.

## 11. Data-quality issues

Outcome-consistency violations: **0**. Price-history decision coverage is **100.00%** with 0 decisions matching multiple eligible intervals. All **29** Phase-2-critical logical joins were audited with **0** total orphans. Referenced-price-rule compliance is **91.16%**; the remaining cases need rule-semantics review rather than automatic repair. Pytest evidence is machine-generated and source-bound: **59 passed / 0 failed**.

## 12. Generator leakage analysis

Generator result: **GENERATOR_LOGIC_NOT_AVAILABLE**. The located older generator registry does not contain pricing-decision generation logic, so no formula is inferred. Empirical `PurchaseProbability` deciles are reported solely to measure synthetic outcome encoding; that field remains prohibited.

## 13. Final leakage matrix summary

All live columns are classified under a **deny-by-default explicit allowlist**. Cost and pricing rules are optimizer-only; raw sales/events are derivation-only; recommendation outputs and post-outcome fields are prohibited; PII is excluded; identifiers are join-only by default; inventory is prohibited historically.

## 14. Locked feature-policy summary

Core features are treatment price and proven pre-decision product/market/time context. Conditional features include high-cardinality IDs, preferences, and behavior. Current inventory, cost, rules, and constraints are optimization-only.

## 15. Inventory limitation

Inventory is a point-in-time snapshot and is **never** backfilled, forward-filled, or treated as historical decision context. It is supported only as a current optimization constraint.

## 16. Perishable/expiry limitation

Expiry-driven pricing remains out of scope. No expiry, batch, manufacture, or shelf-life values are created.

## 17. Proposed temporal split

- train: 2025-01-01 08:12:26 through 2025-09-23 14:26:24 — 24,500 rows, 4,581 purchases, 2,517 products
- validation: 2025-09-23 15:09:15 through 2025-11-15 23:42:22 — 5,250 rows, 939 purchases, 1,470 products
- test: 2025-11-15 23:57:30 through 2025-12-31 23:59:39 — 5,250 rows, 972 purchases, 1,426 products

This is a Phase 3 proposal and uses chronological boundaries only.

## 18. Known limitations

- Generator source for pricing decisions is unavailable.
- Region/channel-matched competitor context is sparse (30-day coverage 6.57%).
- Product×Store 30-day sales coverage is 24.95%; hierarchical fallbacks are required.
- 1,893 promotion associations are not active at their price interval.
- Rule compliance is 91.16% under the audited direct constraints and needs semantic review.
- Individual SKU histories are uneven; global/hierarchical modelling is required.
- Inventory cannot be used historically.

## 19. Risks for Phase 2+

Synthetic probability/policy outputs could make accuracy misleading if admitted accidentally. Phase 2 must build joins point-in-time, enforce the leakage allowlist, quantify exclusions, and retain hierarchical fallbacks.

## 20. Overall result

**PASS_WITH_WARNINGS**

## 21. Recommendation

**PROCEED_TO_PHASE_2** — Phase 2 may begin only under the locked contract and leakage tests.

### Dynamic-pricing learnability verdicts

1. AppliedPrice variation sufficient? **YES** — 2,409 products have at least two applied prices.
2. Both purchase classes represented? **YES** — 6,492 purchases and 28,508 non-purchases.
3. Quantity target usable? **YES** — 6,492 consistent positive purchased rows.
4. Leakage-safe point-in-time features constructible? **YES_WITH_LIMITATIONS** — coverage varies by feature family.
5. Competitor history useful? **YES_WITH_LIMITATIONS** — region/channel-matched 30-day coverage is 6.57%.
6. Sales velocity derivable? **YES_WITH_LIMITATIONS** — 30-day coverage ranges from Product×Store 24.95% to Category 99.73%.
7. Season/promotion/calendar context joinable? **YES_WITH_LIMITATIONS** — temporal overlap and region/date rules are mandatory.
8. Optimizer outputs separable? **YES** — explicit policy plus automated rejection tests.
9. Hidden generator structural problem? **NO** — none demonstrated; source unavailable, so empirical proxy risk remains a warning.
10. Proceed to Phase 2? **YES_WITH_LIMITATIONS**.
