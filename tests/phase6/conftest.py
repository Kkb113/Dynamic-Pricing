from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture()
def candidate_surface():
    rows = []
    for decision in ["D1", "D2"]:
        for rank, price in enumerate([90.0, 100.0, 110.0, 120.0]):
            raw = [0.30, 0.28, 0.29, 0.24][rank]
            rows.append({
                "PricingDecisionID": decision,
                "DecisionTime": pd.Timestamp("2025-01-01"),
                "ProductID": "P1", "StoreID": "S1", "Channel": "Web",
                "CurrentPrice": 100.0, "AppliedPrice": 100.0, "BasePrice": 100.0, "CostPrice": 70.0,
                "candidate_multiplier": price / 100.0, "CandidatePrice": price, "candidate_rank_by_price": rank,
                "is_current_price_candidate": price == 100.0,
                "is_support_lower_boundary": rank == 0, "is_support_upper_boundary": rank == 3,
                "raw_purchase_probability": raw, "conditional_quantity": 1.0,
                "raw_expected_units": raw,
            })
    return pd.DataFrame(rows)
