# Phase 8 Acceptance Report

## 1. Executive verdict

**PASS_WITH_WARNINGS** — PROCEED_TO_PHASE_9.

## 2. Upstream Phase 7 verification

{
  "status": "PASS",
  "blockers": [],
  "phase7_result": "PASS_WITH_WARNINGS",
  "phase7_frozen_policy": "P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
  "final_rule_violation_count": 0,
  "rows": {
    "validation": 5250,
    "test": 5250,
    "current": 1829
  },
  "fingerprints": {
    "manifest_sha256": "8d79b5bee6a8b073f06508550cce2e2f35747a157d891c8cddaf45e9ab3050c6",
    "frozen_policy_sha256": "74ee5dc91242ad14e2afa65088ffb6f342483816ca2da2e7810801aa20f1cf8c",
    "validation_decisions_sha256": "339c95141eda615175a52470244ad95608c71ea389cd21ae9702776a452dde56",
    "test_decisions_sha256": "4b81635f2794488c923a2334db2d93759abed6e5fdd78e2f9fa7a718135c48fa",
    "current_decisions_sha256": "71c3a73e93c78611c4d6af09ce3105981bd00be4900aee53babbd55b9a3d8563"
  },
  "phase7_manifest_base_git_sha": "6b0f4c990b3abcb28c5b60c11551ec6f6554c1a0",
  "phase7_evidence_git_sha": "1518eeb619db1d4ebda8208eb0fa9601829d0fb4",
  "phase7_upstream": {
    "candidate_surface_fingerprints": {
      "test": "da959dac729757fe4cee76c309c92e85ae88948758c28ad3475b384c092e00ac",
      "validation": "4c2e1729736d429f9f0c7910d4c1fc7d82fc6c850255112d6cf4cc63d41bb610"
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
    "manifest_path": "artifacts\\phase6\\phase6_manifest.json",
    "manifest_sha256": "b0881cd6e13ae8aa16fea8163a46cbdc40a2fabe66f3ca346539523b7f737b8a",
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
    "recommendation_fingerprints": {
      "test": "d7ec42c95eaa06766e0e2195d02d88fd4b1d56b1030fb23bcf130728aa834f52",
      "validation": "2db3bb58f18aa0d21dd68b52721556e845a5a92c5babbe89b353f9818948edab"
    },
    "spec_path": "artifacts\\phase6\\frozen_optimizer_spec.json",
    "spec_sha256": "d18bf5783aee43443709848f224ad6f6158638150f7272bf43ea1a371f86177e",
    "status": "PASS",
    "warnings_preserved": [
      "OPTIMIZER_BOUNDARY_HEAVY",
      "OPTIMIZER_STRONGLY_BOUNDARY_SEEKING",
      "HIGH_RESPONSE_GUARD_USAGE"
    ]
  }
}

## 3. Evaluation protocol freeze

Frozen spec SHA: `9c8ceb607834057ce158ab94c3d22264d52e387629be421b79f1550b2101a04c`. The spec was
written before the single TEST outcome read.

## 4. TEST outcome access control

{
  "test_outcome_access_count": 1,
  "evaluation_spec_frozen_before_test": true,
  "test_used_for_training": false,
  "test_used_for_hpo": false,
  "test_used_for_model_selection": false,
  "test_used_for_rule_selection": false,
  "test_used_for_candidate_grid_selection": false,
  "test_used_for_threshold_selection": false,
  "evaluation_spec_frozen_at": "2026-08-19T07:09:48.143058+00:00",
  "test_outcomes_loaded_at": "2026-08-19T07:09:48.189523+00:00",
  "source": {
    "status": "FROZEN_ARTIFACT_REUSE",
    "rows": 5250,
    "sql_select_only": false,
    "outcome_reread": false,
    "source_path": "artifacts\\phase8\\test_factual_backtest.parquet",
    "source_sha256": "347aa556c7fa9a0f61748c80c890a09a4132fa2d3098ce83865873b9abaee9f4"
  }
}

## 5. Outcome integrity / 6. Revenue consistency

{
  "validation": {
    "join": {
      "expected_rows": 5250,
      "rows": 5250,
      "unique_ids": 5250,
      "duplicate_ids": 0,
      "missing_ids": 0,
      "unexpected_ids": 0,
      "one_to_one": true
    },
    "quality": {
      "rows": 5250,
      "purchased_flag_values": [
        0,
        1
      ],
      "invalid_purchased_flag_rows": 0,
      "invalid_quantity_rows": 0,
      "invalid_revenue_rows": 0,
      "invalid_applied_price_rows": 0,
      "contradictions": {
        "nonpurchase_positive_quantity": 0,
        "nonpurchase_positive_revenue": 0,
        "purchase_zero_quantity": 0
      },
      "contradictory_rows": 0,
      "status": "PASS"
    },
    "revenue": {
      "tolerance": 0.01,
      "exact_cent_match_rate": 1.0,
      "mean_delta": 3.248195363474744e-17,
      "p95_absolute_delta": 0.0,
      "max_absolute_delta": 1.1368683772161603e-13,
      "mismatch_count": 0,
      "mismatch_rate": 0.0,
      "status": "PASS"
    },
    "gross_profit_formula": {
      "tolerance": 1e-09,
      "rows": 5250,
      "exact_match_rate": 1.0,
      "mean_delta": -3.315866100213801e-17,
      "p95_absolute_delta": 0.0,
      "max_absolute_delta": 5.684341886080802e-14,
      "mismatch_count": 0,
      "status": "PASS"
    }
  },
  "test": {
    "join": {
      "expected_rows": 5250,
      "rows": 5250,
      "unique_ids": 5250,
      "duplicate_ids": 0,
      "missing_ids": 0,
      "unexpected_ids": 0,
      "one_to_one": true
    },
    "quality": {
      "rows": 5250,
      "purchased_flag_values": [
        0,
        1
      ],
      "invalid_purchased_flag_rows": 0,
      "invalid_quantity_rows": 0,
      "invalid_revenue_rows": 0,
      "invalid_applied_price_rows": 0,
      "contradictions": {
        "nonpurchase_positive_quantity": 0,
        "nonpurchase_positive_revenue": 0,
        "purchase_zero_quantity": 0
      },
      "contradictory_rows": 0,
      "status": "PASS"
    },
    "revenue": {
      "tolerance": 0.01,
      "exact_cent_match_rate": 1.0,
      "mean_delta": -5.413658939124573e-17,
      "p95_absolute_delta": 0.0,
      "max_absolute_delta": 2.2737367544323206e-13,
      "mismatch_count": 0,
      "mismatch_rate": 0.0,
      "status": "PASS"
    },
    "gross_profit_formula": {
      "tolerance": 1e-09,
      "rows": 5250,
      "exact_match_rate": 1.0,
      "mean_delta": 9.000207986294602e-17,
      "p95_absolute_delta": 0.0,
      "max_absolute_delta": 2.2737367544323206e-13,
      "mismatch_count": 0,
      "status": "PASS"
    }
  },
  "observed_gross_profit_definition": "ActualRevenue - (Product.CostPrice * QuantityPurchased)",
  "cost_limitation": "Static Product.CostPrice is used because historical cost snapshots are unavailable."
}

## 7–14. Factual evaluation

{
  "purchase": {
    "rows": 5250,
    "positive_rate": 0.18514285714285714,
    "roc_auc": 0.6093393176304454,
    "average_precision": 0.24523451977509367,
    "log_loss": 0.46908721778657386,
    "brier_score": 0.14786924715837632,
    "top_decile_lift": 1.491769547325103,
    "ece": 0.008380833821411722,
    "calibration_rows": [
      {
        "decile": 1,
        "decision_count": 3,
        "mean_predicted_probability": 0.09707152172777168,
        "observed_purchase_rate": 0.3333333333333333
      },
      {
        "decile": 2,
        "decision_count": 3674,
        "mean_predicted_probability": 0.15028034842969323,
        "observed_purchase_rate": 0.15568862275449102
      },
      {
        "decile": 3,
        "decision_count": 1522,
        "mean_predicted_probability": 0.24298149663370366,
        "observed_purchase_rate": 0.25492772667542707
      },
      {
        "decile": 4,
        "decision_count": 51,
        "mean_predicted_probability": 0.3184005908781325,
        "observed_purchase_rate": 0.21568627450980393
      }
    ]
  },
  "demand": {
    "aggregate_observed": 1260.0,
    "aggregate_predicted": 1225.461176694419,
    "aggregate_delta": -34.53882330558099,
    "aggregate_error_pct": -0.02741176452823888,
    "mae": 0.37985884280541526,
    "rmse": 0.5694084073253828,
    "wape": 1.582745178355897,
    "mean_bias": -0.006578823486777299,
    "poisson_deviance": 0.8349210360449312
  },
  "revenue": {
    "aggregate_observed": 192321.13,
    "aggregate_predicted": 184788.02956532539,
    "aggregate_delta": -7533.1004346746195,
    "aggregate_error_pct": -0.03916938526034357,
    "mae": 57.58664659313121,
    "rmse": 104.01525649413237,
    "wape": 1.5720056065287202,
    "mean_bias": -1.434876273271355
  },
  "gross_profit": {
    "aggregate_observed": 83046.97,
    "aggregate_predicted": 79250.104728012,
    "aggregate_delta": -3796.8652719880047,
    "aggregate_error_pct": -0.04571949189703134,
    "mae": 24.710188804153457,
    "rmse": 44.40484921452553,
    "wape": 1.5621098665225914,
    "mean_bias": -0.7232124327596203
  },
  "observed_gross_margin_rate": 0.43181407056000554,
  "predicted_historical_gross_margin_rate": 0.4288703381622232,
  "aggregate_units_error_pct": -0.02741176452823888,
  "aggregate_revenue_error_pct": -0.03916938526034357,
  "aggregate_gross_profit_error_pct": -0.04571949189703134
}

## 15–23. Scenario economics and governance cost

{
  "S0_HISTORICAL_APPLIED": {
    "scenario": "S0_HISTORICAL_APPLIED",
    "label": "historical factual prediction at observed price",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1225.461176694419,
    "aggregate_expected_revenue": 184788.02956532539,
    "aggregate_expected_gross_profit": 79250.104728012,
    "gross_margin_rate": 0.4288703381622232,
    "mean_price": 150.7057180952381,
    "median_price": 132.675,
    "price_increase_rate": 0.0,
    "price_decrease_rate": 0.0,
    "hold_rate": 1.0,
    "mean_price_change_pct": 0.0,
    "median_price_change_pct": 0.0,
    "factual_or_counterfactual": "factual_prediction"
  },
  "S1_CURRENT_PRICE": {
    "scenario": "S1_CURRENT_PRICE",
    "label": "model-implied scenario estimate",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1209.293336386254,
    "aggregate_expected_revenue": 178069.79657353478,
    "aggregate_expected_gross_profit": 73956.0129525392,
    "gross_margin_rate": 0.41532036524789706,
    "mean_price": 148.1118761904762,
    "median_price": 129.18,
    "price_increase_rate": 0.304952380952381,
    "price_decrease_rate": 0.5481904761904762,
    "hold_rate": 0.14685714285714285,
    "mean_price_change_pct": -0.01817860193346408,
    "median_price_change_pct": -0.01700511380499054,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S2_PHASE6_MODEL_OPTIMAL": {
    "scenario": "S2_PHASE6_MODEL_OPTIMAL",
    "label": "model-implied scenario estimate",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1158.8265285696234,
    "aggregate_expected_revenue": 186997.14279058683,
    "aggregate_expected_gross_profit": 87601.06025970247,
    "gross_margin_rate": 0.4684620254214503,
    "mean_price": 162.6966457142857,
    "median_price": 142.1,
    "price_increase_rate": 0.8636190476190476,
    "price_decrease_rate": 0.13428571428571429,
    "hold_rate": 0.0020952380952380953,
    "mean_price_change_pct": 0.07892394713202425,
    "median_price_change_pct": 0.07467536721626919,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S3_PHASE7_FINAL_AUTOMATIC": {
    "scenario": "S3_PHASE7_FINAL_AUTOMATIC",
    "label": "model-implied scenario estimate",
    "rows": 5175,
    "missing_price_rows": 75,
    "aggregate_expected_units": 1145.2622360745604,
    "aggregate_expected_revenue": 183014.3161701461,
    "aggregate_expected_gross_profit": 84966.10135086284,
    "gross_margin_rate": 0.4642593165874025,
    "mean_price": 161.21689661835748,
    "median_price": 140.32,
    "price_increase_rate": 0.7694685990338165,
    "price_decrease_rate": 0.22743961352657005,
    "hold_rate": 0.0030917874396135265,
    "mean_price_change_pct": 0.07101919974198002,
    "median_price_change_pct": 0.06679519165343599,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S4_PHASE7_WITH_HISTORICAL_FALLBACK": {
    "scenario": "S4_PHASE7_WITH_HISTORICAL_FALLBACK",
    "label": "model-implied scenario estimate",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1163.7939080018582,
    "aggregate_expected_revenue": 186263.71929527677,
    "aggregate_expected_gross_profit": 86400.47319711858,
    "gross_margin_rate": 0.46386098980527285,
    "mean_price": 161.3194304761905,
    "median_price": 140.58,
    "price_increase_rate": 0.7584761904761905,
    "price_decrease_rate": 0.2241904761904762,
    "hold_rate": 0.017333333333333333,
    "mean_price_change_pct": 0.07000463974566602,
    "median_price_change_pct": 0.06366339195255057,
    "factual_or_counterfactual": "counterfactual_model_implied"
  }
}

{
  "S0_HISTORICAL_APPLIED": {
    "scenario": "S0_HISTORICAL_APPLIED",
    "label": "historical factual prediction at observed price",
    "rows": 5175,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1206.929504767121,
    "aggregate_expected_revenue": 181538.62644019473,
    "aggregate_expected_gross_profit": 77815.73288175625,
    "gross_margin_rate": 0.4286455968498336,
    "mean_price": 150.44936231884057,
    "median_price": 132.35,
    "price_increase_rate": 0.0,
    "price_decrease_rate": 0.0,
    "hold_rate": 1.0,
    "mean_price_change_pct": 0.0,
    "median_price_change_pct": 0.0,
    "factual_or_counterfactual": "factual_prediction"
  },
  "S1_CURRENT_PRICE": {
    "scenario": "S1_CURRENT_PRICE",
    "label": "model-implied scenario estimate",
    "rows": 5175,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1191.163157565345,
    "aggregate_expected_revenue": 174952.91684146834,
    "aggregate_expected_gross_profit": 72605.03386567248,
    "gross_margin_rate": 0.4149975614951463,
    "mean_price": 147.84114396135266,
    "median_price": 129.04,
    "price_increase_rate": 0.3045410628019324,
    "price_decrease_rate": 0.5489855072463768,
    "hold_rate": 0.14647342995169083,
    "mean_price_change_pct": -0.018260009946182713,
    "median_price_change_pct": -0.017668939863608082,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S2_PHASE6_MODEL_OPTIMAL": {
    "scenario": "S2_PHASE6_MODEL_OPTIMAL",
    "label": "model-implied scenario estimate",
    "rows": 5175,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1141.5734573855752,
    "aggregate_expected_revenue": 183735.79395386198,
    "aggregate_expected_gross_profit": 86018.21349884434,
    "gross_margin_rate": 0.4681625264614713,
    "mean_price": 162.3955458937198,
    "median_price": 141.94,
    "price_increase_rate": 0.8624154589371981,
    "price_decrease_rate": 0.13545893719806762,
    "hold_rate": 0.0021256038647342996,
    "mean_price_change_pct": 0.07881857970815584,
    "median_price_change_pct": 0.0742482781790694,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S3_PHASE7_FINAL_AUTOMATIC": {
    "scenario": "S3_PHASE7_FINAL_AUTOMATIC",
    "label": "model-implied scenario estimate",
    "rows": 5175,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1145.2622360745604,
    "aggregate_expected_revenue": 183014.3161701461,
    "aggregate_expected_gross_profit": 84966.10135086284,
    "gross_margin_rate": 0.4642593165874025,
    "mean_price": 161.21689661835748,
    "median_price": 140.32,
    "price_increase_rate": 0.7694685990338165,
    "price_decrease_rate": 0.22743961352657005,
    "hold_rate": 0.0030917874396135265,
    "mean_price_change_pct": 0.07101919974198002,
    "median_price_change_pct": 0.06679519165343599,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S4_PHASE7_WITH_HISTORICAL_FALLBACK": {
    "scenario": "S4_PHASE7_WITH_HISTORICAL_FALLBACK",
    "label": "model-implied scenario estimate",
    "rows": 5175,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1145.2622360745604,
    "aggregate_expected_revenue": 183014.3161701461,
    "aggregate_expected_gross_profit": 84966.10135086284,
    "gross_margin_rate": 0.4642593165874025,
    "mean_price": 161.21689661835748,
    "median_price": 140.32,
    "price_increase_rate": 0.7694685990338165,
    "price_decrease_rate": 0.22743961352657005,
    "hold_rate": 0.0030917874396135265,
    "mean_price_change_pct": 0.07101919974198002,
    "median_price_change_pct": 0.06679519165343599,
    "factual_or_counterfactual": "counterfactual_model_implied"
  }
}
{
  "S1_CURRENT_PRICE": {
    "cohort": "S3_PHASE7_FINAL_AUTOMATIC",
    "rows": 5175
  },
  "S2_PHASE6_MODEL_OPTIMAL": {
    "cohort": "S3_PHASE7_FINAL_AUTOMATIC",
    "rows": 5175
  },
  "S3_PHASE7_FINAL_AUTOMATIC": {
    "cohort": "S3_PHASE7_FINAL_AUTOMATIC",
    "rows": 5175
  },
  "S4_PHASE7_WITH_HISTORICAL_FALLBACK": {
    "cohort": "ALL_DECISION_ROWS",
    "rows": 5250
  }
}

{
  "S1_CURRENT_PRICE": {
    "expected_units_delta": -15.766347201775943,
    "expected_units_delta_pct": -0.013063188147693916,
    "expected_revenue_delta": -6585.709598726389,
    "expected_revenue_delta_pct": -0.03627718093865801,
    "expected_gross_profit_delta": -5210.699016083774,
    "expected_gross_profit_delta_pct": -0.06696202455616032
  },
  "S2_PHASE6_MODEL_OPTIMAL": {
    "expected_units_delta": -65.35604738154575,
    "expected_units_delta_pct": -0.0541506750173916,
    "expected_revenue_delta": 2197.1675136672566,
    "expected_revenue_delta_pct": 0.012103030394972618,
    "expected_gross_profit_delta": 8202.480617088091,
    "expected_gross_profit_delta_pct": 0.1054090260841217
  },
  "S3_PHASE7_FINAL_AUTOMATIC": {
    "expected_units_delta": -61.66726869256058,
    "expected_units_delta_pct": -0.051094341839343284,
    "expected_revenue_delta": 1475.6897299513803,
    "expected_revenue_delta_pct": 0.00812879197605654,
    "expected_gross_profit_delta": 7150.368469106586,
    "expected_gross_profit_delta_pct": 0.09188846784970622
  },
  "S4_PHASE7_WITH_HISTORICAL_FALLBACK": {
    "expected_units_delta": -61.66726869256081,
    "expected_units_delta_pct": -0.05032168286138873,
    "expected_revenue_delta": 1475.6897299513803,
    "expected_revenue_delta_pct": 0.007985851320686882,
    "expected_gross_profit_delta": 7150.368469106586,
    "expected_gross_profit_delta_pct": 0.09022535040990544
  }
}

## 24–28. Boundary behavior and overlap

{
  "price_distribution": {
    "rows": 5175,
    "price_increase_rate": 0.9943961352657005,
    "price_decrease_rate": 0.00463768115942029,
    "hold_rate": 0.000966183574879227,
    "mean_price_change_pct": 0.09100111515245198,
    "median_price_change_pct": 0.09998472738380078,
    "p05_price_change_pct": 0.07495324413753407,
    "p25_price_change_pct": 0.07502145922746789,
    "p75_price_change_pct": 0.10001068136339919,
    "p95_price_change_pct": 0.10005108013975597
  },
  "boundary_rates": {
    "tolerance": 0.005,
    "rows": 5250,
    "phase6_upper_grid_boundary_rate": 0.9756190476190476,
    "phase6_lower_grid_boundary_rate": 0.00019047619047619048,
    "phase7_upper_grid_boundary_rate": 0.6892753623188406,
    "phase7_lower_grid_boundary_rate": 0.0001932367149758454,
    "phase7_any_grid_boundary_rate": 0.6894685990338164,
    "phase7_automatic_rows": 5175
  },
  "neighbor_fragility": {
    "rows": 3567,
    "mean_gp_advantage": 0.6271238134445573,
    "median_gp_advantage": 0.5082451471843683,
    "p05_gp_advantage": 0.08480222776073763,
    "p25_gp_advantage": 0.25452628938152255,
    "p75_gp_advantage": 0.8433037191674373,
    "p95_gp_advantage": 1.6590832121460246,
    "mean_relative_gp_advantage": 0.04017070047615495,
    "median_relative_gp_advantage": 0.04036603503149194,
    "share_relative_below_0_1pct": 0.0,
    "share_relative_below_0_5pct": 0.005326604990187833,
    "share_relative_at_least_1pct": 0.9823380992430614,
    "warning_codes": []
  },
  "boundary_augmentation": {
    "in_support_unsimulated_boundaries": 5384,
    "boundaries_scored": 5384,
    "decision_rows_with_scored_boundaries": 3171,
    "augmented_candidate_rows": 33923,
    "decisions_where_augmented_optimum_differs": 2912,
    "change_rate": 0.9183222958057395,
    "aggregate_model_implied_gp_delta": 931.5944455800493,
    "relative_aggregate_gp_delta": 0.01096430730336892,
    "affected_subset_gp_gap_pct": 0.01950360905688137,
    "policywide_automatic_gp_gap_pct": 0.01096430730336892,
    "affected_subset_phase7_automatic_gp": 48470.62116655262,
    "policywide_automatic_phase7_gp": 84966.10135086284,
    "ineligible_augmented_candidate_rows": 3657,
    "mean_price_delta": 1.8574929044465476,
    "selection_policy": {
      "objective": "EXPECTED_GROSS_PROFIT",
      "tie_relative": 0.001,
      "tie_absolute": 1e-08,
      "closest_to_current_price": true,
      "lower_price_tie_break": true,
      "materiality_relative_expected_profit_uplift": 0.005
    },
    "support_envelope_source": "PHASE6_EFFECTIVE_SUPPORT_ENVELOPE",
    "warning_codes": [
      "COARSE_GRID_VALUE_WARNING"
    ],
    "blockers": [],
    "augmented_surface_rows": 33923
  },
  "policy_overlap": {
    "exact_matches": 16,
    "exact_match_rate": 0.0030917874396135265,
    "observed_units": 1.0,
    "observed_revenue": 169.08,
    "observed_gross_profit": 86.39000000000001,
    "predicted_units": 4.43862424344971,
    "predicted_revenue": 276.8203721139848,
    "predicted_gross_profit": 132.14082872379646
  }
}

## 29–34. Segments, rule impact, and promotions

{
  "segment_summary": {
    "minimum_rows": 100,
    "supported_segments": 44,
    "warnings": [
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "Channel",
        "value": "Online",
        "error_pct": -0.22116571598038945
      },
      {
        "code": "SEGMENT_GP_CALIBRATION_WARNING",
        "dimension": "Channel",
        "value": "Online",
        "error_pct": -0.2516819163069995
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "RegionID",
        "value": "REG000006",
        "error_pct": 0.23201200644779046
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "RegionID",
        "value": "REG000009",
        "error_pct": -0.2912345304604129
      },
      {
        "code": "SEGMENT_GP_CALIBRATION_WARNING",
        "dimension": "RegionID",
        "value": "REG000009",
        "error_pct": -0.2853977996619569
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000016",
        "error_pct": -0.22970725215114013
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000019",
        "error_pct": 0.31629539518880145
      },
      {
        "code": "SEGMENT_GP_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000019",
        "error_pct": 0.3581582649802672
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000024",
        "error_pct": 0.4028567294673812
      },
      {
        "code": "SEGMENT_GP_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000024",
        "error_pct": 0.2765998631581282
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000043",
        "error_pct": 0.2097656622618202
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000046",
        "error_pct": -0.4664963445293586
      },
      {
        "code": "SEGMENT_GP_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000046",
        "error_pct": -0.46695482443301034
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000050",
        "error_pct": -0.21675091764440893
      },
      {
        "code": "SEGMENT_REVENUE_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000057",
        "error_pct": 0.42360847352546566
      },
      {
        "code": "SEGMENT_GP_CALIBRATION_WARNING",
        "dimension": "CategoryID",
        "value": "CAT000057",
        "error_pct": 0.3743709961364613
      }
    ],
    "revenue_warning_count": 10,
    "gp_warning_count": 6,
    "major_segment_economic_calibration_failure": false,
    "blockers": []
  },
  "rule_impact": [
    {
      "constraint_type": "MinPrice",
      "decisions_affected": 3,
      "candidate_rows_filtered": 4,
      "price_delta_mean": -4.693333333333334,
      "share_of_test_decisions_affected": 0.0005714285714285715,
      "average_model_implied_gp_impact": null,
      "average_price_impact": -4.693333333333334,
      "gp_impact_note": "Phase 7 source diagnostics do not attribute counterfactual GP to one overlapping guardrail; no invented attribution is reported."
    },
    {
      "constraint_type": "MaxPrice",
      "decisions_affected": 55,
      "candidate_rows_filtered": 103,
      "price_delta_mean": 14.120011904761904,
      "share_of_test_decisions_affected": 0.010476190476190476,
      "average_model_implied_gp_impact": null,
      "average_price_impact": 14.120011904761904,
      "gp_impact_note": "Phase 7 source diagnostics do not attribute counterfactual GP to one overlapping guardrail; no invented attribution is reported."
    },
    {
      "constraint_type": "MinMarginPct",
      "decisions_affected": 139,
      "candidate_rows_filtered": 249,
      "price_delta_mean": -9.944321386603994,
      "share_of_test_decisions_affected": 0.026476190476190476,
      "average_model_implied_gp_impact": null,
      "average_price_impact": -9.944321386603994,
      "gp_impact_note": "Phase 7 source diagnostics do not attribute counterfactual GP to one overlapping guardrail; no invented attribution is reported."
    },
    {
      "constraint_type": "MaxDiscountPct",
      "decisions_affected": 525,
      "candidate_rows_filtered": 1056,
      "price_delta_mean": -8.437652932998716,
      "share_of_test_decisions_affected": 0.1,
      "average_model_implied_gp_impact": null,
      "average_price_impact": -8.437652932998716,
      "gp_impact_note": "Phase 7 source diagnostics do not attribute counterfactual GP to one overlapping guardrail; no invented attribution is reported."
    },
    {
      "constraint_type": "MaxPriceChangePct",
      "decisions_affected": 3047,
      "candidate_rows_filtered": 6462,
      "price_delta_mean": 0.0005244797513998,
      "share_of_test_decisions_affected": 0.5803809523809523,
      "average_model_implied_gp_impact": null,
      "average_price_impact": 0.0005244797513998,
      "gp_impact_note": "Phase 7 source diagnostics do not attribute counterfactual GP to one overlapping guardrail; no invented attribution is reported."
    }
  ],
  "promotion_diagnostics": {
    "promotion_pricing_mode": "CONTEXT_ONLY",
    "active_promotion_context_rate": 0.030095238095238095,
    "promotion_conflict_review_rate": 0.0,
    "causal_claims_made": false,
    "historical_markdown_backtest": "NOT_AVAILABLE_NO_HISTORICAL_INVENTORY"
  }
}

## 35–40. Inventory, staleness, bootstrap, reproducibility

{
  "historical_inventory": {
    "validation": "NOT_AVAILABLE_NO_HISTORICAL_INVENTORY",
    "test": "NOT_AVAILABLE_NO_HISTORICAL_INVENTORY",
    "inventory_constraint_applied": false
  },
  "current_inventory": {
    "as_of_date": "2025-12-31",
    "eligible_contexts": 1829,
    "inventory_coverage": 1.0,
    "stale_contexts": 595,
    "stale_context_rate": 0.24546204620462045,
    "price_increases": 1564,
    "price_decreases": 78,
    "holds": 170,
    "seasonal_markdowns": 69,
    "markdown_reviews": 172,
    "promotion_reviews": 0,
    "inventory_capped_expected_units": 406.9253978968268,
    "inventory_capped_expected_revenue": 66877.96588809243,
    "inventory_capped_expected_gross_profit": 30353.774653034478,
    "source_artifact": "phase7/current_inventory_business_decisions.parquet",
    "warnings": [
      "CURRENT_CONTEXT_STALENESS_HIGH"
    ]
  },
  "bootstrap": {
    "seed": 42,
    "bootstrap_samples": 1000,
    "confidence": 0.95,
    "intervals": {
      "aggregate_units_error_pct": {
        "lower_2_5_pct": -0.08385347290671867,
        "upper_97_5_pct": 0.03497827630566439,
        "mean": -0.02608835189996143
      },
      "aggregate_revenue_error_pct": {
        "lower_2_5_pct": -0.10996268376568366,
        "upper_97_5_pct": 0.0387044894921101,
        "mean": -0.0374005056842816
      },
      "aggregate_gp_error_pct": {
        "lower_2_5_pct": -0.11511013495858238,
        "upper_97_5_pct": 0.029795851730678957,
        "mean": -0.04368037448770488
      },
      "phase7_model_implied_gp_delta_pct": {
        "lower_2_5_pct": 0.08893329451141022,
        "upper_97_5_pct": 0.09502387560381478,
        "mean": 0.09192639225565152
      }
    },
    "interpretation": "Sample uncertainty only; intervals do not make counterfactual comparisons causal.",
    "status": "PASS"
  },
  "reproducibility": {
    "status": "PASS",
    "mismatches": 0,
    "max_numeric_delta": 0.0,
    "tolerance": 1e-10,
    "joined_outcomes_identical": true,
    "factual_metrics_identical": true,
    "scenario_economics_identical": true,
    "automatic_cohort_identical": true,
    "bootstrap_identical": true
  }
}

## 41–45. Compute, limitations, and handoff

{
  "compute": {
    "physical_cores": 16,
    "logical_threads": 22,
    "usable_threads": 22,
    "rows_evaluated": 10500,
    "candidate_rows_inspected": 47250,
    "boundary_candidates_scored": 5384,
    "timings_seconds": {
      "validation_outcome_loading_seconds": 0.030050900000787806,
      "test_outcome_loading_seconds": 0.03254629999719327,
      "validation_historical_scoring_seconds": 0.156301999995776,
      "validation_scenario_scoring_seconds": 0.3680045999935828,
      "validation_s0_historical_applied_scoring_seconds": 0.021233899999060668,
      "validation_s1_current_price_scoring_seconds": 0.09207480000623036,
      "validation_s2_phase6_model_optimal_scoring_seconds": 0.12973280000005616,
      "validation_s3_phase7_final_automatic_scoring_seconds": 0.07627640000282554,
      "validation_s4_phase7_with_historical_fallback_scoring_seconds": 0.020046199999342207,
      "validation_scenario_assembly_seconds": 0.023656299999856856,
      "validation_factual_metrics_seconds": 0.027145400003064424,
      "test_historical_scoring_seconds": 0.1846739000029629,
      "test_scenario_scoring_seconds": 0.3822924999985844,
      "test_s0_historical_applied_scoring_seconds": 0.02164999999513384,
      "test_s1_current_price_scoring_seconds": 0.09955469999840716,
      "test_s2_phase6_model_optimal_scoring_seconds": 0.10677920000307495,
      "test_s3_phase7_final_automatic_scoring_seconds": 0.10232349999569124,
      "test_s4_phase7_with_historical_fallback_scoring_seconds": 0.022417000000132248,
      "test_scenario_assembly_seconds": 0.026286299995263107,
      "test_factual_metrics_seconds": 0.030178400003933348,
      "boundary_analysis_seconds": 88.84170219999942,
      "segment_analysis_seconds": 0.11226280000119004,
      "bootstrap_seconds": 8.298957399994833,
      "outcome_loading_seconds": 0.06259719999798108,
      "historical_scoring_seconds": 0.3409758999987389,
      "current_price_scoring_seconds": 0.19162950000463752,
      "scenario_assembly_seconds": 0.04994259999511996,
      "factual_metrics_seconds": 0.05732380000699777,
      "total": 110.24323949999962
    },
    "policy": "Batched frozen CatBoost inference; no nested outer parallel loop.",
    "no_training": true
  },
  "warnings": [
    "AGGRESSIVE_PRICE_POLICY",
    "COARSE_GRID_VALUE_WARNING",
    "CURRENT_CONTEXT_STALENESS_HIGH",
    "LOW_FACTUAL_POLICY_OVERLAP",
    "SEGMENT_GP_CALIBRATION_WARNING",
    "SEGMENT_REVENUE_CALIBRATION_WARNING"
  ],
  "major_blockers": []
}

Phase 9 may consume the frozen recommendation and evaluation artifacts only
after independent Phase 8 approval. This report does not present scenario
estimates as realized outcomes.
