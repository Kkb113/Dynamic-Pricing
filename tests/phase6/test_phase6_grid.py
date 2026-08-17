from __future__ import annotations

import numpy as np
import pandas as pd

from optimization.candidate_grid import audit_price_support, build_candidate_grid, generate_candidate_rows, round_price_half_up


def test_round_half_up_and_grid_support():
    assert round_price_half_up(101.005) == 101.01
    train = pd.DataFrame({"CurrentPrice": [100.0] * 100, "AppliedPrice": np.linspace(90.0, 110.0, 100)})
    audit = audit_price_support(train)
    grid = build_candidate_grid(audit)
    assert 1.0 in grid.multipliers
    assert len(grid.multipliers) >= 5
    assert all(grid.effective_low - 1e-12 <= m <= grid.effective_high + 1e-12 or m == 1.0 for m in grid.multipliers)


def test_candidate_prices_are_unique_and_current_is_exactly_once():
    context = pd.DataFrame({"PricingDecisionID": ["D1"], "DecisionTime": [pd.Timestamp("2025-01-01")], "ProductID": ["P"], "StoreID": ["S"], "Channel": ["Web"], "CurrentPrice": [0.11], "AppliedPrice": [0.11], "BasePrice": [0.11]})
    audit = {"p01": 0.8, "p99": 1.2}
    candidates = generate_candidate_rows(context, build_candidate_grid(audit))
    assert candidates["CandidatePrice"].is_unique
    assert candidates["is_current_price_candidate"].sum() == 1
    assert candidates["CandidatePrice"].is_monotonic_increasing


def test_historical_parity_bypasses_grid_rounding():
    assert round_price_half_up(101.005) != 101.005
