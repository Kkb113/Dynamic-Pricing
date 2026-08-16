# Phase 4 Feature Selection Report

## Screening protocol

Feature-family screening used only the three locked expanding-window folds inside TRAIN. Official VALIDATION and TEST were not accessed. The CatBoost screening configuration was fixed (`iterations=1500`, `learning_rate=0.05`, `depth=6`, `l2_leaf_reg=5`, Bayesian bootstrap, seed 42, early stopping 150) and was not tuned.

## Results

| Family | Features | Mean Log Loss | Mean Brier | Mean AP | Mean ROC-AUC |
|---|---:|---:|---:|---:|---:|
| F0_CORE | 53 | 0.469076 | 0.146576 | 0.186267 | 0.511158 |
| F1_CORE_HIGH_CARDINALITY | 55 | 0.468692 | 0.146463 | 0.189620 | 0.516383 |
| F2_CORE_COMPETITOR | 61 | 0.469243 | 0.146629 | 0.182189 | 0.506404 |
| F3_CORE_BEHAVIOR | 65 | 0.459941 | 0.143898 | 0.236384 | 0.604103 |
| F4_CORE_CUSTOMER | 59 | 0.468427 | 0.146394 | 0.193078 | 0.527846 |
| F5_CORE_HIGH_CARDINALITY_COMPETITOR | 63 | 0.469368 | 0.146667 | 0.184103 | 0.506436 |
| F6_CORE_HIGH_CARDINALITY_BEHAVIOR | 67 | 0.460410 | 0.144005 | 0.233207 | 0.601635 |
| F7_CORE_HIGH_CARDINALITY_COMPETITOR_BEHAVIOR | 75 | 0.460285 | 0.144008 | 0.233527 | 0.601890 |
| F8_CORE_ALL_APPROVED_CONTEXT | 81 | 0.460084 | 0.143912 | 0.234286 | 0.603598 |

## Decision

- Selected family: **F3_CORE_BEHAVIOR**
- Selected feature count: **65**
- Non-customer reference: **F3_CORE_BEHAVIOR**
- Customer context selected: **False**
- Customer-eligible families: `[]`
- CORE remained a reference candidate throughout.

The primary criterion was mean temporal-fold Log Loss, followed by Brier Score, then AP, AUC, and stability. Near ties were resolved in favor of the simpler family when Log Loss differed by less than 0.001 and Brier by less than 0.0005. Customer context required at least 0.002 mean Log Loss improvement, no Brier deterioration, and improvement in at least two folds.

## Leakage and eligibility

All feature names came from the Phase 2 contract. Conditional context was admitted only through explicit Phase 4 groups. PII, identifiers, targets, inventory, pricing-rule outputs, optimizer-only outputs, and post-outcome columns were rejected. CatBoost used native categorical features; no one-hot, target, mean, or frequency encoding was used.
