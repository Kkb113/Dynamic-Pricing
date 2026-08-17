# Phase 6 Candidate Simulation Report

Phase 6 evaluates deterministic candidate-price scenarios using the frozen Phase 4 native probability model and the official Phase 5 estimator. It is observational scenario modelling, not causal elasticity.

## Support

TRAIN AppliedPrice/CurrentPrice p01=0.892998, p99=1.117389; effective envelope=[0.892998, 1.117389]. Candidates: `[0.9, 0.925, 0.95, 0.975, 1.0, 1.025, 1.05, 1.075, 1.1]`. Prices use Decimal `ROUND_HALF_UP` to cents.

## Response safety

Raw expected units are retained. The optimizer-safe series is the low-price-to-high-price cumulative minimum, so it cannot increase with price. This is a conservative shape guard, not a trained model or calibration step.

Historical validation parity: `PASS`; TEST parity: `PASS`.

## Limitations

Inventory and Pricing_Rules are intentionally not applied in Phase 6. CostPrice is a static Product reference used only after model inference.
