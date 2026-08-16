from __future__ import annotations

from typing import Any

from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from features.feature_contract import model_feature_columns
from validation.preprocessing import make_preprocessor


# The diagnostic is context-only: remove direct prices, price history, and
# promotion-price proxies.  The explicit names make the policy reviewable;
# contract groups and price-dependent declarations keep it robust to additions.
PRICE_ABLATION_FEATURE_GROUPS = frozenset({"price", "price_history", "promotion"})
PRICE_ABLATION_FEATURES = frozenset({
    "CurrentPrice",
    "AppliedPrice",
    "BasePrice",
    "price_change_amount",
    "price_change_pct",
    "price_vs_base_pct",
    "current_vs_base_pct",
    "discount_from_base_pct",
    "active_history_selling_price",
    "history_discount_pct",
    "days_since_current_price_started",
    "previous_selling_price",
    "previous_price_change_pct",
    "active_promotion_flag",
    "active_promotion_discount_pct",
})


def purchase_feature_sets(contract: dict[str, Any]) -> dict[str, list[str]]:
    core = model_feature_columns(contract, population="purchase")
    contract_group_features = {
        feature["name"]
        for feature in contract["features"]
        if feature.get("feature_group") in PRICE_ABLATION_FEATURE_GROUPS
    }
    price_features = set(contract["feature_lists"].get("price_dependent_features", []))
    excluded = set(PRICE_ABLATION_FEATURES) | contract_group_features | price_features
    no_price = [name for name in core if name not in excluded]
    return {"core": core, "core_no_price": no_price}


def make_purchase_pipeline(contract: dict[str, Any], model_name: str) -> tuple[Pipeline, list[str]]:
    feature_sets = purchase_feature_sets(contract)
    if model_name == "purchase_logistic_core_no_price":
        feature_names = feature_sets["core_no_price"]
    elif model_name in {"purchase_dummy_prior", "purchase_logistic_core"}:
        feature_names = feature_sets["core"]
    else:
        raise ValueError(f"Unknown purchase baseline: {model_name}")
    preprocessor, _, _ = make_preprocessor(contract, feature_names)
    if model_name == "purchase_dummy_prior":
        estimator = DummyClassifier(strategy="prior")
    else:
        estimator = LogisticRegression(
            penalty="l2", C=1.0, solver="lbfgs", max_iter=2000,
            random_state=42, class_weight=None,
        )
    return Pipeline([("preprocess", preprocessor), ("model", estimator)]), feature_names
