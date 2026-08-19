# Phase 8 Factual Backtest Report

## Purpose

This report evaluates predictions at the historical `AppliedPrice`, where the
outcomes are observed. Alternative-price results are reported separately as
model-implied scenario estimates.

## TEST purchase model

| Metric | Value |
|---|---:|
| ROC-AUC | 0.6093393176304454 |
| Average Precision | 0.24523451977509367 |
| Log Loss | 0.46908721778657386 |
| Brier Score | 0.14786924715837632 |
| Top-decile lift | 1.491769547325103 |
| Phase 4 probability parity max delta | 0.0 |
| Phase 5 expected-unit parity max delta | 0.0 |

## Factual demand, revenue, and gross profit

{
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
  }
}

Observed gross profit is a proxy using static `Product.CostPrice`; historical
cost snapshots were not available. Ordinary MAPE is intentionally omitted
because many historical decisions have zero units.

## Calibration and segments

The probability-decile CSV and supported-segment CSV contain the complete
decile and segment evidence. Segment warnings are measured diagnostics, not
single-row failures.

## Limitations

Historical inventory is not used for this backtest. The observed economics are
descriptive at the offered price and do not establish what an alternative
price would have produced.
