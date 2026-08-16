# Phase 4 CatBoost Purchase Probability Model Report

## Model search

Optuna used a serial `TPESampler(seed=42)` with `n_jobs=1`; each trial used `22` CatBoost CPU threads. The objective was mean Log Loss over the three TRAIN expanding folds. `60` trials completed, `0` failed, and `0` were pruned. The selected trial was `35` with mean Log Loss `0.459865` and fold standard deviation `0.007821`.

Selected parameters:

```json
{
  "bagging_temperature": 0.843547603487963,
  "border_count": 128,
  "depth": 4,
  "l2_leaf_reg": 3.919279211543739,
  "learning_rate": 0.046909856915972124,
  "random_strength": 0.6183057530027418
}
```

## Temporal-fold stability

The selected specification was re-evaluated on all three TRAIN folds. Full fold rows and aggregate summaries are in `artifacts/phase4/temporal_fold_metrics.csv` and `temporal_fold_summary.json`.

## TRAIN → VALIDATION

| Model | ROC-AUC | AP | Log Loss | Brier | ECE | Top-decile lift |
|---|---:|---:|---:|---:|---:|---:|
| Dummy prior | 0.500000 | 0.178857 | 0.469876 | 0.146933 | 0.008122 | 1.000000 |
| Phase 3 logistic | 0.500459 | 0.177901 | 0.475542 | 0.148864 | 0.032122 | 0.990415 |
| CatBoost native | 0.596830 | 0.234591 | 0.461540 | 0.144466 | 0.001489 | 1.480298 |
| CatBoost official (NATIVE) | 0.596830 | 0.234591 | 0.461540 | 0.144466 | 0.001489 | 1.480298 |

## Calibration

Calibration candidates were trained from temporally valid TRAIN OOF predictions only. Candidate validation scores are in `artifacts/phase4/calibration_validation.csv`; selection priority was Log Loss, Brier, ECE, then simplicity. Selected method: **NATIVE**. Reason: No sigmoid or isotonic candidate met the predefined log-loss/Brier materiality threshold.

## Candidate-price diagnostics

Historical AppliedPrice parity violations: **0**. The adapter reuses `features.price_features.build_price_dependent_features`; CurrentPrice, BasePrice, history, behavior, and seasonality remain fixed during scenario inference. Price-response stress testing is predictive scenario sensitivity, not causal elasticity.

```json
{
  "causal_interpretation": "model-implied predictive price response only; not a causal elasticity estimate",
  "flat_response_rate": 0.0,
  "mean_probability_range": 0.05140012775892906,
  "median_predicted_probability_by_multiplier": {
    "0.8": 0.20012639189041936,
    "0.9": 0.19008967121492165,
    "0.95": 0.17605975797528856,
    "1.0": 0.16417232048201363,
    "1.05": 0.15814704181405026,
    "1.1": 0.15640083212200656,
    "1.2": 0.1561629179681201
  },
  "median_probability_change_current_to_plus_10pct": -0.00753995651905226,
  "median_probability_change_minus_10pct_to_current": -0.027330833233782714,
  "median_probability_range": 0.049889849271310224,
  "multipliers": [
    0.8,
    0.9,
    0.95,
    1.0,
    1.05,
    1.1,
    1.2
  ],
  "non_monotonic_sequence_rate": 0.5137142857142857,
  "row_count": 5250,
  "significant_upward_violation_rate": 0.05980952380952381
}
```

## Feature importance

Native CatBoost global importance is in `artifacts/phase4/feature_importance.csv`. It is a diagnostic, not the Phase 9 explainability product.

## Holdout discipline

The model, feature family, hyperparameters, iteration count, calibration method, and inference adapter were frozen before TEST. The final CatBoost was fit on TRAIN+VALIDATION with no TEST eval set. `test_access_manifest.json` records the single final benchmark access.

## TEST

| Metric | Value |
|---|---:|
| ROC-AUC | 0.609339 |
| AP | 0.245235 |
| Log Loss | 0.469087 |
| Brier | 0.147869 |
| ECE | 0.008381 |
| Top-decile lift | 1.491770 |

## Reproducibility

Maximum absolute validation probability delta across two identical TRAIN→VALIDATION fits: **0**; status: **PASS**. Best iterations: `200` and `200`.
