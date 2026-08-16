from __future__ import annotations

from typing import Iterable

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from features.feature_contract import FORBIDDEN_MODEL_COLUMNS, validate_model_feature_columns


def _one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # scikit-learn < 1.2 compatibility
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def validate_feature_names(feature_names: Iterable[str], contract: dict) -> list[str]:
    names = list(feature_names)
    validate_model_feature_columns(names, contract)
    forbidden = set(names) & FORBIDDEN_MODEL_COLUMNS
    if forbidden:
        raise ValueError(f"Forbidden leakage fields in model pipeline: {sorted(forbidden)}")
    if any(name.startswith("Pricing_Rules.") or name.startswith("Inventory.") for name in names):
        raise ValueError("Optimizer-only or inventory fields cannot enter a Phase 3 pipeline")
    if {"PurchasedFlag", "QuantityPurchased"} & set(names):
        raise ValueError("Targets cannot enter a Phase 3 model pipeline")
    return names


def make_preprocessor(contract: dict, feature_names: Iterable[str]) -> tuple[ColumnTransformer, list[str], list[str]]:
    names = validate_feature_names(feature_names, contract)
    numeric_allowed = set(contract["feature_lists"].get("numeric_features", []))
    categorical_allowed = set(contract["feature_lists"].get("categorical_features", []))
    numeric = [name for name in names if name in numeric_allowed]
    categorical = [name for name in names if name in categorical_allowed]
    uncovered = set(names) - set(numeric) - set(categorical)
    if uncovered:
        raise ValueError(f"Contract does not classify model features as numeric or categorical: {sorted(uncovered)}")
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="__MISSING__")),
        ("one_hot", _one_hot_encoder()),
    ])
    transformer = ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, numeric),
            ("categorical", categorical_pipeline, categorical),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )
    return transformer, numeric, categorical
