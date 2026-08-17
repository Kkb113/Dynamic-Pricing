# Phase 7 Promotion and Markdown Report

Promotions are category-level, date-inclusive, and never receive an invented priority. Conflicting active discounts require review; identical overlaps use the deterministic PromotionID only for provenance.

Inventory is a current point-in-time snapshot. Historical VALIDATION/TEST outputs carry no inventory fields. Markdown is seasonal + slow-moving + overstock only; no expiry/perishability logic exists.

Promotion audit: {
  "status": "PASS",
  "rows_evaluated": 24500,
  "zero_active_rate": 0.8534693877551021,
  "one_active_rate": 0.13844897959183675,
  "overlap_rate": 0.008081632653061225,
  "conflict_rate": 0.008081632653061225,
  "overlap_count_distribution": {
    "0": 20910,
    "1": 3392,
    "2": 185,
    "3": 13
  },
  "season_match_rate": 0.645093396474612,
  "season_semantics": "AUDIT_ONLY_DESCRIPTIVE",
  "defined_price_exact_cent_agreement": 0.0,
  "promotion_pricing_mode": "CONTEXT_ONLY"
}

Inventory audit: {
  "rows": 15000,
  "unique_product_count": 2860,
  "unique_store_count": 50,
  "snapshot_dates": [
    "2025-12-31"
  ],
  "latest_snapshot_date": "2025-12-31",
  "duplicate_product_store_snapshot_rows": 0,
  "available_qty": {
    "min": 7.0,
    "max": 130.0,
    "mean": 71.6464,
    "median": 72.0,
    "zero_rate": 0.0
  },
  "stock_status_counts": {
    "In Stock": 15000
  }
}
