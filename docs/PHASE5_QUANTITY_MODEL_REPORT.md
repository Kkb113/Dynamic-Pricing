# Phase 5 Conditional Quantity Model Report

## Target and population

The target is `QuantityPurchased` on the purchased-only population (`PurchasedFlag == 1`). The frozen audit contains **6492** rows, support **1–4**, mean **1.304375**, median **1.000000**, and standard deviation **0.635876**. Quantity one represents **77.819%** of purchases; this is a measured **concentrated** target, with no synthetic augmentation.

## Screening and HPO

All QF0–QF8 families and the Phase 4 `F3_CORE_BEHAVIOR` reference were screened under fixed RMSE and Poisson objectives on the three purchased TRAIN folds. The selected screening candidate was **F3_CORE_BEHAVIOR / RMSE**. Optuna used a serial TPE sampler with seed 42 and **60** requested trials; **60** completed.

Selected HPO parameters and complete fold rows are in `artifacts/phase5/best_hyperparameters.json` and `artifacts/phase5/hpo_trials.csv`.

## Validation materiality gate

| Estimator | MAE | RMSE | R² | Poisson deviance | Bias |
|---|---:|---:|---:|---:|---:|
| TRAIN mean | 0.469545 | 0.633690 | -0.0005094900773796596 | 0.243029 | 0.014300 |
| Advanced diagnostic | 0.473082 | 0.633159 | 0.0011648170141482783 | 0.242507 | 0.021803 |

The predeclared adoption gate chose **CONSTANT_MEAN**. Gate details are persisted in `artifacts/phase5/adoption_gate.json`; CatBoost is never promoted merely because it was trained.

## Frozen specification

The specification was hashed before TEST: `260354340c41fe8eaccaafc4e3388f7fb28c81ec4fbaba049504a25b7a487914`. The declared support projection is `max(raw_prediction, 1.0)`; predictions remain continuous and are never rounded.
