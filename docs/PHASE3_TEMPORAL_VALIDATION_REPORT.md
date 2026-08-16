# Phase 3 Temporal Validation Report

## Executive summary

Phase 3 uses the frozen Phase 2 point-in-time dataset and chronological evaluation only. No advanced model, hyperparameter search, causal elasticity estimate, or pricing optimizer is implemented.

## Dataset and split health

- Phase 2 canonical fingerprint: `7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2`
- Rows: **35,000**; unique decisions: **35,000**
- Split boundaries: `2025-01-01T08:12:26` → `2025-09-23T14:26:24` → `2025-11-15T23:42:22` → `2025-12-31T23:59:39`

     split  row_count  purchase_count  non_purchase_count  purchase_rate  quantity_positive_rows   decision_time_min   decision_time_max  distinct_ProductID  distinct_CategoryID  distinct_BrandID  distinct_StoreID  distinct_RegionID  distinct_Channel
     train      24500            4581               19919       0.186980                    4581 2025-01-01T08:12:26 2025-09-23T14:26:24                2517                   70               150                49                 10                 6
validation       5250             939                4311       0.178857                     939 2025-09-23T15:09:15 2025-11-15T23:42:22                1470                   70               148                49                 10                 6
      test       5250             972                4278       0.185143                     972 2025-11-15T23:57:30 2025-12-31T23:59:39                1426                   70               148                49                 10                 6

## Feature contract and leakage protection

Official baselines use `model_feature_columns(contract, population=...)` with the default core-only feature set. Conditional fields, competitor context, behavior, customer context, ProductID, and StoreID are excluded unless explicitly approved for an experiment. Targets, identifiers, PII, inventory, pricing rules, optimizer outputs, and post-outcome fields are rejected by the preprocessing contract.

All imputers, encoders, scalers, and estimators are fit on each training partition only. The final holdout is evaluated once after refitting the frozen specifications on TRAIN+VALIDATION.

## Expanding-window backtesting

Three expanding folds are contained entirely inside TRAIN. Their manifest and per-fold metrics are in `artifacts/phase3/temporal_fold_manifest.json`, `purchase_temporal_fold_metrics.csv`, and `quantity_temporal_fold_metrics.csv`.

## Purchase probability baselines

The official benchmark is `purchase_logistic_core`; `purchase_dummy_prior` is the lower bound. Validation logistic metrics: ROC-AUC **0.5004593593573564**, average precision **0.17790142106169896**, log loss **0.4755424448028758**, Brier **0.1488640726795099**, ECE **0.03212218962041481**, top-decile lift **0.9904153354632588**. Holdout metrics: ROC-AUC **0.526029431852506**, average precision **0.198224848939275**, log loss **0.4825975666616103**, Brier **0.15195172395850157**.

The price ablation is a predictive signal diagnostic only; its comparison is validation-only and is not a causal elasticity estimate.

## Calibration, segment, and price diagnostics

Native 10-bin calibration tables, segment metrics (minimum support 100), and price-change buckets are persisted under `artifacts/phase3/`. Price results are described as observed predictive relationships, never causal elasticity.

## Quantity baselines

Quantity models are trained only on `PurchasedFlag == 1` rows, and `PurchasedFlag` is not a predictor. The official benchmark is `quantity_poisson_core`; the mean predictor is the lower bound. Validation Poisson MAE **0.4802318364680323**, RMSE **0.6350632342864145**, R² **-0.004851174102414868**, Poisson deviance **0.24435339579640508**. Holdout MAE **0.4670921468977555**, RMSE **0.6400303058664499**, R² **-0.00378715858705414**, Poisson deviance **0.24795237058616384**.

## Compute and reproducibility

- Physical cores: **16**
- Logical threads: **22**
- Usable/configured limit: **22 / 22**
- Random seed: **42**; nested parallelism: **disabled**
- Test evidence: **94/94 passed**

## Warnings

- one or more core feature null rates shift by more than 10 percentage points
- logistic validation log_loss (0.475542) is worse than dummy prior (0.469876); investigate before promotion
- logistic validation brier_score (0.148864) is worse than dummy prior (0.146933); investigate before promotion
- logistic validation average precision (0.177901) is near purchase prevalence (0.178857)
- Phase 3 baselines are predictive benchmarks; no causal elasticity claim is made
