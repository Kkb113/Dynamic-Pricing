# Phase 4 Acceptance Report

## 1. Executive verdict

**PASS_WITH_WARNINGS** — CatBoost purchase-probability feasibility gate.

## 2. Upstream verification

- Base branch: `codex/phase1-data-audit`
- Base SHA: `5f4a2a8645954edeec24f8ffba4558cbed92f7d4`
- Phase 2 dataset fingerprint: `7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2`
- Phase 3 split fingerprint: `9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d`
- Rows: **35,000**; purchases: **6,492**; non-purchases: **28,508**
- Split health: train 24,500 / validation 5,250 / test 5,250; target counts and chronology matched the accepted Phase 3 contract.

## 3. Compute environment

- Physical cores: **16**
- Logical threads: **22**
- CatBoost threads: **22**
- Optuna jobs: **1**
- Nested parallelism: **false**

## 4–5. Feature-family screening and selected family

The three TRAIN-only expanding-fold screening results are in `feature_family_screening.csv`. Selected family: **F3_CORE_BEHAVIOR**; CORE remained a candidate. Customer context selected: **False** because the predefined stronger bar was not met.

## 6. Hyperparameter optimization

`hpo_trials.csv` contains every trial. Completed: **60**; failed: **0**; pruned: **0**. Best mean fold Log Loss: **0.459606**; selected fold std: **0.007821**. Optuna used TPE seed 42, serial trials, and a bounded search space.

## 7. Temporal-fold results

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| Log Loss | 0.459865 | 0.007821 | 0.448860 | 0.466326 |
| Brier | 0.143880 | 0.003295 | 0.139248 | 0.146632 |
| AP | 0.235846 | 0.010082 | 0.221727 | 0.244625 |
| ROC-AUC | 0.605302 | 0.002254 | 0.602337 | 0.607798 |
| ECE | 0.010569 | 0.005707 | 0.005382 | 0.018518 |

## 8–12. Final validation and calibration

The official validation model used TRAIN with VALIDATION as eval_set and early stopping. Native and calibrated metrics are in `validation_metrics.json`; 10-bin calibration is in `validation_calibration_table.csv`. Calibration was trained from TRAIN OOF predictions only and frozen before TEST.

## 13–15. Candidate-price parity, stress test, and importance

- Parity violations: **0**
- Flat-response rate: **0.000000**
- Non-monotonic scenario rate: **0.513714**
- Significant upward-violation rate: **0.059810**
- Median -10% → current probability delta: **-0.027331**
- Median current → +10% probability delta: **-0.007540**

These are model-implied predictive responses, not causal price elasticity.

## 16. Frozen model specification

The frozen spec was written and hashed before TEST. Feature count: **65**; categorical feature count: **8**; iterations: **201**; calibration: **NATIVE**; frozen spec SHA: `87ffb4e56af455937a0c92b1be45be0e2c8082cc0efd6afa51eb62f9c05ba9d0`.

## 17–19. Holdout TEST access and diagnostics

TEST was accessed once after all model choices were frozen. Test metrics and supported segment diagnostics are in `test_metrics.json` and `segment_metrics.csv`. No TEST label was used for feature selection, HPO, calibration selection, or retraining.

## 20. Reproducibility

{
  "best_iteration_first": 200,
  "best_iteration_second": 200,
  "max_probability_delta": 0.0,
  "metrics_first": {
    "average_precision": 0.2345912741210851,
    "brier_score": 0.14446562537988186,
    "ece": 0.0014885103538651529,
    "f1_at_0_5": 0.0,
    "log_loss": 0.4615397127791993,
    "non_purchase_count": 4311,
    "precision_at_0_5": 0.0,
    "purchase_count": 939,
    "purchase_rate": 0.17885714285714285,
    "recall_at_0_5": 0.0,
    "roc_auc": 0.5968302104555081,
    "row_count": 5250,
    "top_decile_lift": 1.4802981895633653,
    "top_decile_purchase_rate": 0.26476190476190475,
    "top_decile_tie_policy": "fractional inclusion at score cutoff"
  },
  "metrics_second": {
    "average_precision": 0.2345912741210851,
    "brier_score": 0.14446562537988186,
    "ece": 0.0014885103538651529,
    "f1_at_0_5": 0.0,
    "log_loss": 0.4615397127791993,
    "non_purchase_count": 4311,
    "precision_at_0_5": 0.0,
    "purchase_count": 939,
    "purchase_rate": 0.17885714285714285,
    "recall_at_0_5": 0.0,
    "roc_auc": 0.5968302104555081,
    "row_count": 5250,
    "top_decile_lift": 1.4802981895633653,
    "top_decile_purchase_rate": 0.26476190476190475,
    "top_decile_tie_policy": "fractional inclusion at score cutoff"
  },
  "native_max_probability_delta": 0.0,
  "status": "PASS",
  "tolerance": 1e-10
}

## 21. Compute performance

Timings are in `compute_environment.json`, `compute_benchmark.json`, and the per-fold screening/HPO artifacts.

## 22–23. Known limitations and downstream risks

Upstream limitations remain: sparse competitor history, sparse Product×Store history, sparse promotion coverage, quantity concentration, temporal missingness drift, weak Phase 3 linear purchase signal, and observational/synthetic data that do not identify causal elasticity. Phase 5 must not treat this model as proof of causal demand response; Phase 6 must use candidate-price diagnostics as scenario sensitivity only.

## 24. Verdict

**PASS_WITH_WARNINGS**

Warnings:

- selected conditional context groups: BEHAVIOR_CONTEXT
- strict competitor history is sparse
- Product×Store history is sparse
- promotion coverage is sparse
- quantity target is concentrated
- several historical features have temporal missingness drift
- synthetic/observational data cannot prove causal elasticity
- Phase 3 linear purchase signal was extremely weak

Major blockers: **0**

- None

## 25. Recommendation

**PROCEED_TO_PHASE_5**
