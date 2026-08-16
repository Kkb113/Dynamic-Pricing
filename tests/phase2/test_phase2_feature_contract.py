from pathlib import Path

import pytest

from features.feature_contract import load_contract, model_feature_columns, validate_model_feature_columns


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
    assert "ProductID" in features
    assert "StoreID" in features
