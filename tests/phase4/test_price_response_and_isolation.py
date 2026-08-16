from __future__ import annotations

import pandas as pd

from models.catboost_data import make_catboost_pool
from models.catboost_purchase import make_catboost_classifier
from models.price_response import candidate_price_predictions, summarize_price_response
from tests.phase4._fixtures import phase4_fixture_frame


def test_price_scenarios_change_only_candidate_dependent_inputs() -> None:
    frame, contract, feature_names = phase4_fixture_frame(160)
    train_pool = make_catboost_pool(frame, contract, feature_names, frame["PurchasedFlag"])
    model = make_catboost_classifier({"learning_rate": .05, "depth": 4, "l2_leaf_reg": 5, "random_strength": 1, "bagging_temperature": 1, "border_count": 64}, thread_count=2, iterations=5, early_stopping_rounds=None, use_best_model=False)
    model.fit(train_pool)
    original_context = frame[["CurrentPrice", "BasePrice", "weather_temperature", "product_sales_30d", "Channel"]].copy()
    rows, matrix = candidate_price_predictions(model, frame, contract, feature_names, multipliers=[0.9, 1.0, 1.1])
    assert rows["multiplier"].nunique() == 3
    assert matrix.shape == (len(frame), 3)
    pd.testing.assert_frame_equal(original_context, frame[["CurrentPrice", "BasePrice", "weather_temperature", "product_sales_30d", "Channel"]])
    summary = summarize_price_response(matrix, [0.9, 1.0, 1.1])
    assert 0.0 <= summary["flat_response_rate"] <= 1.0
    assert 0.0 <= summary["non_monotonic_sequence_rate"] <= 1.0

