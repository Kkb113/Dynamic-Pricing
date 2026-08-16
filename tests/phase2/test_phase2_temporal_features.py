import pandas as pd

from features.feature_builder import _latest_competitor, _window_aggregate


def _decision_frame():
    return pd.DataFrame({
        "PricingDecisionID": ["d1", "d2"],
        "DecisionTime": pd.to_datetime(["2025-06-10 12:00:00", "2025-06-11 12:00:00"]),
        "ProductID": ["p1", "p1"],
    })


def test_date_only_sales_exclude_same_day_and_future_orders():
    decisions = _decision_frame()
    sales = pd.DataFrame({
        "ProductID": ["p1", "p1", "p1", "p1"],
        "OrderDate": pd.to_datetime(["2025-06-03", "2025-06-10", "2025-06-11", "2025-05-01"]),
        "Qty": [2, 100, 200, 1],
    })
    values = _window_aggregate(decisions, sales, ["ProductID"], "OrderDate", "Qty", "product_sales", [7])
    assert values.loc[0, "product_sales_7d"] == 2
    assert values.loc[1, "product_sales_7d"] == 100  # June 10 is prior to the June 11 decision.


def test_behavior_windows_include_boundary_and_exclude_future():
    decisions = _decision_frame().iloc[[0]].copy()
    events = pd.DataFrame({
        "CustomerID": ["c1", "c1", "c1"], "ProductID": ["p1"] * 3,
        "EventTime": pd.to_datetime(["2025-06-10 11:00:00", "2025-06-10 12:00:00", "2025-06-10 12:00:01"]),
        "value": [1, 1, 1],
    })
    decisions["CustomerID"] = "c1"
    values = _window_aggregate(decisions, events, ["CustomerID", "ProductID"], "EventTime", "value", "events", [1], unit="hours")
    assert values.loc[0, "events_1h"] == 2


def test_competitor_never_selects_future_observation_and_respects_window():
    competitors = pd.DataFrame({
        "CompetitorPriceID": ["old", "future"],
        "ObservedDateTime": pd.to_datetime(["2025-06-09 12:00:00", "2025-06-10 13:00:00"]),
        "CompetitorPrice": [95.0, 80.0],
    })
    assert _latest_competitor(competitors, pd.Timestamp("2025-06-10 12:00:00"), 30)[0] == 95.0
