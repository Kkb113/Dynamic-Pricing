from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from features.feature_contract import load_contract


@pytest.fixture(scope="session")
def phase2_contract():
    return load_contract(Path(__file__).resolve().parents[2] / "contracts/phase2_feature_contract_v1.yaml")


@pytest.fixture()
def quantity_frame(phase2_contract):
    names = [item["name"] for item in phase2_contract["features"]]
    categorical = set(phase2_contract["feature_lists"]["categorical_features"])
    rows = 18
    result: dict[str, object] = {}
    for name in names:
        if name == "PricingDecisionID":
            result[name] = [f"FIX-{i:04d}" for i in range(rows)]
        elif name == "DecisionTime":
            result[name] = pd.date_range("2025-01-01", periods=rows, freq="h")
        elif name in categorical:
            result[name] = [f"level-{i % 3}" for i in range(rows)]
        elif name == "PurchasedFlag":
            result[name] = np.array([1 if i % 2 == 0 else 0 for i in range(rows)], dtype=np.int8)
        elif name == "QuantityPurchased":
            result[name] = np.array([1 + (i % 3) if i % 2 == 0 else 0 for i in range(rows)], dtype=np.int64)
        else:
            result[name] = np.linspace(1.0, 2.0, rows)
    result["CurrentPrice"] = np.linspace(10.0, 20.0, rows)
    result["AppliedPrice"] = result["CurrentPrice"].copy()
    result["BasePrice"] = np.linspace(12.0, 22.0, rows)
    result["competitor_price"] = np.linspace(9.0, 19.0, rows)
    result["price_change_amount"] = result["AppliedPrice"] - result["CurrentPrice"]
    result["price_change_pct"] = result["price_change_amount"] / result["CurrentPrice"]
    result["price_vs_base_pct"] = (result["AppliedPrice"] - result["BasePrice"]) / result["BasePrice"]
    result["current_vs_base_pct"] = (result["CurrentPrice"] - result["BasePrice"]) / result["BasePrice"]
    result["discount_from_base_pct"] = (result["BasePrice"] - result["AppliedPrice"]) / result["BasePrice"]
    result["price_vs_competitor_pct"] = (result["AppliedPrice"] - result["competitor_price"]) / result["competitor_price"]
    return pd.DataFrame(result)
