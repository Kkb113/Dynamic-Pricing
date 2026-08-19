from app_services.recommendation_service import RecommendationService


def test_known_recommendation_matches_phase7_artifact(registry):
    source = registry.load_decisions("validation").sort_values("PricingDecisionID").iloc[0]
    result = RecommendationService(registry).get_pricing_recommendation(str(source["PricingDecisionID"]))
    assert result["CurrentPrice"] == float(source["CurrentPrice"])
    assert result["FinalRecommendedPrice"] == float(source["FinalRecommendedPrice"])
    assert result["FinalAction"] == source["FinalAction"]
    assert set(result["reason_codes"]) == set(source["phase7_change_reason_codes"])
    assert "PurchasedFlag" not in result and "ActualRevenue" not in result


def test_search_filters_and_limit(registry):
    service = RecommendationService(registry)
    source = registry.load_decisions("validation").sort_values("PricingDecisionID").iloc[0]
    rows = service.search_recommendations(ProductID=source["ProductID"], StoreID=source["StoreID"], Channel=source["Channel"], limit=1)
    assert len(rows) <= 1
    assert rows and rows[0]["ProductID"] == source["ProductID"]
    assert len(service.search_recommendations(limit=1000)) <= 100


def test_manual_review_filter_is_supported(registry):
    service = RecommendationService(registry)
    rows = service.search_recommendations(manual_review_flag=True, limit=100)
    assert all(row["manual_review_flag"] for row in rows)
