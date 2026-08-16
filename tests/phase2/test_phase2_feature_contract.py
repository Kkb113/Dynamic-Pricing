from pathlib import Path

import pandas as pd
import pytest

from features.feature_contract import load_contract, model_feature_columns, validate_model_feature_columns
from features.validation import coverage_report


ROOT = Path(__file__).resolve().parents[2]


def test_every_contract_feature_has_explicit_role_and_metadata():
    contract = load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")
    assert len(contract["features"]) >= 80
    assert all(item["role"] for item in contract["features"])
    assert all("point_in_time_rule" in item and "price_dependent" in item for item in contract["features"])


def test_unknown_features_fail_closed():
    contract = load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")
    with pytest.raises(ValueError, match="Unknown"):
        validate_model_feature_columns(["not_approved"], contract)


def test_targets_audit_keys_and_optimizer_outputs_are_not_model_features():
    contract = load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")
    features = model_feature_columns(contract)
    forbidden = {"PurchasedFlag", "QuantityPurchased", "PricingDecisionID", "CustomerID", "CostPrice", "MarginPct", "RecommendedPrice", "ExpectedDemand"}
    assert forbidden.isdisjoint(features)
    assert "ProductID" not in features
    assert "StoreID" not in features
    assert "FavoriteCategoryID" not in features
    assert "FavoriteBrandID" not in features


def test_conditional_features_require_explicit_approval():
    contract = load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")
    with pytest.raises(ValueError, match="require approved_conditional_features"):
        model_feature_columns(contract, include_conditional=True)
    approved = model_feature_columns(contract, approved_conditional_features=["ProductID", "StoreID"])
    assert "ProductID" in approved
    assert "StoreID" in approved
    assert "FavoriteCategoryID" not in approved


def test_favorite_preference_ids_are_join_only():
    contract = load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")
    entries = {feature["name"]: feature for feature in contract["features"]}
    for name in ["FavoriteCategoryID", "FavoriteBrandID"]:
        assert entries[name]["role"] == "JOIN_ONLY"
        assert entries[name]["model_eligible"] is False


def test_coverage_report_includes_all_model_eligible_features():
    contract = load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")
    frame = pd.DataFrame({feature["name"]: [0] for feature in contract["features"]})
    report = coverage_report(frame, contract)
    eligible = {feature["name"] for feature in contract["features"] if feature["model_eligible"]}
    assert set(report["feature_name"]) == eligible
    assert {"ProductID", "StoreID", "competitor_price", "product_views_1h", "CustomerSegment"}.issubset(eligible)
