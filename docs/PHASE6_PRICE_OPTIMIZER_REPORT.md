# Phase 6 Price Optimizer Report

The official objective is expected gross profit `(CandidatePrice - CostPrice) * SafeExpectedUnits`. Revenue optimization is diagnostic only. Near ties use a 0.1% band, then closest-to-current price, then lower price. A non-current candidate must exceed the current candidate by at least 0.5% relative expected gross profit; otherwise the engine keeps the current price.

The output is `ModelOptimalCandidatePrice`, never a final business recommendation. Phase 7 owns price rules, margin floors, promotion/markdown actions, and inventory constraints.

Warnings measured by this run: ["OPTIMIZER_BOUNDARY_HEAVY", "OPTIMIZER_STRONGLY_BOUNDARY_SEEKING"]
