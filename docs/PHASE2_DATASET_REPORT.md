# Phase 2 Dataset Report

## Grain and targets

- Rows: **35,000**
- Columns: **102**
- Unique `PricingDecisionID`: **35,000**
- Purchases: **6,492**; non-purchases: **28,508**
- Quantity-population rows: **6,492**

## Feature families

Core price, price-history, calendar, context, sales, promotion, holiday/weather, behavioral, optional competitor, and isolated conditional-customer families are declared in `contracts/phase2_feature_contract_v1.yaml`.

## Historical sales coverage

{
  "category_sales": {
    "14": 99.211429,
    "30": 99.728571,
    "7": 95.971429
  },
  "category_store_sales": {
    "14": 31.308571,
    "30": 49.928571,
    "7": 18.822857
  },
  "product_region_sales": {
    "14": 15.562857,
    "30": 27.771429,
    "7": 8.862857
  },
  "product_sales": {
    "14": 39.522857,
    "30": 57.968571,
    "60": 73.688571,
    "7": 25.711429,
    "90": 81.968571
  },
  "product_store_sales": {
    "14": 12.985714,
    "30": 23.411429,
    "7": 7.345714
  }
}

## Competitor fallback usage

{
  "exact_coverage_pct": 6.568571,
  "future_observations_used": 0,
  "generic_region_fallback_selected_count": 2609,
  "no_context_rate_pct": 29.874286,
  "product_fallback_coverage_pct": 70.125714,
  "region_fallback_coverage_pct": 34.02,
  "selected_match_counts": {
    "EXACT": 2299,
    "NONE": 10456,
    "PRODUCT_FALLBACK": 12637,
    "REGION_GENERIC_CHANNEL": 2609,
    "REGION_OTHER_CHANNEL": 6999
  },
  "window_days": 30
}

## Sparsity and distributions

Machine-readable coverage and distribution reports are in `artifacts/phase2/feature_coverage.csv` and `artifacts/phase2/feature_distribution.csv`. Legitimate missing optional context remains null; absent historical counts are zero. No model feature contains infinity.

## Source reconciliation

Source status: **MATCH**. Accepted Phase 1 head: `29c3437e6a13df2c7ee8a24796d32d4762d4a900`. Source-tree hash: `a0cd1e9f3466291f712689b81ebfa297e54a791200c6bd52829c5f55509adc7b`.
