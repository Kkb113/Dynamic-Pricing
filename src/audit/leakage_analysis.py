from __future__ import annotations

from collections.abc import Iterable

TARGETS = {"Pricing_Decision_Log.PurchasedFlag", "Pricing_Decision_Log.QuantityPurchased"}

SYNTHETIC_POLICY_OUTPUTS = {
    "Pricing_Decision_Log.RecommendedPrice", "Pricing_Decision_Log.ExpectedDemand",
    "Pricing_Decision_Log.PurchaseProbability", "Pricing_Decision_Log.PriceElasticity",
    "Pricing_Decision_Log.ExpectedRevenue", "Pricing_Decision_Log.ExpectedMarginPct",
    "Pricing_Decision_Log.ModelVersion", "Pricing_Decision_Log.ReasonCode",
    "Recommendation_Log.Score", "Recommendation_Log.ModelVersion",
    "Recommendation_Log.InventoryAvailable", "Recommendation_Log.RankPosition",
    "Recommendation_Log.RecommendationStrategy",
}

POST_OUTCOME = {
    "Pricing_Decision_Log.ActualRevenue", "Pricing_Decision_Log.OutcomeTime",
    "Pricing_Decision_Log.OrderLineID",
}

PII = {
    "Customer.FirstName", "Customer.LastName", "Customer.Email",
    "Customer.Gender", "Customer.BirthDate", "Ratings.ReviewText",
}

OPTIMIZATION_ONLY = {"Product.CostPrice", "Product.MarginPct"}

RAW_ALLOWED = {
    "Pricing_Decision_Log.DecisionTime", "Pricing_Decision_Log.AppliedPrice",
    "Pricing_Decision_Log.CurrentPrice", "Pricing_Decision_Log.Channel",
    "Product.BasePrice", "Product.Season", "Product.Color", "Product.Size", "Product.ActiveFlag",
    "Brand.BrandTier", "Brand.ActiveFlag", "Product_Category.CategoryLevel",
    "Product_Category.DepartmentName", "Store.StoreType", "Store.OpenDate", "Store.StoreStatus",
    "Region.State", "Region.ClimateZone", "Region.TimeZone",
}

CONDITIONAL_RAW = {
    "Pricing_Decision_Log.ProductID", "Pricing_Decision_Log.StoreID",
    "Product.CategoryID", "Product.BrandID", "Store.RegionID",
    "Customer.CustomerSegment", "Customer.LoyaltyTier", "Customer.PreferredChannel",
    "Customer.CustomerStatus", "Customer.RegionID", "Customer_Preferences.PriceSensitivity",
    "Customer_Preferences.CategoryAffinityScore", "Customer_Preferences.BrandAffinityScore",
}

DERIVATION_TABLES = {
    "Sales_Order", "Sales_Order_Line", "Browsing_Events", "Cart_Events", "Search_Events",
    "Product_Price_History", "Competitor_Price", "Promotions", "Holiday", "Weather",
    "Ratings", "Wishlist", "Recommendation_Response",
}

JOIN_ONLY_COLUMNS = {
    "PricingDecisionID", "SessionID", "CustomerID", "PromotionID", "PricingRuleID",
    "OrderID", "OrderLineID", "RecommendationID", "RecommendationBatchID", "ResponseID",
    "EventID", "CartEventID", "SearchID", "WishlistID", "RatingID", "WeatherID",
    "HolidayID", "PriceHistoryID", "CompetitorPriceID", "InventoryID", "PreferenceID",
}

# Phase 2 must build from this explicit list. Unknown names fail closed.
PHASE2_FEATURE_ALLOWLIST = {
    "AppliedPrice", "CurrentPrice", "BasePrice", "Season", "Channel", "ProductID", "StoreID", "CategoryID", "BrandID",
    "StoreType", "RegionID", "ClimateZone", "CustomerSegment", "LoyaltyTier", "PreferredChannel",
    "PriceSensitivity", "CategoryAffinityScore", "BrandAffinityScore",
    "is_holiday", "holiday_sales_impact_factor", "weather_temperature", "weather_condition",
    "weather_precipitation", "active_promotion_flag", "active_promotion_discount_pct",
    "product_store_sales_7d", "product_store_sales_14d", "product_store_sales_30d",
    "product_region_sales_7d", "product_region_sales_14d", "product_region_sales_30d",
    "product_sales_7d", "product_sales_14d", "product_sales_30d", "product_sales_60d", "product_sales_90d",
    "category_store_sales_7d", "category_store_sales_14d", "category_store_sales_30d",
    "category_sales_7d", "category_sales_14d", "category_sales_30d",
    "product_views_1h", "product_views_24h", "product_views_7d", "product_views_30d",
    "cart_additions_1h", "cart_additions_24h", "cart_additions_7d", "cart_additions_30d",
    "search_clicks_1h", "search_clicks_24h", "search_clicks_7d", "search_clicks_30d",
    "competitor_price_available", "competitor_price_age_days", "competitor_price_exact_channel",
    "competitor_price_region_fallback", "competitor_price_product_fallback", "price_vs_competitor_pct",
}

CONDITIONAL_FEATURES = {
    "ProductID", "StoreID", "CustomerSegment", "LoyaltyTier", "PreferredChannel",
    "PriceSensitivity", "CategoryAffinityScore", "BrandAffinityScore", "RegionID",
}


def classify(source_table: str, column: str) -> tuple[str, str]:
    qualified = f"{source_table}.{column}"
    if qualified in TARGETS:
        return "TARGET", "Locked model target; never an inference-time predictor"
    if qualified in SYNTHETIC_POLICY_OUTPUTS:
        return "PROHIBITED_SYNTHETIC_POLICY_OUTPUT", "Synthetic model, ranking, inventory-policy, or optimizer output"
    if qualified in POST_OUTCOME:
        return "PROHIBITED_POST_OUTCOME", "Observed only after the pricing decision outcome"
    if qualified in PII:
        return "PROHIBITED_PRIVACY_OR_IRRELEVANT", "Direct personal or free-text attribute is unnecessary for pricing"
    if source_table == "Inventory":
        return "PROHIBITED_HISTORICAL_FEATURE", "Snapshot inventory is optimizer-only and cannot be back/forward-filled"
    if source_table == "Pricing_Rules" or qualified in OPTIMIZATION_ONLY:
        return "OPTIMIZATION_ONLY", "Commercial cost/rule input belongs to the optimizer, not either ML model"
    if qualified in RAW_ALLOWED:
        return "ALLOWED_PRE_DECISION", "Explicit raw-feature allowlist; still subject to point-in-time validation"
    if qualified in CONDITIONAL_RAW:
        return "CONDITIONAL_PRE_DECISION", "Explicit conditional allowlist; requires coverage, sparsity, fairness, or proxy approval"
    if column in JOIN_ONLY_COLUMNS or column.endswith("ID"):
        return "JOIN_ONLY_IDENTIFIER", "Join key only; not an unrestricted raw model feature"
    if source_table in DERIVATION_TABLES:
        return "DERIVATION_ONLY", "Raw event/outcome is allowed only through leakage-safe historical aggregation"
    if source_table == "Recommendation_Log":
        return "PROHIBITED_SYNTHETIC_POLICY_OUTPUT", "Recommendation-system field is not an approved pricing-model input"
    return "PROHIBITED_UNREVIEWED", "Deny-by-default: column is not on the explicit Phase 2 raw-feature allowlist"


def build_leakage_matrix(columns: list[dict]) -> list[dict]:
    result = []
    for item in columns:
        table, column = item["source_table"], item["column_name"]
        qualified = f"{table}.{column}"
        classification, reason = classify(table, column)
        model_allowed = classification in {"ALLOWED_PRE_DECISION", "CONDITIONAL_PRE_DECISION"}
        result.append({
            "source_table": table,
            "column": column,
            "classification": classification,
            "allowed_purchase_model": "TARGET" if qualified == "Pricing_Decision_Log.PurchasedFlag" else model_allowed,
            "allowed_quantity_model": "TARGET" if qualified == "Pricing_Decision_Log.QuantityPurchased" else model_allowed,
            "allowed_optimizer": classification in {"ALLOWED_PRE_DECISION", "CONDITIONAL_PRE_DECISION", "OPTIMIZATION_ONLY", "PROHIBITED_HISTORICAL_FEATURE"},
            "available_at_decision_time": classification not in {"PROHIBITED_POST_OUTCOME", "TARGET"},
            "leakage_risk": "HIGH" if classification.startswith("PROHIBITED") or classification == "TARGET" else "MEDIUM" if classification in {"CONDITIONAL_PRE_DECISION", "DERIVATION_ONLY"} else "LOW",
            "privacy_risk": "HIGH" if qualified in PII else "MEDIUM" if table.startswith("Customer") else "LOW",
            "reason": reason,
            "notes": "Current-state optimizer use only" if table == "Inventory" else "Raw values must not be fed to ML" if classification == "DERIVATION_ONLY" else "",
        })
    return result


def validate_candidate_features(fields: Iterable[str], *, approved_conditional: Iterable[str] = ()) -> None:
    approved = set(approved_conditional)
    candidates = set(fields)
    unknown = candidates - PHASE2_FEATURE_ALLOWLIST
    unapproved_conditional = (candidates & CONDITIONAL_FEATURES) - approved
    if unknown:
        raise ValueError(f"Fields are not on the explicit Phase 2 feature allowlist: {sorted(unknown)}")
    if unapproved_conditional:
        raise ValueError(f"Conditional features require explicit approval: {sorted(unapproved_conditional)}")
