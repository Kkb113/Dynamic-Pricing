import pytest

from audit.leakage_analysis import build_leakage_matrix, validate_candidate_features


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
