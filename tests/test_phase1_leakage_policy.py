import pytest

from audit.leakage_analysis import build_leakage_matrix, classify, validate_candidate_features


PROHIBITED = ["RecommendedPrice", "ExpectedDemand", "PurchaseProbability", "PriceElasticity",
              "ExpectedRevenue", "ExpectedMarginPct", "ModelVersion", "ReasonCode", "ActualRevenue",
              "OutcomeTime", "OrderLineID"]


@pytest.mark.parametrize("field", PROHIBITED)
def test_prohibited_fields_rejected(field):
    with pytest.raises(ValueError):
        validate_candidate_features(["AppliedPrice", field])


def test_applied_price_allowed():
    validate_candidate_features(["AppliedPrice", "CurrentPrice", "Season"])


def test_target_specific_fields_rejected_as_features():
    with pytest.raises(ValueError): validate_candidate_features(["QuantityPurchased"])
    with pytest.raises(ValueError): validate_candidate_features(["PurchasedFlag"])


def test_inventory_is_never_historical():
    rows = build_leakage_matrix([{"source_table":"Inventory","column_name":"OnHandQty"}])
    assert rows[0]["classification"] == "PROHIBITED_HISTORICAL_FEATURE"
    assert rows[0]["allowed_purchase_model"] is False
    assert rows[0]["allowed_optimizer"] is True


def test_direct_pii_is_prohibited():
    rows = build_leakage_matrix([{"source_table":"Customer","column_name":"Email"}])
    assert rows[0]["classification"] == "PROHIBITED_PRIVACY_OR_IRRELEVANT"


@pytest.mark.parametrize(("table", "column", "classification"), [
    ("Product", "CostPrice", "OPTIMIZATION_ONLY"),
    ("Product", "MarginPct", "OPTIMIZATION_ONLY"),
    ("Pricing_Rules", "MinPrice", "OPTIMIZATION_ONLY"),
    ("Pricing_Rules", "MaxDiscountPct", "OPTIMIZATION_ONLY"),
    ("Sales_Order", "NetAmount", "DERIVATION_ONLY"),
    ("Sales_Order_Line", "Qty", "DERIVATION_ONLY"),
    ("Recommendation_Log", "Score", "PROHIBITED_SYNTHETIC_POLICY_OUTPUT"),
    ("Recommendation_Log", "InventoryAvailable", "PROHIBITED_SYNTHETIC_POLICY_OUTPUT"),
    ("Recommendation_Response", "Purchased", "DERIVATION_ONLY"),
    ("Unreviewed_Table", "MysteryValue", "PROHIBITED_UNREVIEWED"),
])
def test_contract_specific_and_default_deny_classifications(table, column, classification):
    assert classify(table, column)[0] == classification


def test_optimizer_only_and_derivation_only_are_not_raw_model_features():
    rows = build_leakage_matrix([
        {"source_table":"Product","column_name":"CostPrice"},
        {"source_table":"Pricing_Rules","column_name":"MinPrice"},
        {"source_table":"Sales_Order_Line","column_name":"Qty"},
    ])
    assert all(row["allowed_purchase_model"] is False for row in rows)
    assert all(row["allowed_quantity_model"] is False for row in rows)
    assert rows[0]["allowed_optimizer"] is True and rows[1]["allowed_optimizer"] is True


def test_allowlist_fails_closed_for_unknown_or_optimization_fields():
    with pytest.raises(ValueError, match="explicit Phase 2 feature allowlist"):
        validate_candidate_features(["AppliedPrice", "CostPrice"])
    with pytest.raises(ValueError, match="explicit Phase 2 feature allowlist"):
        validate_candidate_features(["MysteryFeature"])


def test_conditional_allowlist_requires_explicit_approval():
    with pytest.raises(ValueError, match="require explicit approval"):
        validate_candidate_features(["ProductID"])
    validate_candidate_features(["ProductID"], approved_conditional=["ProductID"])
