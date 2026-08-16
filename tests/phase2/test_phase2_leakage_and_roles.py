from pathlib import Path

from features.feature_contract import load_contract, model_feature_columns


def test_inventory_cost_margin_rules_and_recommendation_outputs_are_absent():
    contract = load_contract(Path(__file__).resolve().parents[2] / "contracts/phase2_feature_contract_v1.yaml")
    model = set(model_feature_columns(contract)) | set(model_feature_columns(contract, "quantity"))
    forbidden_tokens = ("Inventory", "CostPrice", "MarginPct", "RecommendedPrice", "ExpectedDemand", "PurchaseProbability", "ActualRevenue", "OutcomeTime")
    assert not any(any(token in name for token in forbidden_tokens) for name in model)


def test_customer_direct_pii_is_not_contract_feature():
    contract = load_contract(Path(__file__).resolve().parents[2] / "contracts/phase2_feature_contract_v1.yaml")
    names = {feature["name"] for feature in contract["features"]}
    assert names.isdisjoint({"FirstName", "LastName", "Email", "BirthDate", "Gender", "ReviewText"})
