import pandas as pd
import pytest

from features.feature_builder import _attach_price_history, _attach_promotions, build_feature_dataset_from_tables
from features.validation import enforce_point_in_time_acceptance, independent_point_in_time_validation


def _decision_base(**overrides):
    row = {
        "PricingDecisionID": "d1",
        "ProductID": "p1",
        "StoreID": "s1",
        "Channel": "Web",
        "DecisionTime": pd.Timestamp("2025-06-10 12:00:00"),
        "CurrentPrice": 40.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _history(rows):
    return {
        "Product_Price_History": pd.DataFrame(rows),
        "Promotions": pd.DataFrame(columns=["PromotionID", "DiscountPct", "StartDate", "EndDate", "ActiveFlag"]),
    }


def _history_row(store, channel, price, promotion=None, history_id=None):
    return {
        "PriceHistoryID": history_id or f"h-{store}-{channel}-{price}",
        "ProductID": "p1",
        "StoreID": store,
        "Channel": channel,
        "BasePrice": 50.0,
        "SellingPrice": price,
        "DiscountPct": 0.1,
        "PromotionID": promotion,
        "EffectiveFrom": "2025-01-01",
        "EffectiveTo": None,
    }


def test_price_history_rejects_unrelated_store_and_channel():
    base = _decision_base()
    tables = _history([_history_row("s9", "Mobile", 9.0)])
    with pytest.raises(ValueError, match="coverage"):
        _attach_price_history(base, tables)


def test_price_history_uses_exact_then_store_generic_then_region_generic_scope():
    base = _decision_base()
    tables = _history([
        _history_row(None, None, 10.0, history_id="generic-generic"),
        _history_row(None, "Web", 20.0, history_id="generic-exact-channel"),
        _history_row("s1", None, 30.0, history_id="exact-store-generic-channel"),
        _history_row("s1", "Web", 40.0, history_id="exact-exact"),
    ])
    selected, _ = _attach_price_history(base, tables)
    assert selected.loc[0, "active_history_selling_price"] == 40.0
    assert selected.loc[0, "active_price_history_id"] == "exact-exact"

    tables = _history([
        _history_row(None, "Web", 20.0, history_id="generic-exact-channel"),
        _history_row("s1", None, 30.0, history_id="exact-store-generic-channel"),
    ])
    selected, _ = _attach_price_history(base, tables)
    assert selected.loc[0, "active_history_selling_price"] == 30.0


def test_promotion_scope_rejects_unrelated_history_and_preserves_history_id():
    base = _decision_base(active_history_promotion_id="P_BAD")
    tables = _history([_history_row("s9", "Mobile", 9.0, promotion="P_BAD")])
    tables["Promotions"] = pd.DataFrame([{
        "PromotionID": "P_BAD", "DiscountPct": 0.5,
        "StartDate": "2025-01-01", "EndDate": "2025-12-31", "ActiveFlag": 1,
    }])
    selected, diagnostics = _attach_promotions(base, tables)
    assert selected.loc[0, "active_history_promotion_id"] == "P_BAD"
    assert selected.loc[0, "active_promotion_flag"] == 0
    assert pd.isna(selected.loc[0, "active_promotion_id"])
    assert diagnostics["active_count"] == 0


def test_promotion_preserves_historical_id_separately_from_validated_active_id():
    base = _decision_base(active_history_promotion_id="P_STALE")
    tables = _history([_history_row("s1", "Web", 40.0, promotion="P_STALE")])
    tables["Promotions"] = pd.DataFrame([{
        "PromotionID": "P_STALE", "DiscountPct": 0.5,
        "StartDate": "2024-01-01", "EndDate": "2024-12-31", "ActiveFlag": 1,
    }])
    selected, _ = _attach_promotions(base, tables)
    assert selected.loc[0, "active_history_promotion_id"] == "P_STALE"
    assert selected.loc[0, "active_promotion_flag"] == 0
    assert pd.isna(selected.loc[0, "active_promotion_id"])
    assert selected.loc[0, "selected_promotion_start_date"] == pd.Timestamp("2024-01-01")


def test_point_in_time_validation_counts_actual_audit_violations():
    frame = pd.DataFrame({
        "DecisionTime": [pd.Timestamp("2025-06-10 12:00:00"), pd.Timestamp("2025-06-11 12:00:00")],
        "selected_competitor_observed_at": [pd.Timestamp("2025-06-10 13:00:00"), pd.Timestamp("2025-06-11 11:00:00")],
        "selected_behavior_event_at": [pd.Timestamp("2025-06-10 12:00:01"), pd.Timestamp("2025-06-11 10:00:00")],
        "selected_sales_order_date": [pd.Timestamp("2025-06-10"), pd.Timestamp("2025-06-10")],
        "selected_price_effective_from": [pd.Timestamp("2025-06-10 13:00:00"), pd.Timestamp("2025-06-01")],
        "selected_price_effective_to": [pd.NaT, pd.Timestamp("2025-06-11")],
        "active_history_promotion_id": ["P1", None],
        "selected_promotion_start_date": [pd.Timestamp("2025-06-11"), pd.NaT],
        "selected_promotion_end_date": [pd.Timestamp("2025-06-20"), pd.NaT],
        "active_promotion_flag": [1, 0],
    })
    result = independent_point_in_time_validation(frame)
    assert result["future_competitor_observations_used"] == 1
    assert result["future_behavioral_events_used"] == 1
    assert result["same_day_date_only_sales_used"] == 1
    assert result["future_sales_used"] == 0
    assert result["future_price_intervals_used"] == 2
    assert result["stale_promotion_associations_treated_active"] == 1
    assert result["invalid_promotion_overlap"] == 1
    assert result["historical_inventory_features"] == 0


def test_point_in_time_acceptance_blocks_actual_audit_violations():
    frame = pd.DataFrame({
        "DecisionTime": [pd.Timestamp("2025-06-10 12:00:00")],
        "selected_competitor_observed_at": [pd.Timestamp("2025-06-10 13:00:00")],
        "selected_behavior_event_at": [pd.Timestamp("2025-06-10 12:00:01")],
        "selected_sales_order_date": [pd.Timestamp("2025-06-10")],
        "selected_price_effective_from": [pd.Timestamp("2025-06-10 13:00:00")],
        "selected_price_effective_to": [pd.NaT],
        "active_history_promotion_id": ["P1"],
        "selected_promotion_start_date": [pd.Timestamp("2025-06-11")],
        "selected_promotion_end_date": [pd.Timestamp("2025-06-20")],
        "active_promotion_flag": [1],
    })
    point_in_time = independent_point_in_time_validation(frame)
    with pytest.raises(RuntimeError, match="POINT_IN_TIME_VALIDATION_FAILED"):
        enforce_point_in_time_acceptance(point_in_time)


def test_full_feature_fixture_emits_audit_sources_and_separates_promotion_ids():
    tables = {
        "Pricing_Decision_Log": pd.DataFrame([{
            "PricingDecisionID": "d1", "DecisionTime": "2025-06-10 12:00:00", "CustomerID": "c1",
            "SessionID": "sess1", "ProductID": "p1", "StoreID": "s1", "Channel": "Web",
            "CurrentPrice": 40.0, "AppliedPrice": 40.0, "PurchasedFlag": 1,
            "OrderLineID": "ol1", "QuantityPurchased": 1,
        }]),
        "Product": pd.DataFrame([{"ProductID": "p1", "CategoryID": "cat1", "BrandID": "brand1", "BasePrice": 50.0, "Season": "Summer"}]),
        "Store": pd.DataFrame([{"StoreID": "s1", "RegionID": "r1", "StoreType": "Retail"}]),
        "Region": pd.DataFrame([{"RegionID": "r1", "ClimateZone": "Temperate"}]),
        "Customer": pd.DataFrame([{"CustomerID": "c1", "LoyaltyTier": "Gold", "CustomerSegment": "Value", "PreferredChannel": "Web"}]),
        "Customer_Preferences": pd.DataFrame([{
            "CustomerID": "c1", "FavoriteCategoryID": "cat1", "FavoriteBrandID": "brand1",
            "PriceSensitivity": "Medium", "CategoryAffinityScore": 0.5, "BrandAffinityScore": 0.5,
        }]),
        "Product_Price_History": pd.DataFrame([_history_row("s1", "Web", 40.0, promotion="P1", history_id="h1")]),
        "Promotions": pd.DataFrame([{
            "PromotionID": "P1", "DiscountPct": 0.2, "StartDate": "2025-06-01", "EndDate": "2025-06-30", "ActiveFlag": 1,
        }]),
        "Competitor_Price": pd.DataFrame([{
            "CompetitorPriceID": "cp1", "ProductID": "p1", "RegionID": "r1", "CompetitorPrice": 42.0,
            "ObservedDateTime": "2025-06-10 11:00:00", "Channel": "Web",
        }]),
        "Sales_Order": pd.DataFrame(columns=["OrderID", "StoreID", "OrderDate", "OrderStatus"]),
        "Sales_Order_Line": pd.DataFrame(columns=["OrderLineID", "OrderID", "ProductID", "Qty"]),
        "Browsing_Events": pd.DataFrame(columns=["EventID", "CustomerID", "ProductID", "EventTime"]),
        "Cart_Events": pd.DataFrame(columns=["CartEventID", "CustomerID", "ProductID", "Action", "EventTime", "Quantity"]),
        "Search_Events": pd.DataFrame(columns=["SearchID", "CustomerID", "ClickedProductID", "EventTime"]),
        "Holiday": pd.DataFrame(columns=["HolidayID", "RegionID", "Date", "SalesImpactFactor"]),
        "Weather": pd.DataFrame(columns=["WeatherID", "RegionID", "Date", "TemperatureF", "Condition", "PrecipitationIn"]),
    }
    result = build_feature_dataset_from_tables(tables, ["Completed"], [7, 14, 30], [1, 24, 168, 720], 30)
    frame = result.frame
    assert frame.loc[0, "active_history_promotion_id"] == "P1"
    assert frame.loc[0, "active_promotion_id"] == "P1"
    assert frame.loc[0, "active_promotion_flag"] == 1
    assert frame.loc[0, "selected_price_effective_from"] == pd.Timestamp("2025-01-01")
    assert frame.loc[0, "selected_competitor_observed_at"] == pd.Timestamp("2025-06-10 11:00:00")
    assert frame.loc[0, "selected_behavior_event_at"] is pd.NaT or pd.isna(frame.loc[0, "selected_behavior_event_at"])
    for name in ["product_sales_velocity_7d", "product_sales_velocity_30d", "product_sales_velocity_90d"]:
        assert frame.loc[0, name] == 0.0
    assert pd.isna(frame.loc[0, "product_sales_velocity_ratio_7d_30d"])
    assert result.diagnostics["price_history"]["future_intervals_used"] == 0
