from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from audit.database_profile import ReadOnlyConnection

from .price_features import build_price_dependent_features, safe_divide

LOG = logging.getLogger("phase2.features")


TABLE_COLUMNS = {
    "Pricing_Decision_Log": [
        "PricingDecisionID", "DecisionTime", "CustomerID", "SessionID", "ProductID", "StoreID", "Channel",
        "CurrentPrice", "AppliedPrice", "PurchasedFlag", "OrderLineID", "QuantityPurchased",
    ],
    "Product": ["ProductID", "CategoryID", "BrandID", "BasePrice", "Season"],
    "Store": ["StoreID", "RegionID", "StoreType"],
    "Region": ["RegionID", "ClimateZone"],
    "Customer": ["CustomerID", "LoyaltyTier", "CustomerSegment", "PreferredChannel"],
    "Customer_Preferences": [
        "CustomerID", "FavoriteCategoryID", "FavoriteBrandID", "PriceSensitivity",
        "CategoryAffinityScore", "BrandAffinityScore",
    ],
    "Product_Price_History": [
        "PriceHistoryID", "ProductID", "StoreID", "Channel", "BasePrice", "SellingPrice", "DiscountPct",
        "PromotionID", "EffectiveFrom", "EffectiveTo",
    ],
    "Promotions": ["PromotionID", "DiscountPct", "StartDate", "EndDate", "ActiveFlag"],
    "Competitor_Price": [
        "CompetitorPriceID", "ProductID", "RegionID", "CompetitorPrice", "ObservedDateTime", "Channel",
    ],
    "Sales_Order": ["OrderID", "StoreID", "OrderDate", "OrderStatus"],
    "Sales_Order_Line": ["OrderLineID", "OrderID", "ProductID", "Qty"],
    "Browsing_Events": ["EventID", "CustomerID", "ProductID", "EventTime"],
    "Cart_Events": ["CartEventID", "CustomerID", "ProductID", "Action", "EventTime", "Quantity"],
    "Search_Events": ["SearchID", "CustomerID", "ClickedProductID", "EventTime"],
    "Holiday": ["HolidayID", "RegionID", "Date", "SalesImpactFactor"],
    "Weather": ["WeatherID", "RegionID", "Date", "TemperatureF", "Condition", "PrecipitationIn"],
}


@dataclass
class FeatureBuildResult:
    frame: pd.DataFrame
    diagnostics: dict[str, Any]
    source_statuses: dict[str, list[dict[str, Any]]]


def _table_query(table: str, columns: Iterable[str], schema: str) -> str:
    quoted = ", ".join(f"[{column}]" for column in columns)
    return f"SELECT {quoted} FROM [{schema}].[{table}]"


def fetch_source_tables(db: ReadOnlyConnection, schema: str = "dbo") -> dict[str, pd.DataFrame]:
    """Fetch each source table once; all statements are SELECT-only."""
    tables: dict[str, pd.DataFrame] = {}
    for table, columns in TABLE_COLUMNS.items():
        rows = db.rows(_table_query(table, columns, schema))
        tables[table] = pd.DataFrame(rows, columns=columns)
        LOG.info("phase2_source_table=%s rows=%s", table, len(tables[table]))
    return tables


def _datetime(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def _numeric(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _normalize_key(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    return (value,)


def _window_aggregate(
    decisions: pd.DataFrame,
    events: pd.DataFrame,
    keys: list[str],
    event_time: str,
    value: str,
    prefix: str,
    windows: list[int],
    unit: str = "days",
) -> pd.DataFrame:
    """Compute historical windows with one in-memory grouped time-series pass."""
    result = pd.DataFrame(index=decisions.index)
    if events.empty:
        for window in windows:
            result[f"{prefix}_{window}{'h' if unit == 'hours' else 'd'}"] = 0.0
        return result
    event = events[keys + [event_time, value]].copy()
    event[event_time] = pd.to_datetime(event[event_time], errors="coerce")
    event[value] = pd.to_numeric(event[value], errors="coerce").fillna(0.0)
    event = event.dropna(subset=[event_time])
    if event.empty:
        for window in windows:
            result[f"{prefix}_{window}{'h' if unit == 'hours' else 'd'}"] = 0.0
        return result
    grouped = event.groupby(keys + [event_time], dropna=False, as_index=False, sort=True)[value].sum()
    grouped = grouped.sort_values(keys + [event_time], kind="mergesort")
    grouped["_cumulative"] = grouped.groupby(keys, dropna=False, sort=False)[value].cumsum()
    lookup: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray]] = {}
    for key, group in grouped.groupby(keys, dropna=False, sort=False):
        key_tuple = _normalize_key(key)
        lookup[key_tuple] = (
            group[event_time].astype("datetime64[ns]").to_numpy(),
            group["_cumulative"].astype(float).to_numpy(),
        )
    for window in windows:
        result[f"{prefix}_{window}{'h' if unit == 'hours' else 'd'}"] = 0.0
    for key, indices in decisions.groupby(keys, dropna=False, sort=False).groups.items():
        key_tuple = _normalize_key(key)
        series = lookup.get(key_tuple)
        if series is None:
            continue
        dates, cumulative = series
        decision_times = pd.to_datetime(decisions.loc[indices, "DecisionTime"]).astype("datetime64[ns]").to_numpy()
        if unit == "days":
            decision_times = decision_times.astype("datetime64[D]").astype("datetime64[ns]")
        for window in windows:
            delta = np.timedelta64(window, "h" if unit == "hours" else "D")
            end_side = "left" if unit == "days" else "right"
            end_positions = np.searchsorted(dates, decision_times, side=end_side) - 1
            start_positions = np.searchsorted(dates, decision_times - delta, side="left") - 1
            end_values = np.where(end_positions >= 0, cumulative[np.maximum(end_positions, 0)], 0.0)
            start_values = np.where(start_positions >= 0, cumulative[np.maximum(start_positions, 0)], 0.0)
            result.loc[indices, f"{prefix}_{window}{'h' if unit == 'hours' else 'd'}"] = end_values - start_values
    return result


def _last_event_age(decisions: pd.DataFrame, sales: pd.DataFrame) -> pd.Series:
    if sales.empty:
        return pd.Series(np.nan, index=decisions.index, dtype="float64")
    events = sales.groupby("ProductID", dropna=False)["OrderDate"].apply(
        lambda values: np.sort(pd.to_datetime(values).astype("datetime64[ns]").to_numpy())
    ).to_dict()
    values = pd.Series(np.nan, index=decisions.index, dtype="float64")
    for key, indices in decisions.groupby("ProductID", dropna=False, sort=False).groups.items():
        dates = events.get(key)
        if dates is None:
            continue
        decision_dates = pd.to_datetime(decisions.loc[indices, "DecisionTime"]).dt.normalize().astype("datetime64[ns]").to_numpy()
        positions = np.searchsorted(dates, decision_dates, side="left") - 1
        valid = positions >= 0
        result = np.full(len(indices), np.nan)
        if valid.any():
            result[valid] = (decision_dates[valid] - dates[positions[valid]]).astype("timedelta64[D]").astype(float)
        values.loc[indices] = result
    return values


def _prepare_base(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    decision = tables["Pricing_Decision_Log"].copy()
    _datetime(decision, ["DecisionTime"])
    _numeric(decision, ["CurrentPrice", "AppliedPrice", "PurchasedFlag", "QuantityPurchased"])
    product = _numeric(tables["Product"].copy(), ["BasePrice"])
    store = tables["Store"].copy()
    region = tables["Region"].copy()
    customer = tables["Customer"].copy()
    preferences = _numeric(tables["Customer_Preferences"].copy(), ["CategoryAffinityScore", "BrandAffinityScore"])
    frame = decision.merge(product, on="ProductID", how="left", validate="many_to_one")
    frame = frame.merge(store, on="StoreID", how="left", validate="many_to_one")
    frame = frame.merge(region, on="RegionID", how="left", validate="many_to_one")
    frame = frame.merge(customer, on="CustomerID", how="left", validate="many_to_one")
    frame = frame.merge(preferences, on="CustomerID", how="left", validate="many_to_one")
    frame = frame.drop(columns=["OrderLineID"], errors="ignore")
    if len(frame) != len(decision) or frame["PricingDecisionID"].duplicated().any():
        raise ValueError("Base-frame joins multiplied or dropped pricing decisions")
    return frame


def _attach_price_history(base: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    history = tables["Product_Price_History"].copy()
    _datetime(history, ["EffectiveFrom", "EffectiveTo"])
    _numeric(history, ["BasePrice", "SellingPrice", "DiscountPct"])
    history = history.sort_values(["ProductID", "StoreID", "Channel", "EffectiveFrom", "PriceHistoryID"], kind="mergesort")
    history["previous_selling_price"] = history.groupby(
        ["ProductID", "StoreID", "Channel"], dropna=False, sort=False
    )["SellingPrice"].shift(1)
    history["previous_price_change_pct"] = safe_divide(
        history["SellingPrice"] - history["previous_selling_price"], history["previous_selling_price"]
    ).to_numpy()
    left = base[["PricingDecisionID", "ProductID", "StoreID", "Channel", "DecisionTime", "CurrentPrice"]]
    candidates = left.merge(history, on="ProductID", how="left", suffixes=("", "_history"))
    active = candidates["EffectiveFrom"].le(candidates["DecisionTime"]) & (
        candidates["EffectiveTo"].isna() | candidates["DecisionTime"].lt(candidates["EffectiveTo"])
    )
    candidates = candidates.loc[active].copy()
    candidates["_scope_priority"] = np.where(
        candidates["StoreID_history"].eq(candidates["StoreID"]) & candidates["Channel_history"].eq(candidates["Channel"]), 0,
        np.where(candidates["StoreID_history"].isna() & candidates["Channel_history"].eq(candidates["Channel"]), 1, 2),
    )
    candidates = candidates.sort_values(
        ["PricingDecisionID", "_scope_priority", "EffectiveFrom", "PriceHistoryID"],
        ascending=[True, True, False, False], kind="mergesort"
    )
    selected = candidates.drop_duplicates("PricingDecisionID", keep="first")
    selected = selected.rename(columns={
        "BasePrice_history": "history_base_price", "SellingPrice": "active_history_selling_price",
        "DiscountPct": "history_discount_pct", "PromotionID": "active_history_promotion_id",
        "EffectiveFrom": "current_price_started_at", "EffectiveTo": "current_price_ended_at",
        "PriceHistoryID": "active_price_history_id",
    })
    selected["days_since_current_price_started"] = (
        selected["DecisionTime"] - selected["current_price_started_at"]
    ).dt.total_seconds() / 86400.0
    selected["price_history_current_price_delta"] = selected["CurrentPrice"] - selected["active_history_selling_price"]
    selected["price_history_current_price_mismatch"] = selected["price_history_current_price_delta"].abs().gt(1e-9)
    keep = [
        "PricingDecisionID", "active_history_selling_price", "history_discount_pct", "days_since_current_price_started",
        "previous_selling_price", "previous_price_change_pct", "active_history_promotion_id", "active_price_history_id",
        "price_history_current_price_delta", "price_history_current_price_mismatch", "_scope_priority",
    ]
    base = base.merge(selected[keep], on="PricingDecisionID", how="left", validate="one_to_one")
    diagnostics = {
        "decision_count": int(len(base)),
        "eligible_interval_count": int(len(selected)),
        "coverage_pct": round(float(selected["PricingDecisionID"].nunique() / len(base) * 100), 6) if len(base) else 0.0,
        "duplicate_selected_decisions": int(selected["PricingDecisionID"].duplicated().sum()),
        "future_intervals_used": 0,
        "current_price_mismatch_count": int(base["price_history_current_price_mismatch"].fillna(False).sum()),
    }
    if diagnostics["eligible_interval_count"] != len(base):
        raise ValueError("Price-history point-in-time coverage is not complete")
    return base, diagnostics


def _attach_promotions(base: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    history = tables["Product_Price_History"].copy()
    _datetime(history, ["EffectiveFrom", "EffectiveTo"])
    promotions = tables["Promotions"].copy()
    _datetime(promotions, ["StartDate", "EndDate"])
    _numeric(promotions, ["DiscountPct"])
    left = base[["PricingDecisionID", "ProductID", "StoreID", "Channel", "DecisionTime"]]
    candidates = left.merge(history, on="ProductID", how="left", suffixes=("", "_history"))
    interval_active = candidates["EffectiveFrom"].le(candidates["DecisionTime"]) & (
        candidates["EffectiveTo"].isna() | candidates["DecisionTime"].lt(candidates["EffectiveTo"])
    )
    candidates = candidates.loc[interval_active].copy()
    candidates = candidates.merge(
        promotions.rename(columns={"DiscountPct": "promotion_discount_pct", "StartDate": "promotion_start_date", "EndDate": "promotion_end_date"}),
        on="PromotionID", how="left", validate="many_to_one",
    )
    associations = history.loc[history["PromotionID"].notna()].merge(
        promotions[["PromotionID", "StartDate", "EndDate"]], on="PromotionID", how="left", validate="many_to_one"
    )
    association_stale = associations["PromotionID"].notna() & (
        associations["StartDate"].isna()
        | associations["EffectiveFrom"].dt.normalize().gt(associations["EndDate"])
        | associations["EffectiveTo"].fillna(associations["EffectiveFrom"]).dt.normalize().lt(associations["StartDate"])
    )
    decision_date = candidates["DecisionTime"].dt.normalize()
    active = candidates["PromotionID"].notna() & candidates["promotion_start_date"].le(decision_date) & candidates["promotion_end_date"].ge(decision_date)
    candidates = candidates.loc[active].copy()
    candidates["_scope_priority"] = np.where(
        candidates["StoreID_history"].eq(candidates["StoreID"]) & candidates["Channel_history"].eq(candidates["Channel"]), 0, 1
    )
    candidates = candidates.sort_values(
        ["PricingDecisionID", "_scope_priority", "EffectiveFrom", "PriceHistoryID"],
        ascending=[True, True, False, False], kind="mergesort"
    )
    selected = candidates.drop_duplicates("PricingDecisionID", keep="first")
    selected = selected.rename(columns={"PromotionID": "active_history_promotion_id"})
    selected = selected[["PricingDecisionID", "active_history_promotion_id", "promotion_discount_pct"]]
    merged = base.drop(columns=["active_history_promotion_id"], errors="ignore").merge(
        selected, on="PricingDecisionID", how="left", validate="one_to_one"
    )
    active = merged["active_history_promotion_id"].notna()
    merged["active_promotion_flag"] = active.astype("int8")
    merged["active_promotion_discount_pct"] = merged["promotion_discount_pct"].where(active)
    diagnostics = {
        "active_count": int(active.sum()),
        "coverage_pct": round(float(active.mean() * 100), 6),
        "stale_associations_treated_active": 0,
        "stale_association_count": int(association_stale.sum()),
    }
    return merged.drop(columns=["promotion_discount_pct"], errors="ignore"), diagnostics


def _sales_frame(tables: dict[str, pd.DataFrame], statuses: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    orders = tables["Sales_Order"].copy()
    lines = tables["Sales_Order_Line"].copy()
    _datetime(orders, ["OrderDate"])
    _numeric(lines, ["Qty"])
    observed_statuses = sorted(str(value) for value in orders["OrderStatus"].dropna().unique())
    eligible = orders["OrderStatus"].isin(statuses)
    sales = lines.merge(orders.loc[eligible, ["OrderID", "StoreID", "OrderDate", "OrderStatus"]], on="OrderID", how="inner", validate="many_to_one")
    sales = sales.rename(columns={"OrderDate": "OrderDate"})
    return sales, {"observed_statuses": observed_statuses, "eligible_statuses": statuses, "excluded_statuses": sorted(set(observed_statuses) - set(statuses)), "eligible_line_count": int(len(sales))}


def _attach_sales(base: pd.DataFrame, tables: dict[str, pd.DataFrame], statuses: list[str], windows: list[int]) -> tuple[pd.DataFrame, dict[str, Any]]:
    sales, status_diag = _sales_frame(tables, statuses)
    product_map = tables["Product"][["ProductID", "CategoryID"]].drop_duplicates("ProductID")
    store_map = tables["Store"][["StoreID", "RegionID"]].drop_duplicates("StoreID")
    sales = sales.merge(product_map, on="ProductID", how="left", validate="many_to_one")
    sales = sales.merge(store_map, on="StoreID", how="left", validate="many_to_one")
    families = [
        (["ProductID", "StoreID"], "product_store_sales"),
        (["ProductID", "RegionID"], "product_region_sales"),
        (["ProductID"], "product_sales"),
        (["CategoryID", "StoreID"], "category_store_sales"),
        (["CategoryID"], "category_sales"),
    ]
    family_windows = {
        "product_store_sales": [7, 14, 30], "product_region_sales": [7, 14, 30],
        "product_sales": [7, 14, 30, 60, 90], "category_store_sales": [7, 14, 30],
        "category_sales": [7, 14, 30],
    }
    for keys, prefix in families:
        values = _window_aggregate(base, sales, keys, "OrderDate", "Qty", prefix, family_windows[prefix])
        base = pd.concat([base, values], axis=1)
    base["product_sales_velocity_7d"] = safe_divide(base["product_sales_7d"], 7)
    base["product_sales_velocity_30d"] = safe_divide(base["product_sales_30d"], 30)
    base["product_sales_velocity_90d"] = safe_divide(base["product_sales_90d"], 90)
    base["product_sales_velocity_ratio_7d_30d"] = safe_divide(base["product_sales_velocity_7d"], base["product_sales_velocity_30d"])
    base["days_since_last_product_sale"] = _last_event_age(base, sales)
    coverage = {
        prefix: {
            str(window): round(float((base[f"{prefix}_{window}treplace" if False else f"{prefix}_{window}d"] > 0).mean() * 100), 6)
            for window in family_windows[prefix]
        }
        for _, prefix in families
    }
    status_diag["coverage"] = coverage
    return base, status_diag


def _latest_competitor(group: pd.DataFrame, decision_time: pd.Timestamp, cutoff_days: int) -> tuple[float | None, float | None, str | None]:
    if group.empty:
        return None, None, None
    times = group["ObservedDateTime"].astype("datetime64[ns]").to_numpy()
    position = int(np.searchsorted(times, np.datetime64(decision_time), side="right") - 1)
    if position < 0:
        return None, None, None
    observed = pd.Timestamp(times[position])
    age = (decision_time - observed).total_seconds() / 86400.0
    if age < 0 or age > cutoff_days:
        return None, None, None
    row = group.iloc[position]
    return float(row["CompetitorPrice"]), float(age), str(row["CompetitorPriceID"])


def _attach_competitor(base: pd.DataFrame, tables: dict[str, pd.DataFrame], window_days: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    competitor = tables["Competitor_Price"].copy()
    _datetime(competitor, ["ObservedDateTime"])
    _numeric(competitor, ["CompetitorPrice"])
    competitor = competitor.sort_values(["ProductID", "RegionID", "Channel", "ObservedDateTime", "CompetitorPriceID"], kind="mergesort")
    exact = {(key[0], key[1], key[2]): group.sort_values(["ObservedDateTime", "CompetitorPriceID"], kind="mergesort") for key, group in competitor.groupby(["ProductID", "RegionID", "Channel"], dropna=False, sort=False)}
    region = {(key[0], key[1]): group.sort_values(["ObservedDateTime", "CompetitorPriceID"], kind="mergesort") for key, group in competitor.groupby(["ProductID", "RegionID"], dropna=False, sort=False)}
    generic = competitor.loc[competitor["Channel"].isna() | competitor["Channel"].astype(str).str.strip().eq("")]
    region_generic = {(key[0], key[1]): group.sort_values(["ObservedDateTime", "CompetitorPriceID"], kind="mergesort") for key, group in generic.groupby(["ProductID", "RegionID"], dropna=False, sort=False)}
    product = {key: group.sort_values(["ObservedDateTime", "CompetitorPriceID"], kind="mergesort") for key, group in competitor.groupby("ProductID", dropna=False, sort=False)}
    columns = ["competitor_price_exact_channel", "competitor_price_region_fallback", "competitor_price_product_fallback"]
    for column in columns:
        base[column] = np.nan
    base["competitor_price_available"] = 0
    base["competitor_price_age_days"] = np.nan
    base["competitor_match_level"] = "NONE"
    generic_region_selected = 0
    for index, row in base.iterrows():
        decision_time = row["DecisionTime"]
        exact_value = _latest_competitor(exact.get((row["ProductID"], row["RegionID"], row["Channel"]), pd.DataFrame()), decision_time, window_days)
        generic_value = _latest_competitor(region_generic.get((row["ProductID"], row["RegionID"]), pd.DataFrame()), decision_time, window_days)
        region_value = generic_value if generic_value[0] is not None else _latest_competitor(region.get((row["ProductID"], row["RegionID"]), pd.DataFrame()), decision_time, window_days)
        product_value = _latest_competitor(product.get(row["ProductID"], pd.DataFrame()), decision_time, window_days)
        base.at[index, columns[0]] = exact_value[0]
        base.at[index, columns[1]] = region_value[0]
        base.at[index, columns[2]] = product_value[0]
        if exact_value[0] is not None:
            selected = exact_value; level = "EXACT"
        elif region_value[0] is not None:
            selected = region_value; level = "REGION_FALLBACK"
            if generic_value[0] is not None and selected[2] == generic_value[2]:
                generic_region_selected += 1
        elif product_value[0] is not None:
            selected = product_value; level = "PRODUCT_FALLBACK"
        else:
            selected = (None, None, None); level = "NONE"
        if selected[0] is not None:
            base.at[index, "competitor_price_available"] = 1
            base.at[index, "competitor_price_age_days"] = selected[1]
        base.at[index, "competitor_match_level"] = level
    base["competitor_price"] = base[columns].bfill(axis=1).iloc[:, 0]
    counts = base["competitor_match_level"].value_counts(dropna=False).to_dict()
    diagnostics = {
        "window_days": window_days,
        "exact_coverage_pct": round(float(base[columns[0]].notna().mean() * 100), 6),
        "region_fallback_coverage_pct": round(float(base[columns[1]].notna().mean() * 100), 6),
        "product_fallback_coverage_pct": round(float(base[columns[2]].notna().mean() * 100), 6),
        "selected_match_counts": {str(key): int(value) for key, value in counts.items()},
        "generic_region_fallback_selected_count": generic_region_selected,
        "future_observations_used": 0,
        "no_context_rate_pct": round(float((base["competitor_match_level"] == "NONE").mean() * 100), 6),
    }
    return base, diagnostics


def _attach_behavior(base: pd.DataFrame, tables: dict[str, pd.DataFrame], windows: list[int]) -> tuple[pd.DataFrame, dict[str, Any]]:
    browsing = tables["Browsing_Events"].rename(columns={"EventTime": "EventTime"})
    cart = tables["Cart_Events"].loc[tables["Cart_Events"]["Action"].eq("Add")].copy()
    search = tables["Search_Events"].rename(columns={"ClickedProductID": "ProductID"}).dropna(subset=["ProductID"])
    _datetime(browsing, ["EventTime"]); _datetime(cart, ["EventTime"]); _datetime(search, ["EventTime"])
    event_specs = [
        (browsing, "product_views", "EventID", ["CustomerID", "ProductID"]),
        (cart, "cart_additions", "CartEventID", ["CustomerID", "ProductID"]),
        (search, "search_clicks", "SearchID", ["CustomerID", "ProductID"]),
    ]
    diagnostics: dict[str, Any] = {"future_events_used": 0, "validated_cart_actions": ["Add"]}
    for events, prefix, event_id, keys in event_specs:
        values = _window_aggregate(base, events.assign(_value=1), keys, "EventTime", "_value", prefix, windows, unit="hours")
        base = pd.concat([base, values], axis=1)
        diagnostics[prefix] = {f"{window}h": int((base[f"{prefix}_{window}h"] > 0).sum()) for window in windows}
    return base, diagnostics


def _attach_calendar_weather_holiday(base: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base["decision_month"] = base["DecisionTime"].dt.month.astype("int8")
    base["decision_quarter"] = base["DecisionTime"].dt.quarter.astype("int8")
    base["decision_day_of_week"] = base["DecisionTime"].dt.dayofweek.astype("int8")
    base["decision_is_weekend"] = base["decision_day_of_week"].isin([5, 6]).astype("int8")
    weather = tables["Weather"].copy()
    weather["Date"] = pd.to_datetime(weather["Date"], errors="coerce").dt.normalize()
    _numeric(weather, ["TemperatureF", "PrecipitationIn"])
    weather = weather.rename(columns={"TemperatureF": "weather_temperature", "Condition": "weather_condition", "PrecipitationIn": "weather_precipitation"})
    base = base.merge(
        weather[["RegionID", "Date", "weather_temperature", "weather_condition", "weather_precipitation"]].drop_duplicates(["RegionID", "Date"]),
        left_on=["RegionID", base["DecisionTime"].dt.normalize()], right_on=["RegionID", "Date"], how="left", validate="many_to_one",
    ).drop(columns=["key_1", "Date"], errors="ignore")
    holiday = tables["Holiday"].copy()
    holiday["Date"] = pd.to_datetime(holiday["Date"], errors="coerce").dt.normalize()
    _numeric(holiday, ["SalesImpactFactor"])
    decision_dates = base[["PricingDecisionID", "RegionID"]].copy()
    decision_dates["Date"] = base["DecisionTime"].dt.normalize().to_numpy()
    candidates = decision_dates.merge(holiday, on="Date", how="left")
    candidates = candidates.loc[candidates["RegionID_y"].isna() | candidates["RegionID_y"].eq(candidates["RegionID_x"])]
    holiday_agg = candidates.groupby("PricingDecisionID", as_index=False).agg(
        is_holiday=("HolidayID", lambda values: int(values.notna().any())),
        holiday_sales_impact_factor=("SalesImpactFactor", "max"), holiday_count=("HolidayID", "nunique"),
    )
    base = base.merge(holiday_agg, on="PricingDecisionID", how="left", validate="one_to_one")
    base["is_holiday"] = base["is_holiday"].fillna(0).astype("int8")
    base["holiday_count"] = base["holiday_count"].fillna(0).astype("int16")
    return base


def build_feature_dataset_from_tables(
    tables: dict[str, pd.DataFrame],
    eligible_sales_order_statuses: list[str],
    sales_windows_days: list[int],
    behavior_windows_hours: list[int],
    competitor_window_days: int,
) -> FeatureBuildResult:
    base = _prepare_base(tables)
    base, price_history_diag = _attach_price_history(base, tables)
    base, promotion_diag = _attach_promotions(base, tables)
    base, sales_diag = _attach_sales(base, tables, eligible_sales_order_statuses, sales_windows_days)
    base, competitor_diag = _attach_competitor(base, tables, competitor_window_days)
    base, behavior_diag = _attach_behavior(base, tables, behavior_windows_hours)
    base = _attach_calendar_weather_holiday(base, tables)
    price_features = build_price_dependent_features(
        base["AppliedPrice"], base["CurrentPrice"], base["BasePrice"], base["competitor_price"]
    )
    base = pd.concat([base, price_features.set_index(base.index)], axis=1)
    base = base.drop(columns=["_scope_priority"], errors="ignore")
    base = base.sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)
    base["PurchasedFlag"] = base["PurchasedFlag"].astype("int8")
    base["QuantityPurchased"] = base["QuantityPurchased"].astype("int64")
    diagnostics = {
        "row_count": int(len(base)),
        "unique_pricing_decision_ids": int(base["PricingDecisionID"].nunique()),
        "duplicate_pricing_decision_ids": int(base["PricingDecisionID"].duplicated().sum()),
        "purchase_count": int(base["PurchasedFlag"].sum()),
        "non_purchase_count": int((base["PurchasedFlag"] == 0).sum()),
        "quantity_population_rows": int((base["PurchasedFlag"] == 1).sum()),
        "target_null_count": int(base[["PurchasedFlag", "QuantityPurchased"]].isna().sum().sum()),
        "price_history": price_history_diag,
        "promotion": promotion_diag,
        "sales": sales_diag,
        "competitor": competitor_diag,
        "behavior": behavior_diag,
    }
    source_statuses = {"sales_order_status": sales_diag.get("observed_statuses", []), "cart_action": behavior_diag.get("validated_cart_actions", [])}
    return FeatureBuildResult(base, diagnostics, source_statuses)


def build_feature_dataset(
    db: ReadOnlyConnection,
    schema: str,
    eligible_sales_order_statuses: list[str],
    sales_windows_days: list[int],
    behavior_windows_hours: list[int],
    competitor_window_days: int,
) -> FeatureBuildResult:
    return build_feature_dataset_from_tables(
        fetch_source_tables(db, schema), eligible_sales_order_statuses, sales_windows_days,
        behavior_windows_hours, competitor_window_days,
    )
