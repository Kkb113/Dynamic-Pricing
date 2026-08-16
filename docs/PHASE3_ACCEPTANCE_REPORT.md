# Phase 3 Acceptance Report

## 1. Executive verdict

**PASS_WITH_WARNINGS** — chronological baseline framework completed against the frozen Phase 2 dataset.

## 2. Phase 2 dataset verification

- Fingerprint: `7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2`
- Rows: **35,000**; unique `PricingDecisionID`: **35,000**
- Purchases: **6,492**; non-purchases: **28,508**
- The runner blocked before modelling if this fingerprint, row count, uniqueness, or target totals did not match.

## 3. Compute environment

- Physical cores detected: **16**
- Logical threads detected: **22**
- Maximum/configured/usable threads: **22 / 22 / 22**
- Effective parallelism: **single_fit_at_a_time_with_threadpool_limit**; nested parallelism: **False**

## 4. Canonical temporal split

```text
     split  row_count  purchase_count  non_purchase_count  purchase_rate  quantity_positive_rows   decision_time_min   decision_time_max  distinct_ProductID  distinct_CategoryID  distinct_BrandID  distinct_StoreID  distinct_RegionID  distinct_Channel
     train      24500            4581               19919       0.186980                    4581 2025-01-01T08:12:26 2025-09-23T14:26:24                2517                   70               150                49                 10                 6
validation       5250             939                4311       0.178857                     939 2025-09-23T15:09:15 2025-11-15T23:42:22                1470                   70               148                49                 10                 6
      test       5250             972                4278       0.185143                     972 2025-11-15T23:57:30 2025-12-31T23:59:39                1426                   70               148                49                 10                 6
```

All equal `DecisionTime` values remain together. The resulting partitions are approximately 70/15/15 and are strictly ordered.

## 5. Split integrity

Every decision is assigned exactly once; train/validation/test identifier intersections are empty; `max(TRAIN.DecisionTime) < min(VALIDATION.DecisionTime) < min(TEST.DecisionTime)`. The canonical assignments are in `artifacts/phase3/split_assignments.parquet`.

## 6. Expanding-window validation design

Three expanding folds are contained inside TRAIN. Every fold has both target classes and records row counts, target counts, dates, and Product/Category/Store/Channel coverage in `temporal_fold_manifest.json`.

## 7. Feature contract

Official models use `model_feature_columns(contract, population=...)` from the Phase 2 contract with core features only. ProductID, StoreID, competitor, behavior, customer-context, and join-only favorites remain conditional or excluded by default.

## 8. Preprocessing leakage protection

Each model is a single `ColumnTransformer` + `Pipeline`: numeric median imputation and scaling plus constant-missing categorical imputation and `OneHotEncoder(handle_unknown='ignore')`. Every fold and final fit learns preprocessing only from its training rows.

## 9. Purchase dummy baseline

`purchase_dummy_prior` is the natural-prevalence lower bound. Validation ROC-AUC **0.500000**, log loss **0.469876**, Brier **0.146933**.

## 10. Logistic regression baseline

`purchase_logistic_core` uses fixed L2 `LogisticRegression(C=1.0, solver='lbfgs', max_iter=2000, random_state=42, class_weight=None)` with no search or tuning.

## 11. Purchase probability metrics

| Model | Split | ROC-AUC | AP | Log loss | Brier | ECE | Top-decile lift |
|---|---|---:|---:|---:|---:|---:|---:|
| purchase_dummy_prior | validation | 0.500000 | 0.178857 | 0.469876 | 0.146933 | 0.008122 | 0.969116 |
| purchase_logistic_core | validation | 0.500459 | 0.177901 | 0.475542 | 0.148864 | 0.032122 | 0.990415 |
| purchase_logistic_core | test | 0.526029 | 0.198225 | 0.482598 | 0.151952 | 0.026116 | 1.121399 |

Precision, recall, and F1 at 0.5 are retained in the JSON metric artifacts; probability quality is the primary criterion.

## 12. Calibration

Native 10-bin calibration tables and ECE are persisted at `purchase_calibration_validation.csv` and `purchase_calibration_test.csv`. No post-hoc calibration was fit.

## 13. Temporal-fold stability

The logistic-core fold summary is **mean ROC-AUC 0.511835 ± 0.011288**, with min **0.499656** and max **0.526862**. Full per-fold and mean/std/min/max metrics are in `temporal_fold_metric_summary.json`.

## 14. Price-response diagnostic

`purchase_logistic_core_no_price` is a validation-only predictive signal ablation. Validation logistic core ROC-AUC **0.500459** versus no-price **0.501050**; observed difference **-0.000590**. This is not causal elasticity.

## 15. Quantity mean baseline

`quantity_dummy_mean` trains only on purchased TRAIN rows and is evaluated only on purchased future rows. Validation MAE **0.469545**, RMSE **0.633690**.

## 16. Poisson quantity baseline

`quantity_poisson_core` uses fixed `PoissonRegressor(alpha=1.0, max_iter=1000)` and the same core contract. Validation MAE **0.480232**, RMSE **0.635063**, R² **-0.004851**, Poisson deviance **0.244353**.

## 17. Quantity metrics

Holdout Poisson MAE **0.467092**, RMSE **0.640030**, R² **-0.003787**, Poisson deviance **0.247952**; negative prediction count **0**. Quantity predictions are non-negative.

## 18. Segment diagnostics

Validation and test segment metrics for Channel, Season, RegionID, CategoryID, and StoreType use minimum support 100. Feature missingness, unseen levels, target drift, and price buckets are persisted under `artifacts/phase3/`.

## 19. Holdout-test discipline

The TEST partition was not used for feature choice, threshold choice, preprocessing fit, model selection, or tuning. Frozen specifications were refit once on TRAIN+VALIDATION and evaluated once on TEST. `test_access_manifest.json` records the data ranges, model fingerprints, prediction fingerprints, and generation time.

## 20. Compute performance

`compute_benchmark.json` records threads used, purchase-logistic fit time, quantity-Poisson fit time, and total temporal-fold time. Fitted complete pipelines are serialized with joblib under `artifacts/phase3/models/`.

## 21. Known limitations

The synthetic/observational data show weak purchase signal and quantity concentration; unseen categories, null-rate shifts, and drift are diagnostic warnings rather than repaired by resampling. No source rows or targets were changed.

## 22. Risks for Phase 4

The baselines do not establish causal price elasticity, and advanced models must beat these chronological benchmarks without changing the split or leakage contract. Conditional features require a separately approved experiment.

## 23. Final verdict

**PASS_WITH_WARNINGS**

Warnings: - one or more core feature null rates shift by more than 10 percentage points
- logistic validation log_loss (0.475542) is worse than dummy prior (0.469876); investigate before promotion
- logistic validation brier_score (0.148864) is worse than dummy prior (0.146933); investigate before promotion
- logistic validation average precision (0.177901) is near purchase prevalence (0.178857)
- Phase 3 baselines are predictive benchmarks; no causal elasticity claim is made

Leakage status: **0 runtime leakage violations; 0 conditional-feature violations in official baselines; 0 test-fit violations**.

## 24. Recommendation

**PROCEED_TO_PHASE_4**
