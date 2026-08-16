from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from baselines.purchase import make_purchase_pipeline, purchase_feature_sets
from baselines.quantity import make_quantity_pipeline, purchased_population
from features.feature_contract import load_contract, model_feature_columns
from validation.preprocessing import make_preprocessor, validate_feature_names


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def contract():
    return load_contract(ROOT / "contracts/phase2_feature_contract_v1.yaml")


def test_core_features_are_contract_driven_and_conditionals_are_opt_in(contract):
    purchase = model_feature_columns(contract, population="purchase")
    quantity = model_feature_columns(contract, population="quantity")
    assert purchase == quantity
    assert "ProductID" not in purchase
    assert "StoreID" not in purchase
    assert not any(name.startswith("competitor_") for name in purchase)
    assert not any(name.startswith("product_views_") for name in purchase)
    assert "FavoriteCategoryID" not in purchase
    assert "FavoriteBrandID" not in purchase
    assert "PurchasedFlag" not in quantity
    assert "QuantityPurchased" not in quantity
    assert purchase_feature_sets(contract)["core"] == purchase


def test_forbidden_targets_identifiers_and_optimizer_fields_are_rejected(contract):
    for forbidden in ["PurchasedFlag", "QuantityPurchased", "PricingDecisionID", "CustomerID", "RecommendedPrice", "Inventory.OnHandQty", "Pricing_Rules.RuleID", "Email"]:
        with pytest.raises(ValueError):
            validate_feature_names([forbidden], contract)


def test_preprocessing_fits_only_on_training_and_handles_unseen_future_category(contract):
    features = ["CurrentPrice", "Channel"]
    preprocessor, _, _ = make_preprocessor(contract, features)
    train = pd.DataFrame({"CurrentPrice": [10.0, 20.0, np.nan, 40.0], "Channel": ["Web", "Web", "Store", "Store"]})
    future = pd.DataFrame({"CurrentPrice": [30.0, np.nan], "Channel": ["FutureOnly", "Web"]})
    transformed_train = preprocessor.fit_transform(train)
    transformed_future = preprocessor.transform(future)
    assert transformed_train.shape[0] == len(train)
    assert transformed_future.shape[0] == len(future)
    categories = preprocessor.named_transformers_["categorical"].named_steps["one_hot"].categories_[0]
    assert "FutureOnly" not in categories
    pipeline = LogisticRegression(max_iter=100).fit(transformed_train, [0, 1, 0, 1])
    assert pipeline.predict_proba(transformed_future).shape == (2, 2)


def test_quantity_population_filter_excludes_non_purchases_and_flag_is_not_a_feature(contract):
    frame = pd.DataFrame({"PurchasedFlag": [0, 1, 1], "QuantityPurchased": [0, 2, 1]})
    population = purchased_population(frame)
    assert population["PurchasedFlag"].tolist() == [1, 1]
    pipeline, features = make_quantity_pipeline(contract, "quantity_dummy_mean")
    assert "PurchasedFlag" not in features
    assert "QuantityPurchased" not in features
