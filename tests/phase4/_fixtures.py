from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from features.price_features import build_price_dependent_features
from models.catboost_data import build_feature_families


ROOT = Path(__file__).resolve().parents[2]


def phase4_contract() -> dict:
    return yaml.safe_load((ROOT / "contracts/phase2_feature_contract_v1.yaml").read_text(encoding="utf-8"))


def phase4_fixture_frame(rows: int = 180) -> tuple[pd.DataFrame, dict, tuple[str, ...]]:
    contract = phase4_contract()
    feature_names = build_feature_families(contract)["F0_CORE"].feature_names
    frame = pd.DataFrame(index=np.arange(rows))
    categorical = set(contract["feature_lists"]["categorical_features"])
    for index, name in enumerate(feature_names):
        if name in categorical:
            frame[name] = np.where(np.arange(rows) % 3 == 0, "A", np.where(np.arange(rows) % 3 == 1, "B", None))
        else:
            frame[name] = 1.0 + (np.arange(rows) + index) / 100.0
    frame["PricingDecisionID"] = [f"FIX{index:06d}" for index in range(rows)]
    frame["DecisionTime"] = pd.date_range("2025-01-01", periods=rows, freq="h")
    frame["PurchasedFlag"] = (np.arange(rows) % 5 == 0).astype("int8")
    frame["QuantityPurchased"] = frame["PurchasedFlag"].astype(int)
    frame["CurrentPrice"] = 10.0 + np.arange(rows) / 100.0
    frame["AppliedPrice"] = frame["CurrentPrice"] * (1.0 + ((np.arange(rows) % 5) - 2) / 100.0)
    frame["BasePrice"] = 12.0
    frame["competitor_price"] = 11.0
    rebuilt = build_price_dependent_features(frame["AppliedPrice"], frame["CurrentPrice"], frame["BasePrice"], frame["competitor_price"])
    for name in ["price_change_amount", "price_change_pct", "price_vs_base_pct", "discount_from_base_pct", "price_vs_competitor_pct", "current_vs_base_pct"]:
        if name in frame:
            frame[name] = rebuilt[name].to_numpy()
    return frame, contract, feature_names


