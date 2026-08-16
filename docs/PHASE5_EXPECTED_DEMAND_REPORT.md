# Phase 5 Expected Demand Report

Expected units are computed only as `Phase 4 official_probability × Phase 5 conditional_quantity`; actual `PurchasedFlag` is used only to form the evaluation target `ObservedUnits`.

## Validation

| Stack | MAE | RMSE | Poisson deviance | Aggregate units error % |
|---|---:|---:|---:|---:|
| P × mean Q | 0.376738 | 0.561405 | 0.828607 | 1.946587 |
| P × advanced Q | 0.377503 | 0.561376 | 0.828517 | 2.527160 |
| P × official Q | 0.376738 | 0.561405 | 0.828607 | 1.946587 |

The expected-unit decile table is `artifacts/phase5/expected_units_validation_calibration.csv`. Candidate-price parity is **True** with maximum expected-unit delta **0.000e+00**.

## Holdout

TEST was accessed once after the frozen specification. Full metrics are in `artifacts/phase5/test_expected_units_metrics.json` and the immutable prediction artifact.
