# Phase 6 Acceptance Report

## 1. Executive verdict

**PASS_WITH_WARNINGS** — PROCEED_TO_PHASE_7

## 2. Upstream verification

- Phase 2: `7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2`
- Phase 3: `9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d`
- Phase 4 model/spec: `1af936a1905dcb21e3623392a16afbdbfc6b57c6866093fd6b33f12976dfd86d` / `87ffb4e56af455937a0c92b1be45be0e2c8082cc0efd6afa51eb62f9c05ba9d0`
- Phase 5 official estimator: `CONSTANT_MEAN`, mean `1.3057971014492753`

## 3–20. Contract and parity gates

TEST outcomes accessed by scenario engine: **False**. TEST scenario context outcome columns: **[]**. Cost coverage: **1.0**. Support: **{"candidate_multiplier_template": [0.9, 0.925, 0.95, 0.975, 1.0, 1.025, 1.05, 1.075, 1.1], "count": 24500, "effective_support_high": 1.1173885792710216, "effective_support_low": 0.8929977619398718, "max": 1.1201831362075543, "mean": 1.019822843056361, "min": 0.8799014576062409, "p01": 0.8929977619398718, "p05": 0.9050912024762382, "p25": 0.9687779630179572, "p50": 1.0152957836513834, "p75": 1.0899782675217224, "p95": 1.1070176241530623, "p99": 1.1173885792710216, "std": 0.06826214156631909, "technical_multiplier_high": 1.2, "technical_multiplier_low": 0.8, "training_ratio_p01": 0.8929977619398718, "training_ratio_p99": 1.1173885792710216, "valid_positive_rate": 1.0}**. Candidate parity: **{"integrated_expected_unit_delta": 0.0, "phase4_candidate_probability_delta": 0.0, "phase4_feature_max_delta": 0.0, "phase4_feature_violations": 0, "phase4_test_prediction_delta": 0.0, "phase5_artifact_quantity_delta": 0.0024325427332176908, "phase5_artifact_scope": "PRE_FREEZE_TRAIN_ONLY", "phase5_candidate_quantity_delta": 0.0, "phase5_feature_max_delta": 0.0, "phase5_test_expected_unit_delta": 0.0, "rows": 5250, "split": "validation", "status": "PASS", "tolerance": 1e-10}**. TEST stack parity: **{"integrated_expected_unit_delta": 0.0, "phase4_candidate_probability_delta": 0.0, "phase4_feature_max_delta": 0.0, "phase4_feature_violations": 0, "phase4_test_prediction_delta": 0.0, "phase5_artifact_quantity_delta": 0.0, "phase5_artifact_scope": "POST_FREEZE_TRAIN_PLUS_VALIDATION", "phase5_candidate_quantity_delta": 0.0, "phase5_feature_max_delta": 0.0, "phase5_test_expected_unit_delta": 0.0, "rows": 5250, "split": "test", "status": "PASS", "tolerance": 1e-10}**.

## 21–30. Scenario diagnostics

VALIDATION: `{"all_candidates_negative_margin_rate": 0.0, "any_boundary_selection_rate": 0.981904761904762, "candidate_negative_margin_rate": 0.0, "candidate_rows": 47250, "decision_count": 5250, "decisions_where_all_candidates_negative_margin": 0, "decisions_with_any_negative_margin_candidate": 0, "lower_boundary_selection_rate": 0.00038095238095238096, "max_candidate_count": 9, "mean_candidate_count": 9.0, "mean_expected_profit_uplift": 2.572559924571292, "mean_expected_revenue_delta": 1.6735719533616142, "mean_price_change_pct": 0.09919008630929192, "median_expected_profit_uplift": 2.0317082524480004, "median_price_change_pct": 0.10000000000000009, "median_recommended_multiplier": 1.1, "min_candidate_count": 9, "no_change_rate": 0.0, "p05_price_change_pct": 0.09991603694374485, "p25_price_change_pct": 0.09998306806233026, "p75_price_change_pct": 0.10002020817416674, "p95_price_change_pct": 0.10008240764677818, "positive_uplift_rate": 1.0, "price_decrease_rate": 0.002476190476190476, "price_increase_rate": 0.9975238095238095, "raw_vs_safe_recommendation_change_rate": 0.001142857142857143, "revenue_profit_differ_rate": 0.6426666666666667, "split": "validation", "upper_boundary_selection_rate": 0.9815238095238096}`

TEST: `{"all_candidates_negative_margin_rate": 0.0, "any_boundary_selection_rate": 0.9758095238095238, "candidate_negative_margin_rate": 0.0, "candidate_rows": 47250, "decision_count": 5250, "decisions_where_all_candidates_negative_margin": 0, "decisions_with_any_negative_margin_candidate": 0, "lower_boundary_selection_rate": 0.00019047619047619048, "max_candidate_count": 9, "mean_candidate_count": 9.0, "mean_expected_profit_uplift": 2.566393252582335, "mean_expected_revenue_delta": 1.6340887086251197, "mean_price_change_pct": 0.0989178324871371, "median_expected_profit_uplift": 2.058202637178119, "median_price_change_pct": 0.10000000000000009, "median_recommended_multiplier": 1.1, "min_candidate_count": 9, "no_change_rate": 0.0, "p05_price_change_pct": 0.09990890037343178, "p25_price_change_pct": 0.09998384424088547, "p75_price_change_pct": 0.10001979610016831, "p95_price_change_pct": 0.10007225433526012, "positive_uplift_rate": 1.0, "price_decrease_rate": 0.0032380952380952383, "price_increase_rate": 0.9967619047619047, "raw_vs_safe_recommendation_change_rate": 0.00038095238095238096, "revenue_profit_differ_rate": 0.6460952380952381, "split": "test", "upper_boundary_selection_rate": 0.9756190476190476}`

The response guard, safe-demand invariants, gross-profit surface, raw-vs-safe optimizer comparison, revenue-vs-profit comparison, boundary diagnostics, and segment diagnostics are serialized in `artifacts/phase6/`.

## 31. Compute and reproducibility

`{"Phase4_prediction_seconds": 0.41672309997375123, "Phase5_quantity_seconds": 0.05409909997251816, "candidate_generation_seconds": 0.3592678999702912, "candidate_rows_per_second": 763.7041984662435, "candidate_rows_scored": 94500, "decisions_scored": 10500, "economic_scoring_seconds": 0.02393679996021092, "feature_generation_seconds": 1.1641711000120267, "logical_threads": 22, "optimizer_selection_seconds": 92.98281119999592, "physical_cores": 16, "threads_used": 22, "total_seconds": 123.73900809997576}`

`{"candidate_price_mismatch_count": 0, "candidate_row_count_run1": 47250, "candidate_row_count_run2": 47250, "decision_status_mismatch_count": 0, "max_expected_profit_delta": 0.0, "max_expected_units_delta": 0.0, "max_probability_delta": 0.0, "max_revenue_delta": 0.0, "selected_price_mismatch_count": 0, "status": "PASS", "tolerance": 1e-10}`

## 32–35. Limitations and handoff

Phase 6 does not claim actual uplift and does not access historical inventory or outcomes during scenario simulation. Phase 7 must apply Pricing_Rules, MinPrice/MaxPrice, margin and discount limits, scope priority, promotion/markdown logic, and current inventory constraints.

Warnings: ["OPTIMIZER_BOUNDARY_HEAVY", "OPTIMIZER_STRONGLY_BOUNDARY_SEEKING", "HIGH_RESPONSE_GUARD_USAGE"]

Major blockers: []

Final recommendation: **PROCEED_TO_PHASE_7**
