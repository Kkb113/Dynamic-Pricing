from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from models.catboost_data import (
    build_feature_families,
    build_purchase_model_features_for_candidate_price,
    make_catboost_pool,
    prepare_catboost_frame,
    validate_feature_schema,
)


ROOT = Path(__file__).resolve().parents[2]


def _fixture() -> tuple[pd.DataFrame, dict, tuple[str, ...]]:
    contract = yaml.safe_load((ROOT / "contracts/phase2_feature_contract_v1.yaml").read_text(encoding="utf-8"))
    frame = pd.read_parquet(ROOT / "artifacts/phase2/feature_dataset.parquet").head(40).copy()
    family = build_feature_families(contract)["F0_CORE"]
    return frame, contract, family.feature_names


def test_native_adapter_preserves_order_categories_and_numeric_nan() -> None:
    frame, contract, feature_names = _fixture()
    frame.loc[frame.index[0], "weather_condition"] = None
    frame.loc[frame.index[1], "weather_temperature"] = np.nan
    prepared = prepare_catboost_frame(frame, contract, feature_names)
    assert list(prepared.columns) == list(feature_names)
    assert prepared["weather_condition"].iloc[0] == "__MISSING__"
    assert np.isnan(prepared["weather_temperature"].iloc[1])
    pool = make_catboost_pool(frame, contract, feature_names, frame["PurchasedFlag"])
    assert pool.get_cat_feature_indices() == [feature_names.index(name) for name in ["CategoryID", "BrandID", "Season", "StoreType", "RegionID", "ClimateZone", "Channel", "weather_condition"]]


def test_candidate_price_adapter_recreates_historical_input() -> None:
    frame, contract, feature_names = _fixture()
    historical = prepare_catboost_frame(frame, contract, feature_names)
    candidate = build_purchase_model_features_for_candidate_price(frame, frame["AppliedPrice"].to_numpy(), contract, feature_names)
    categorical = set(contract["feature_lists"]["categorical_features"])
    for column in feature_names:
        if column in categorical:
            assert historical[column].astype(str).equals(candidate[column].astype(str))
        else:
            assert np.allclose(historical[column].to_numpy(dtype=float), candidate[column].to_numpy(dtype=float), equal_nan=True, atol=1e-12, rtol=1e-12)
    validate_feature_schema(historical, candidate, feature_names)


def test_catboost_adapter_does_not_one_hot_or_target_encode() -> None:
    source = (ROOT / "src/models/catboost_data.py").read_text(encoding="utf-8")
    assert "OneHotEncoder" not in source
    assert "target_encode" not in source
    assert "cat_features" in source

