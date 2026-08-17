# Phase 7 Acceptance Report

This report is generated from the read-only SQL acceptance run and the immutable Phase 1–6 artifacts. Phase 7 is advisory-only; it never writes back to SQL and it never retrains a model.

## 1. Executive verdict

**BLOCKED** — DO_NOT_PROCEED_TO_PHASE_8.

## 2. Upstream Phase 6 verification

{
  "manifest_path": "artifacts\\phase6\\phase6_manifest.json",
  "manifest_sha256": "b0881cd6e13ae8aa16fea8163a46cbdc40a2fabe66f3ca346539523b7f737b8a",
  "spec_path": "artifacts\\phase6\\frozen_optimizer_spec.json",
  "spec_sha256": "d18bf5783aee43443709848f224ad6f6158638150f7272bf43ea1a371f86177e",
  "candidate_surface_fingerprints": {
    "validation": "4c2e1729736d429f9f0c7910d4c1fc7d82fc6c850255112d6cf4cc63d41bb610",
    "test": "da959dac729757fe4cee76c309c92e85ae88948758c28ad3475b384c092e00ac"
  },
  "recommendation_fingerprints": {
    "validation": "2db3bb58f18aa0d21dd68b52721556e845a5a92c5babbe89b353f9818948edab",
    "test": "d7ec42c95eaa06766e0e2195d02d88fd4b1d56b1030fb23bcf130728aa834f52"
  },
  "phase6_manifest": {
    "base_branch": "codex/phase1-data-audit",
    "base_git_sha": "91cb9bff7e16fa845eac5b7abf4ddd945af40c78",
    "candidate_counts": {
      "test": 47250,
      "validation": 47250
    },
    "candidate_grid": [
      0.9,
      0.925,
      0.95,
      0.975,
      1.0,
      1.025,
      1.05,
      1.075,
      1.1
    ],
    "candidate_parity": {
      "integrated_expected_unit_delta": 0.0,
      "phase4_candidate_probability_delta": 0.0,
      "phase4_feature_max_delta": 0.0,
      "phase4_feature_violations": 0,
      "phase4_test_prediction_delta": 0.0,
      "phase5_artifact_quantity_delta": 0.0024325427332176908,
      "phase5_artifact_scope": "PRE_FREEZE_TRAIN_ONLY",
      "phase5_candidate_quantity_delta": 0.0,
      "phase5_feature_max_delta": 0.0,
      "phase5_test_expected_unit_delta": 0.0,
      "rows": 5250,
      "split": "validation",
      "status": "PASS",
      "tolerance": 1e-10
    },
    "ci_status": "PASS",
    "compute": {
      "Phase4_prediction_seconds": 0.41672309997375123,
      "Phase5_quantity_seconds": 0.05409909997251816,
      "candidate_generation_seconds": 0.3592678999702912,
      "candidate_rows_per_second": 763.7041984662435,
      "candidate_rows_scored": 94500,
      "decisions_scored": 10500,
      "economic_scoring_seconds": 0.02393679996021092,
      "feature_generation_seconds": 1.1641711000120267,
      "logical_threads": 22,
      "optimizer_selection_seconds": 92.98281119999592,
      "physical_cores": 16,
      "threads_used": 22,
      "total_seconds": 123.73900809997576
    },
    "cost_audit": {
      "cost_gt_base_count": 0,
      "cost_gt_base_rate": 0.0,
      "cost_gt_current_count": 0,
      "cost_gt_current_rate": 0.0,
      "coverage_rate": 1.0,
      "covered_rows": 35000,
      "decision_rows": 35000,
      "invalid_count": 0,
      "max": 426.46,
      "mean": 86.85882685714286,
      "median": 74.365,
      "min": 2.58,
      "missing_count": 0,
      "optimizer_only": true,
      "sidecar_path": "artifacts/phase6/product_cost_sidecar.parquet",
      "sidecar_sha256": "67207c07321025d19065fc3163af1ed38b032f633f06d091b800200a96dc18c4",
      "source": "dbo.Product.CostPrice_read_only",
      "static_cost_limitation": "Product.CostPrice is a static reference; historical cost variation is unavailable in Phase 2.",
      "unique_products": 2671
    },
    "cost_coverage": 1.0,
    "cost_source": "dbo.Product.CostPrice_read_only",
    "evidence_git_sha": "e8fdd5acb14f5ac0435ff508ab21c286dcc881e2",
    "implementation_git_sha": "408c87276d24dd34c6455cf60fbcb6967c2616d7",
    "major_blockers": [],
    "materiality_policy": {
      "minimum_relative_expected_profit_uplift": 0.005
    },
    "official_objective": "EXPECTED_GROSS_PROFIT",
    "outcome_blindness": {
      "ActualRevenue_accessed": false,
      "OrderLineID_accessed": false,
      "OutcomeTime_accessed": false,
      "PurchasedFlag_accessed": false,
      "QuantityPurchased_accessed": false,
      "frozen_optimizer_spec_sha256": "8a2361f145a93ae372311c5fe49d24ccb889dd87a7eee6523cd66a1d46d53ab8",
      "test_feature_end": "2025-12-31T23:59:39",
      "test_feature_start": "2025-11-15T23:57:30",
      "test_outcomes_accessed": false,
      "test_scenario_context_columns": [
        "PricingDecisionID",
        "DecisionTime",
        "ProductID",
        "StoreID",
        "Channel",
        "CurrentPrice",
        "AppliedPrice",
        "BasePrice",
        "price_change_amount",
        "price_change_pct",
        "price_vs_base_pct",
        "current_vs_base_pct",
        "discount_from_base_pct",
        "active_history_selling_price",
        "history_discount_pct",
        "days_since_current_price_started",
        "previous_selling_price",
        "previous_price_change_pct",
        "decision_month",
        "decision_quarter",
        "decision_day_of_week",
        "decision_is_weekend",
        "CategoryID",
        "BrandID",
        "Season",
        "StoreType",
        "RegionID",
        "ClimateZone",
        "active_promotion_flag",
        "active_promotion_discount_pct",
        "product_store_sales_7d",
        "product_store_sales_14d",
        "product_store_sales_30d",
        "product_region_sales_7d",
        "product_region_sales_14d",
        "product_region_sales_30d",
        "product_sales_7d",
        "product_sales_14d",
        "product_sales_30d",
        "product_sales_60d",
        "product_sales_90d",
        "category_store_sales_7d",
        "category_store_sales_14d",
        "category_store_sales_30d",
        "category_sales_7d",
        "category_sales_14d",
        "category_sales_30d",
        "product_sales_velocity_7d",
        "product_sales_velocity_30d",
        "product_sales_velocity_90d",
        "product_sales_velocity_ratio_7d_30d",
        "days_since_last_product_sale",
        "is_holiday",
        "holiday_sales_impact_factor",
        "weather_temperature",
        "weather_condition",
        "weather_precipitation",
        "product_views_1h",
        "product_views_24h",
        "product_views_168h",
        "product_views_720h",
        "cart_additions_1h",
        "cart_additions_24h",
        "cart_additions_168h",
        "cart_additions_720h",
        "search_clicks_1h",
        "search_clicks_24h",
        "search_clicks_168h",
        "search_clicks_720h",
        "CostPrice"
      ],
      "test_scenario_context_outcome_columns": [],
      "test_scenario_outcomes_accessed": false,
      "test_used_to_tune_candidate_grid": false,
      "test_used_to_tune_materiality": false,
      "test_used_to_tune_objective": false,
      "test_used_to_tune_response_guard": false
    },
    "phase2_dataset_sha": "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2",
    "phase3_split_sha": "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d",
    "phase4_frozen_spec_sha": "87ffb4e56af455937a0c92b1be45be0e2c8082cc0efd6afa51eb62f9c05ba9d0",
    "phase4_model_sha": "1af936a1905dcb21e3623392a16afbdbfc6b57c6866093fd6b33f12976dfd86d",
    "phase5_estimator_fingerprint": "481e7de3c4fa8113ee5fd13e5c318b8bc2cb7dc2c652883119ee8608975978ba",
    "phase5_estimator_type": "CONSTANT_MEAN",
    "phase5_frozen_spec_sha": "260354340c41fe8eaccaafc4e3388f7fb28c81ec4fbaba049504a25b7a487914",
    "phase5_mean_value": 1.3057971014492753,
    "price_support": {
      "candidate_multiplier_template": [
        0.9,
        0.925,
        0.95,
        0.975,
        1.0,
        1.025,
        1.05,
        1.075,
        1.1
      ],
      "count": 24500,
      "effective_support_high": 1.1173885792710216,
      "effective_support_low": 0.8929977619398718,
      "max": 1.1201831362075543,
      "mean": 1.019822843056361,
      "min": 0.8799014576062409,
      "p01": 0.8929977619398718,
      "p05": 0.9050912024762382,
      "p25": 0.9687779630179572,
      "p50": 1.0152957836513834,
      "p75": 1.0899782675217224,
      "p95": 1.1070176241530623,
      "p99": 1.1173885792710216,
      "std": 0.06826214156631909,
      "technical_multiplier_high": 1.2,
      "technical_multiplier_low": 0.8,
      "training_ratio_p01": 0.8929977619398718,
      "training_ratio_p99": 1.1173885792710216,
      "valid_positive_rate": 1.0
    },
    "recommendation": "PROCEED_TO_PHASE_7",
    "reproducibility": {
      "candidate_price_mismatch_count": 0,
      "candidate_row_count_run1": 47250,
      "candidate_row_count_run2": 47250,
      "decision_status_mismatch_count": 0,
      "max_expected_profit_delta": 0.0,
      "max_expected_units_delta": 0.0,
      "max_probability_delta": 0.0,
      "max_revenue_delta": 0.0,
      "selected_price_mismatch_count": 0,
      "status": "PASS",
      "tolerance": 1e-10
    },
    "response_guard_metrics": {
      "test": {
        "adjusted_decision_count": 1952,
        "adjusted_decision_rate": 0.3718095238095238,
        "candidate_adjustment_count": 3183,
        "candidate_adjustment_rate": 0.06736507936507936,
        "candidate_count": 47250,
        "decision_count": 5250,
        "max_adjustment": 0.039215312653799905,
        "mean_adjustment": 0.00019594293743743028,
        "median_adjustment": 0.0,
        "p95_adjustment": 0.0006397710545302332,
        "raw_non_monotonic_decision_count": 1952,
        "raw_non_monotonic_decision_rate": 0.3718095238095238,
        "safe_monotonic_violations": 0
      },
      "validation": {
        "adjusted_decision_count": 1958,
        "adjusted_decision_rate": 0.372952380952381,
        "candidate_adjustment_count": 3216,
        "candidate_adjustment_rate": 0.06806349206349206,
        "candidate_count": 47250,
        "decision_count": 5250,
        "max_adjustment": 0.04187030097774669,
        "mean_adjustment": 0.00019667536083375713,
        "median_adjustment": 0.0,
        "p95_adjustment": 0.0006123767676781108,
        "raw_non_monotonic_decision_count": 1958,
        "raw_non_monotonic_decision_rate": 0.372952380952381,
        "safe_monotonic_violations": 0
      }
    },
    "result": "PASS_WITH_WARNINGS",
    "test_optimizer_summary": {
      "all_candidates_negative_margin_rate": 0.0,
      "any_boundary_selection_rate": 0.9758095238095238,
      "candidate_negative_margin_rate": 0.0,
      "candidate_rows": 47250,
      "decision_count": 5250,
      "decisions_where_all_candidates_negative_margin": 0,
      "decisions_with_any_negative_margin_candidate": 0,
      "lower_boundary_selection_rate": 0.00019047619047619048,
      "max_candidate_count": 9,
      "mean_candidate_count": 9.0,
      "mean_expected_profit_uplift": 2.566393252582335,
      "mean_expected_revenue_delta": 1.6340887086251197,
      "mean_price_change_pct": 0.0989178324871371,
      "median_expected_profit_uplift": 2.058202637178119,
      "median_price_change_pct": 0.10000000000000009,
      "median_recommended_multiplier": 1.1,
      "min_candidate_count": 9,
      "no_change_rate": 0.0,
      "p05_price_change_pct": 0.09990890037343178,
      "p25_price_change_pct": 0.09998384424088547,
      "p75_price_change_pct": 0.10001979610016831,
      "p95_price_change_pct": 0.10007225433526012,
      "positive_uplift_rate": 1.0,
      "price_decrease_rate": 0.0032380952380952383,
      "price_increase_rate": 0.9967619047619047,
      "raw_vs_safe_recommendation_change_rate": 0.00038095238095238096,
      "revenue_profit_differ_rate": 0.6460952380952381,
      "split": "test",
      "upper_boundary_selection_rate": 0.9756190476190476
    },
    "test_stack_parity": {
      "integrated_expected_unit_delta": 0.0,
      "phase4_candidate_probability_delta": 0.0,
      "phase4_feature_max_delta": 0.0,
      "phase4_feature_violations": 0,
      "phase4_test_prediction_delta": 0.0,
      "phase5_artifact_quantity_delta": 0.0,
      "phase5_artifact_scope": "POST_FREEZE_TRAIN_PLUS_VALIDATION",
      "phase5_candidate_quantity_delta": 0.0,
      "phase5_feature_max_delta": 0.0,
      "phase5_test_expected_unit_delta": 0.0,
      "rows": 5250,
      "split": "test",
      "status": "PASS",
      "tolerance": 1e-10
    },
    "tests": {
      "duration_seconds": 13.318926,
      "exit_code": 0,
      "failed": 0,
      "generated_at_utc": "2026-08-17T01:34:29.991595+00:00",
      "invocation": [
        "__main__.py",
        "-q",
        "--basetemp=C:\\Users\\karth\\AppData\\Local\\Temp\\dynamic-pricing-phase4-publish-20260816\\.phase6-pytest-p69jcc1l"
      ],
      "passed": 134,
      "runner_exit_code": 0,
      "skipped": 0,
      "source": "pytest_sessionfinish",
      "source_tree_sha256": "a55c7f23a2c5e57190c9db01cefb77d8cc8daa350dbd1fbbbdb877d0311bc60a",
      "status": "PASS",
      "total": 134,
      "xfailed": 0,
      "xpassed": 0
    },
    "tie_policy": {
      "band": {
        "absolute": 1e-08,
        "relative": 0.001
      },
      "break": [
        "CLOSEST_TO_CURRENT_PRICE",
        "LOWER_PRICE",
        "DETERMINISTIC_CANDIDATE_ORDER"
      ]
    },
    "validation_optimizer_summary": {
      "all_candidates_negative_margin_rate": 0.0,
      "any_boundary_selection_rate": 0.981904761904762,
      "candidate_negative_margin_rate": 0.0,
      "candidate_rows": 47250,
      "decision_count": 5250,
      "decisions_where_all_candidates_negative_margin": 0,
      "decisions_with_any_negative_margin_candidate": 0,
      "lower_boundary_selection_rate": 0.00038095238095238096,
      "max_candidate_count": 9,
      "mean_candidate_count": 9.0,
      "mean_expected_profit_uplift": 2.572559924571292,
      "mean_expected_revenue_delta": 1.6735719533616142,
      "mean_price_change_pct": 0.09919008630929192,
      "median_expected_profit_uplift": 2.0317082524480004,
      "median_price_change_pct": 0.10000000000000009,
      "median_recommended_multiplier": 1.1,
      "min_candidate_count": 9,
      "no_change_rate": 0.0,
      "p05_price_change_pct": 0.09991603694374485,
      "p25_price_change_pct": 0.09998306806233026,
      "p75_price_change_pct": 0.10002020817416674,
      "p95_price_change_pct": 0.10008240764677818,
      "positive_uplift_rate": 1.0,
      "price_decrease_rate": 0.002476190476190476,
      "price_increase_rate": 0.9975238095238095,
      "raw_vs_safe_recommendation_change_rate": 0.001142857142857143,
      "revenue_profit_differ_rate": 0.6426666666666667,
      "split": "validation",
      "upper_boundary_selection_rate": 0.9815238095238096
    },
    "warnings": [
      "OPTIMIZER_BOUNDARY_HEAVY",
      "OPTIMIZER_STRONGLY_BOUNDARY_SEEKING",
      "HIGH_RESPONSE_GUARD_USAGE"
    ]
  },
  "frozen_optimizer_spec": {
    "candidate_multiplier_template": [
      0.9,
      0.925,
      0.95,
      0.975,
      1.0,
      1.025,
      1.05,
      1.075,
      1.1
    ],
    "candidate_prediction_batch_size": 250000,
    "cost_sidecar_sha": "67207c07321025d19065fc3163af1ed38b032f633f06d091b800200a96dc18c4",
    "cost_source": "dbo.Product.CostPrice_read_only",
    "effective_support_high": 1.1173885792710216,
    "effective_support_low": 0.8929977619398718,
    "frozen_optimizer_spec_sha256": "8a2361f145a93ae372311c5fe49d24ccb889dd87a7eee6523cd66a1d46d53ab8",
    "inventory_constraint_applied": false,
    "minimum_relative_profit_uplift": 0.005,
    "official_objective": "EXPECTED_GROSS_PROFIT",
    "outcome_blind_policy": true,
    "phase2_dataset_sha": "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2",
    "phase3_split_sha": "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d",
    "phase4_calibration": "NATIVE",
    "phase4_frozen_spec_sha": "87ffb4e56af455937a0c92b1be45be0e2c8082cc0efd6afa51eb62f9c05ba9d0",
    "phase4_model_sha": "1af936a1905dcb21e3623392a16afbdbfc6b57c6866093fd6b33f12976dfd86d",
    "phase4_ordered_feature_names": [
      "CurrentPrice",
      "AppliedPrice",
      "BasePrice",
      "price_change_amount",
      "price_change_pct",
      "price_vs_base_pct",
      "current_vs_base_pct",
      "discount_from_base_pct",
      "active_history_selling_price",
      "history_discount_pct",
      "days_since_current_price_started",
      "previous_selling_price",
      "previous_price_change_pct",
      "decision_month",
      "decision_quarter",
      "decision_day_of_week",
      "decision_is_weekend",
      "CategoryID",
      "BrandID",
      "Season",
      "StoreType",
      "RegionID",
      "ClimateZone",
      "Channel",
      "active_promotion_flag",
      "active_promotion_discount_pct",
      "product_store_sales_7d",
      "product_store_sales_14d",
      "product_store_sales_30d",
      "product_region_sales_7d",
      "product_region_sales_14d",
      "product_region_sales_30d",
      "product_sales_7d",
      "product_sales_14d",
      "product_sales_30d",
      "product_sales_60d",
      "product_sales_90d",
      "category_store_sales_7d",
      "category_store_sales_14d",
      "category_store_sales_30d",
      "category_sales_7d",
      "category_sales_14d",
      "category_sales_30d",
      "product_sales_velocity_7d",
      "product_sales_velocity_30d",
      "product_sales_velocity_90d",
      "product_sales_velocity_ratio_7d_30d",
      "days_since_last_product_sale",
      "is_holiday",
      "holiday_sales_impact_factor",
      "weather_temperature",
      "weather_condition",
      "weather_precipitation",
      "product_views_1h",
      "product_views_24h",
      "product_views_168h",
      "product_views_720h",
      "cart_additions_1h",
      "cart_additions_24h",
      "cart_additions_168h",
      "cart_additions_720h",
      "search_clicks_1h",
      "search_clicks_24h",
      "search_clicks_168h",
      "search_clicks_720h"
    ],
    "phase5_estimator_fingerprint": "481e7de3c4fa8113ee5fd13e5c318b8bc2cb7dc2c652883119ee8608975978ba",
    "phase5_estimator_type": "CONSTANT_MEAN",
    "phase5_frozen_quantity_spec_sha": "260354340c41fe8eaccaafc4e3388f7fb28c81ec4fbaba049504a25b7a487914",
    "phase5_mean_value": 1.3057971014492753,
    "phase5_ordered_feature_names": [
      "CurrentPrice",
      "AppliedPrice",
      "BasePrice",
      "price_change_amount",
      "price_change_pct",
      "price_vs_base_pct",
      "current_vs_base_pct",
      "discount_from_base_pct",
      "active_history_selling_price",
      "history_discount_pct",
      "days_since_current_price_started",
      "previous_selling_price",
      "previous_price_change_pct",
      "decision_month",
      "decision_quarter",
      "decision_day_of_week",
      "decision_is_weekend",
      "CategoryID",
      "BrandID",
      "Season",
      "StoreType",
      "RegionID",
      "ClimateZone",
      "Channel",
      "active_promotion_flag",
      "active_promotion_discount_pct",
      "product_store_sales_7d",
      "product_store_sales_14d",
      "product_store_sales_30d",
      "product_region_sales_7d",
      "product_region_sales_14d",
      "product_region_sales_30d",
      "product_sales_7d",
      "product_sales_14d",
      "product_sales_30d",
      "product_sales_60d",
      "product_sales_90d",
      "category_store_sales_7d",
      "category_store_sales_14d",
      "category_store_sales_30d",
      "category_sales_7d",
      "category_sales_14d",
      "category_sales_30d",
      "product_sales_velocity_7d",
      "product_sales_velocity_30d",
      "product_sales_velocity_90d",
      "product_sales_velocity_ratio_7d_30d",
      "days_since_last_product_sale",
      "is_holiday",
      "holiday_sales_impact_factor",
      "weather_temperature",
      "weather_condition",
      "weather_precipitation",
      "product_views_1h",
      "product_views_24h",
      "product_views_168h",
      "product_views_720h",
      "cart_additions_1h",
      "cart_additions_24h",
      "cart_additions_168h",
      "cart_additions_720h",
      "search_clicks_1h",
      "search_clicks_24h",
      "search_clicks_168h",
      "search_clicks_720h"
    ],
    "price_rounding_policy": "ROUND_HALF_UP_2_DECIMAL",
    "pricing_rules_applied": false,
    "promotion_actions_generated": false,
    "random_seed": 42,
    "response_safety_policy": "LOW_TO_HIGH_CUMULATIVE_MINIMUM",
    "response_safety_tolerance": 1e-12,
    "technical_multiplier_high": 1.2,
    "technical_multiplier_low": 0.8,
    "thread_count": 22,
    "tie_band": {
      "absolute": 1e-08,
      "relative": 0.001
    },
    "tie_break_policy": [
      "CLOSEST_TO_CURRENT_PRICE",
      "LOWER_PRICE",
      "DETERMINISTIC_CANDIDATE_ORDER"
    ],
    "training_ratio_p01": 0.8929977619398718,
    "training_ratio_p99": 1.1173885792710216
  },
  "warnings_preserved": [
    "OPTIMIZER_BOUNDARY_HEAVY",
    "OPTIMIZER_STRONGLY_BOUNDARY_SEEKING",
    "HIGH_RESPONSE_GUARD_USAGE"
  ],
  "status": "PASS"
}

## 3. Rule source audit

Rows: **200**; active rows: **200**. Source is `dbo.Pricing_Rules` through a SELECT-only connector.

## 4. Percentage semantics

Canonical convention: **PERCENT_POINTS**.

## 5. Rule scope semantics

NULL ProductID/CategoryID/StoreID/Channel values are wildcards; CategoryID is joined from dbo.Product.

## 6. Effective-date semantics

Rules use the half-open `[EffectiveFrom, EffectiveTo)` interval.

## 7. Priority/specificity resolution

Selected policy: **None**. An unresolved policy is a hard blocker; no fallback precedence is used for automatic prices.

## 8. TRAIN rule-ID reconciliation

{
  "split": "train",
  "status": "BLOCKED",
  "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
  "policy_used_for_diagnostic_replay": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
  "semantics_status": "BLOCKED",
  "acceptance_threshold": 0.995,
  "metrics": {
    "rows": 24500,
    "exact_cent_match_rate": 0.9343265306122449,
    "absolute_delta_mean": 0.07198326530612244,
    "absolute_delta_median": 0.0,
    "absolute_delta_p95": 0.2504999999999923,
    "absolute_delta_max": 13.389999999999986,
    "constrained_decision_count": 4373,
    "constrained_decision_rate": 0.17848979591836733,
    "rule_violation_count": 0
  },
  "reference_full_historical_constrained_rate": 0.173,
  "reference_historical_rule_violations": 0
}

## 9. Rule constraint formulas

MinPrice, MaxPrice, minimum margin, maximum discount, and maximum movement are evaluated independently and intersected; invalid intervals require manual review.

## 10. Historical TRAIN replay

{
  "split": "train",
  "status": "BLOCKED",
  "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
  "policy_used_for_diagnostic_replay": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
  "semantics_status": "BLOCKED",
  "acceptance_threshold": 0.995,
  "metrics": {
    "rows": 24500,
    "exact_cent_match_rate": 0.9343265306122449,
    "absolute_delta_mean": 0.07198326530612244,
    "absolute_delta_median": 0.0,
    "absolute_delta_p95": 0.2504999999999923,
    "absolute_delta_max": 13.389999999999986,
    "constrained_decision_count": 4373,
    "constrained_decision_rate": 0.17848979591836733,
    "rule_violation_count": 0
  },
  "reference_full_historical_constrained_rate": 0.173,
  "reference_historical_rule_violations": 0
}

## 11. Historical VALIDATION replay

{
  "split": "validation",
  "status": "BLOCKED",
  "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
  "policy_used_for_diagnostic_replay": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
  "semantics_status": "BLOCKED",
  "acceptance_threshold": 0.995,
  "metrics": {
    "rows": 5250,
    "exact_cent_match_rate": 0.9363809523809524,
    "absolute_delta_mean": 0.07673714285714288,
    "absolute_delta_median": 0.0,
    "absolute_delta_p95": 0.21550000000000477,
    "absolute_delta_max": 13.860000000000014,
    "constrained_decision_count": 896,
    "constrained_decision_rate": 0.17066666666666666,
    "rule_violation_count": 0
  },
  "reference_full_historical_constrained_rate": 0.173,
  "reference_historical_rule_violations": 0
}

## 12. Promotion semantics

{
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

## 13. Promotion overlap/conflicts

Overlapping discounts never select the larger discount implicitly; conflicting overlaps produce review.

## 14. Promotion pricing mode

**CONTEXT_ONLY**.

## 15. Candidate augmentation

Only exact-cent rule/promotion boundaries inside the Phase 6 support envelope may be added, and they require a frozen-model scoring callback. No unsimulated boundary is written.

## 16. Business candidate filtering

Only candidates with `passes_all_pricing_rules == true` are eligible; Phase 6 objective and tie/materiality policy are preserved.

## 17. VALIDATION final recommendations

{
  "split": "validation",
  "decision_count": 5250,
  "candidate_rows": 47250,
  "same_price_rate": 1.0,
  "changed_price_rate": 0.0,
  "price_increase_rate": 0.0,
  "price_decrease_rate": 0.0,
  "hold_rate": 0.0,
  "rule_forced_change_rate": 0.0,
  "promotion_action_rate": 0.0,
  "markdown_action_rate": 0.0,
  "manual_review_rate": 1.0,
  "mean_price_change_pct": NaN,
  "median_price_change_pct": NaN,
  "phase6_upper_boundary_rate": 0.981904761904762,
  "phase7_upper_boundary_rate": 0.0,
  "phase7_minus_phase6_upper_boundary_delta": -0.981904761904762,
  "mean_expected_gross_profit_after": NaN,
  "final_rule_violation_count": 0,
  "outcomes_used": false,
  "diagnostics": {
    "rule": {
      "candidate_rows": 47250,
      "decisions": 5250,
      "rule_violation_rows": 47250,
      "rule_resolution_null_rate": 1.0
    },
    "decisions": 5250,
    "action_counts": {
      "MANUAL_REVIEW_RULE_CONFLICT": 5250
    },
    "constraint_impact": {
      "RULE_MIN_PRICE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_PRICE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MIN_MARGIN": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_DISCOUNT": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_PRICE_CHANGE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      }
    },
    "candidate_augmentation": {
      "status": "NOT_RUN_RULE_POLICY_BLOCKED",
      "added_candidates": 0,
      "out_of_support_boundaries": []
    }
  }
}

## 18. Frozen Phase 7 policy

{
  "phase": 7,
  "base_branch": "codex/phase1-data-audit",
  "base_git_sha": "6b0f4c990b3abcb28c5b60c11551ec6f6554c1a0",
  "phase7_implementation_git_sha": "6e6174589ce14bf8f2ca5a09537a09d578b415ce",
  "upstream": {
    "phase2_dataset_sha": "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2",
    "phase3_split_sha": "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d",
    "phase4_model_sha": "1af936a1905dcb21e3623392a16afbdbfc6b57c6866093fd6b33f12976dfd86d",
    "phase4_spec_sha": "6746428e9875726202e28a6adfc498421c09f4c129cf91d75b3ad2c0412a1f8d",
    "phase5_estimator_sha": "481e7de3c4fa8113ee5fd13e5c318b8bc2cb7dc2c652883119ee8608975978ba",
    "phase5_spec_sha": "cd7e8aa198fcbc886b893b5319439dfa381c192ede31b1f27ea11a93d14712f0",
    "phase6_manifest_sha": "b0881cd6e13ae8aa16fea8163a46cbdc40a2fabe66f3ca346539523b7f737b8a",
    "phase6_optimizer_spec_sha": "d18bf5783aee43443709848f224ad6f6158638150f7272bf43ea1a371f86177e",
    "candidate_surface_fingerprints": {
      "validation": "4c2e1729736d429f9f0c7910d4c1fc7d82fc6c850255112d6cf4cc63d41bb610",
      "test": "da959dac729757fe4cee76c309c92e85ae88948758c28ad3475b384c092e00ac"
    },
    "recommendation_fingerprints": {
      "validation": "2db3bb58f18aa0d21dd68b52721556e845a5a92c5babbe89b353f9818948edab",
      "test": "d7ec42c95eaa06766e0e2195d02d88fd4b1d56b1030fb23bcf130728aa834f52"
    }
  },
  "rule_percentage_convention": "PERCENT_POINTS",
  "rule_effective_date_convention": "[EffectiveFrom, EffectiveTo)",
  "rule_precedence_policy": null,
  "scope_wildcard_policy": "NULL_APPLIES_TO_ALL",
  "rule_formulas": {
    "MinPrice": "floor",
    "MaxPrice": "ceiling",
    "MinMarginPct": "CostPrice/(1-MinMarginFraction)",
    "MaxDiscountPct": "BasePrice*(1-MaxDiscountFraction)",
    "MaxPriceChangePct": "CurrentPrice*(1 +/- MaxPriceChangeFraction)"
  },
  "promotion_pricing_mode": "CONTEXT_ONLY",
  "promotion_season_semantics": {
    "observed_values": [
      "All",
      "Fall",
      "Spring",
      "Summer",
      "Winter"
    ],
    "generic_values": [
      "All"
    ],
    "seasonal_values": [
      "Fall",
      "Spring",
      "Summer",
      "Winter"
    ],
    "semantics": "SOURCE_NON_GENERIC_VALUES",
    "calendar_mapping_used": false
  },
  "inventory_snapshot_policy": "CURRENT_ONLY",
  "inventory_status_map": {
    "In Stock": "NORMAL"
  },
  "slow_moving_thresholds": {
    "metric": "product_store_sales_30d",
    "fallback_metric": "product_sales_30d",
    "quantile": 0.25,
    "minimum_category_rows": 100,
    "global_threshold": 0.0,
    "category_thresholds": {
      "CAT000011": 0.0,
      "CAT000012": 0.0,
      "CAT000013": 0.0,
      "CAT000014": 0.0,
      "CAT000015": 0.0,
      "CAT000016": 0.0,
      "CAT000017": 0.0,
      "CAT000018": 0.0,
      "CAT000019": 0.0,
      "CAT000020": 0.0,
      "CAT000021": 0.0,
      "CAT000022": 0.0,
      "CAT000023": 0.0,
      "CAT000024": 0.0,
      "CAT000025": 0.0,
      "CAT000026": 0.0,
      "CAT000027": 0.0,
      "CAT000028": 0.0,
      "CAT000029": 0.0,
      "CAT000030": 0.0,
      "CAT000031": 0.0,
      "CAT000032": 0.0,
      "CAT000033": 0.0,
      "CAT000034": 0.0,
      "CAT000035": 0.0,
      "CAT000036": 0.0,
      "CAT000037": 0.0,
      "CAT000038": 0.0,
      "CAT000039": 0.0,
      "CAT000040": 0.0,
      "CAT000041": 0.0,
      "CAT000042": 0.0,
      "CAT000043": 0.0,
      "CAT000044": 0.0,
      "CAT000045": 0.0,
      "CAT000046": 0.0,
      "CAT000047": 0.0,
      "CAT000048": 0.0,
      "CAT000049": 0.0,
      "CAT000050": 0.0,
      "CAT000051": 0.0,
      "CAT000052": 0.0,
      "CAT000053": 0.0,
      "CAT000054": 0.0,
      "CAT000055": 0.0,
      "CAT000056": 0.0,
      "CAT000057": 0.0,
      "CAT000058": 0.0,
      "CAT000059": 0.0,
      "CAT000060": 0.0,
      "CAT000061": 0.0,
      "CAT000062": 0.0,
      "CAT000063": 0.0,
      "CAT000064": 0.0,
      "CAT000065": 0.0,
      "CAT000066": 0.0,
      "CAT000067": 0.0,
      "CAT000068": 0.0,
      "CAT000069": 0.0,
      "CAT000070": 0.0,
      "CAT000071": 0.0,
      "CAT000072": 0.0,
      "CAT000073": 0.0,
      "CAT000074": 0.0,
      "CAT000075": 0.0,
      "CAT000076": 0.0,
      "CAT000077": 0.0,
      "CAT000078": 0.0,
      "CAT000079": 0.0,
      "CAT000080": 0.0
    },
    "category_support": {
      "CAT000011": 665,
      "CAT000012": 703,
      "CAT000013": 457,
      "CAT000014": 648,
      "CAT000015": 470,
      "CAT000016": 474,
      "CAT000017": 607,
      "CAT000018": 481,
      "CAT000019": 688,
      "CAT000020": 386,
      "CAT000021": 610,
      "CAT000022": 424,
      "CAT000023": 315,
      "CAT000024": 623,
      "CAT000025": 262,
      "CAT000026": 276,
      "CAT000027": 300,
      "CAT000028": 263,
      "CAT000029": 277,
      "CAT000030": 334,
      "CAT000031": 243,
      "CAT000032": 226,
      "CAT000033": 253,
      "CAT000034": 346,
      "CAT000035": 222,
      "CAT000036": 235,
      "CAT000037": 403,
      "CAT000038": 369,
      "CAT000039": 354,
      "CAT000040": 289,
      "CAT000041": 426,
      "CAT000042": 332,
      "CAT000043": 519,
      "CAT000044": 336,
      "CAT000045": 499,
      "CAT000046": 405,
      "CAT000047": 459,
      "CAT000048": 510,
      "CAT000049": 384,
      "CAT000050": 485,
      "CAT000051": 358,
      "CAT000052": 560,
      "CAT000053": 145,
      "CAT000054": 161,
      "CAT000055": 101,
      "CAT000056": 184,
      "CAT000057": 500,
      "CAT000058": 235,
      "CAT000059": 222,
      "CAT000060": 163,
      "CAT000061": 235,
      "CAT000062": 279,
      "CAT000063": 181,
      "CAT000064": 602,
      "CAT000065": 600,
      "CAT000066": 254,
      "CAT000067": 171,
      "CAT000068": 112,
      "CAT000069": 186,
      "CAT000070": 174,
      "CAT000071": 102,
      "CAT000072": 132,
      "CAT000073": 258,
      "CAT000074": 443,
      "CAT000075": 275,
      "CAT000076": 147,
      "CAT000077": 419,
      "CAT000078": 200,
      "CAT000079": 277,
      "CAT000080": 266
    },
    "source_split": "TRAIN",
    "policy_type": "RELATIVE_SYNTHETIC_POC_POLICY"
  },
  "markdown_policy": "seasonal + slow-moving + overstock + positive available; no expiry logic",
  "action_precedence": [
    "OUT_OF_STOCK / INVENTORY UNAVAILABLE",
    "RULE CONFLICT / NO COMPLIANT CANDIDATE",
    "ACTIVE PROMOTION COMMITMENT / PROMOTION CONFLICT",
    "CURRENT seasonal slow-moving markdown policy",
    "NORMAL rule-compliant model pricing"
  ],
  "phase6_tie_policy": {
    "absolute": 1e-08,
    "relative": 0.001,
    "break": [
      "CLOSEST_TO_CURRENT_PRICE",
      "LOWER_PRICE",
      "DETERMINISTIC_CANDIDATE_ORDER"
    ]
  },
  "materiality_relative_expected_profit_uplift": 0.005,
  "max_current_context_age_days": 30,
  "ADVISORY_ONLY": true,
  "AUTO_WRITEBACK": false,
  "frozen_business_policy_spec_sha256": "209edef4f5bb2a1512066388b404cff88df245fabf82ce87b1b2502153308be3"
}

## 19. TEST policy replay

{
  "split": "test",
  "status": "BLOCKED",
  "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
  "policy_used_for_diagnostic_replay": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
  "semantics_status": "BLOCKED",
  "acceptance_threshold": 0.995,
  "metrics": {
    "rows": 5250,
    "exact_cent_match_rate": 0.9335238095238095,
    "absolute_delta_mean": 0.09208380952380966,
    "absolute_delta_median": 0.0,
    "absolute_delta_p95": 0.2700000000000031,
    "absolute_delta_max": 13.360000000000014,
    "constrained_decision_count": 886,
    "constrained_decision_rate": 0.16876190476190475,
    "rule_violation_count": 0
  },
  "reference_full_historical_constrained_rate": 0.173,
  "reference_historical_rule_violations": 0
}

## 20. TEST final recommendations

{
  "split": "test",
  "decision_count": 5250,
  "candidate_rows": 47250,
  "same_price_rate": 1.0,
  "changed_price_rate": 0.0,
  "price_increase_rate": 0.0,
  "price_decrease_rate": 0.0,
  "hold_rate": 0.0,
  "rule_forced_change_rate": 0.0,
  "promotion_action_rate": 0.0,
  "markdown_action_rate": 0.0,
  "manual_review_rate": 1.0,
  "mean_price_change_pct": NaN,
  "median_price_change_pct": NaN,
  "phase6_upper_boundary_rate": 0.9758095238095238,
  "phase7_upper_boundary_rate": 0.0,
  "phase7_minus_phase6_upper_boundary_delta": -0.9758095238095238,
  "mean_expected_gross_profit_after": NaN,
  "final_rule_violation_count": 0,
  "outcomes_used": false,
  "diagnostics": {
    "rule": {
      "candidate_rows": 47250,
      "decisions": 5250,
      "rule_violation_rows": 47250,
      "rule_resolution_null_rate": 1.0
    },
    "decisions": 5250,
    "action_counts": {
      "MANUAL_REVIEW_RULE_CONFLICT": 5250
    },
    "constraint_impact": {
      "RULE_MIN_PRICE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_PRICE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MIN_MARGIN": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_DISCOUNT": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_PRICE_CHANGE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      }
    },
    "candidate_augmentation": {
      "status": "NOT_RUN_RULE_POLICY_BLOCKED",
      "added_candidates": 0,
      "out_of_support_boundaries": []
    }
  }
}

## 21. Final rule violations

Count: **0**.

## 22. Phase 6 vs Phase 7 comparison

Validation/test comparison is retained in each business summary, including Phase 6 and Phase 7 support-boundary rates.

## 23. Boundary behavior

The live source run records the boundary-heavy behavior rather than tuning it away.

## 24. Inventory snapshot audit

{
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

## 25. Current inventory mode

{
  "mode": "CURRENT_INVENTORY_MODE",
  "as_of_date": "2025-12-31",
  "eligible_current_contexts": 1829,
  "stale_contexts": 595,
  "inventory_matched": 1829,
  "no_price_out_of_stock_decisions": 0,
  "promotion_actions": 0,
  "markdown_actions": 234,
  "manual_reviews": 1829,
  "diagnostics": {
    "rule": {
      "candidate_rows": 16461,
      "decisions": 1829,
      "rule_violation_rows": 16461,
      "rule_resolution_null_rate": 1.0
    },
    "decisions": 1829,
    "action_counts": {
      "MANUAL_REVIEW_RULE_CONFLICT": 1829
    },
    "constraint_impact": {
      "RULE_MIN_PRICE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_PRICE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MIN_MARGIN": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_DISCOUNT": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      },
      "RULE_MAX_PRICE_CHANGE": {
        "decisions_affected": 0,
        "candidate_rows_filtered": 0,
        "price_delta_mean": 0.0
      }
    },
    "candidate_augmentation": {
      "status": "NOT_RUN_RULE_POLICY_BLOCKED",
      "added_candidates": 0,
      "out_of_support_boundaries": []
    }
  }
}

## 26. Slow-moving thresholds

{
  "metric": "product_store_sales_30d",
  "fallback_metric": "product_sales_30d",
  "quantile": 0.25,
  "minimum_category_rows": 100,
  "global_threshold": 0.0,
  "category_thresholds": {
    "CAT000011": 0.0,
    "CAT000012": 0.0,
    "CAT000013": 0.0,
    "CAT000014": 0.0,
    "CAT000015": 0.0,
    "CAT000016": 0.0,
    "CAT000017": 0.0,
    "CAT000018": 0.0,
    "CAT000019": 0.0,
    "CAT000020": 0.0,
    "CAT000021": 0.0,
    "CAT000022": 0.0,
    "CAT000023": 0.0,
    "CAT000024": 0.0,
    "CAT000025": 0.0,
    "CAT000026": 0.0,
    "CAT000027": 0.0,
    "CAT000028": 0.0,
    "CAT000029": 0.0,
    "CAT000030": 0.0,
    "CAT000031": 0.0,
    "CAT000032": 0.0,
    "CAT000033": 0.0,
    "CAT000034": 0.0,
    "CAT000035": 0.0,
    "CAT000036": 0.0,
    "CAT000037": 0.0,
    "CAT000038": 0.0,
    "CAT000039": 0.0,
    "CAT000040": 0.0,
    "CAT000041": 0.0,
    "CAT000042": 0.0,
    "CAT000043": 0.0,
    "CAT000044": 0.0,
    "CAT000045": 0.0,
    "CAT000046": 0.0,
    "CAT000047": 0.0,
    "CAT000048": 0.0,
    "CAT000049": 0.0,
    "CAT000050": 0.0,
    "CAT000051": 0.0,
    "CAT000052": 0.0,
    "CAT000053": 0.0,
    "CAT000054": 0.0,
    "CAT000055": 0.0,
    "CAT000056": 0.0,
    "CAT000057": 0.0,
    "CAT000058": 0.0,
    "CAT000059": 0.0,
    "CAT000060": 0.0,
    "CAT000061": 0.0,
    "CAT000062": 0.0,
    "CAT000063": 0.0,
    "CAT000064": 0.0,
    "CAT000065": 0.0,
    "CAT000066": 0.0,
    "CAT000067": 0.0,
    "CAT000068": 0.0,
    "CAT000069": 0.0,
    "CAT000070": 0.0,
    "CAT000071": 0.0,
    "CAT000072": 0.0,
    "CAT000073": 0.0,
    "CAT000074": 0.0,
    "CAT000075": 0.0,
    "CAT000076": 0.0,
    "CAT000077": 0.0,
    "CAT000078": 0.0,
    "CAT000079": 0.0,
    "CAT000080": 0.0
  },
  "category_support": {
    "CAT000011": 665,
    "CAT000012": 703,
    "CAT000013": 457,
    "CAT000014": 648,
    "CAT000015": 470,
    "CAT000016": 474,
    "CAT000017": 607,
    "CAT000018": 481,
    "CAT000019": 688,
    "CAT000020": 386,
    "CAT000021": 610,
    "CAT000022": 424,
    "CAT000023": 315,
    "CAT000024": 623,
    "CAT000025": 262,
    "CAT000026": 276,
    "CAT000027": 300,
    "CAT000028": 263,
    "CAT000029": 277,
    "CAT000030": 334,
    "CAT000031": 243,
    "CAT000032": 226,
    "CAT000033": 253,
    "CAT000034": 346,
    "CAT000035": 222,
    "CAT000036": 235,
    "CAT000037": 403,
    "CAT000038": 369,
    "CAT000039": 354,
    "CAT000040": 289,
    "CAT000041": 426,
    "CAT000042": 332,
    "CAT000043": 519,
    "CAT000044": 336,
    "CAT000045": 499,
    "CAT000046": 405,
    "CAT000047": 459,
    "CAT000048": 510,
    "CAT000049": 384,
    "CAT000050": 485,
    "CAT000051": 358,
    "CAT000052": 560,
    "CAT000053": 145,
    "CAT000054": 161,
    "CAT000055": 101,
    "CAT000056": 184,
    "CAT000057": 500,
    "CAT000058": 235,
    "CAT000059": 222,
    "CAT000060": 163,
    "CAT000061": 235,
    "CAT000062": 279,
    "CAT000063": 181,
    "CAT000064": 602,
    "CAT000065": 600,
    "CAT000066": 254,
    "CAT000067": 171,
    "CAT000068": 112,
    "CAT000069": 186,
    "CAT000070": 174,
    "CAT000071": 102,
    "CAT000072": 132,
    "CAT000073": 258,
    "CAT000074": 443,
    "CAT000075": 275,
    "CAT000076": 147,
    "CAT000077": 419,
    "CAT000078": 200,
    "CAT000079": 277,
    "CAT000080": 266
  },
  "source_split": "TRAIN",
  "policy_type": "RELATIVE_SYNTHETIC_POC_POLICY"
}

## 27. Seasonal semantics

Season is treated as source metadata; no invented calendar mapping or promotion-season requirement is applied.

## 28. Markdown decisions

Markdown is seasonal + slow-moving + overstock with positive available quantity and low-stock suppression. Expiry/perishability logic is forbidden.

## 29. Current snapshot recommendation distribution

See `current_inventory_summary.json` and the current decision Parquet artifact.

## 30. Manual review

{
  "validation": 1.0,
  "test": 1.0
}

## 31. Reproducibility

{
  "rule_resolution_mismatches": 0,
  "final_price_mismatches": 0,
  "action_mismatches": 0,
  "max_economic_delta": 0.0,
  "status": "PASS"
}

## 32. Compute

{
  "rule_resolution_seconds": 29.662137900013477,
  "promotion_resolution_seconds": 59.05922799999826,
  "inventory_policy_seconds": 0.017656899988651276,
  "model_augmentation_inference_seconds": 0.0,
  "final_selection_seconds": 172.33161560000735,
  "total_seconds": 265.2060458000051
}

## 33. Known limitations

Historical inventory is unavailable by contract; current inventory is a single 2025-12-31 snapshot. Outcome backtesting is deferred to Phase 8.

## 34. Phase 8 handoff

Phase 8 must not begin until this Phase 7 verdict is independently reviewed and explicitly approved.

## 35. PASS / PASS_WITH_WARNINGS / BLOCKED

**BLOCKED**.

## 36. Final recommendation

**DO_NOT_PROCEED_TO_PHASE_8**
