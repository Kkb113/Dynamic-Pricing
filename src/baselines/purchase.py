from __future__ import annotations

from typing import Any

from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from features.feature_contract import model_feature_columns
from validation.preprocessing import make_preprocessor


def purchase_feature_sets(contract: dict[str, Any]) -> dict[str, list[str]]:
    core = model_feature_columns(contract, population="purchase")
    price_features = set(contract["feature_lists"].get("price_dependent_features", []))
    no_price = [name for name in core if name not in price_features]
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
