from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd
from catboost import Pool

from features.feature_contract import model_feature_columns, validate_model_feature_columns
from features.price_features import PRICE_DEPENDENT_FEATURES, build_price_dependent_features


MISSING_CATEGORY = "__MISSING__"

# These are the only conditional families that Phase 4 may add.  The names are
# deliberately explicit; a feature cannot become eligible merely because it
# happens to be present in the parquet file.
CONDITIONAL_GROUP_NAMES = {
    "HIGH_CARDINALITY_CONTEXT": frozenset({"ProductID", "StoreID"}),
    "COMPETITOR_CONTEXT": frozenset({
        "competitor_price_exact_channel",
        "competitor_price_region_fallback",
        "competitor_price_product_fallback",
        "competitor_price",
        "competitor_price_available",
        "competitor_price_age_days",
        "competitor_match_level",
        "price_vs_competitor_pct",
    }),
    "BEHAVIOR_CONTEXT": frozenset({
        "product_views_1h", "product_views_24h", "product_views_168h", "product_views_720h",
        "cart_additions_1h", "cart_additions_24h", "cart_additions_168h", "cart_additions_720h",
        "search_clicks_1h", "search_clicks_24h", "search_clicks_168h", "search_clicks_720h",
    }),
    "CUSTOMER_CONTEXT": frozenset({
        "CustomerSegment", "LoyaltyTier", "PreferredChannel", "PriceSensitivity",
        "CategoryAffinityScore", "BrandAffinityScore",
    }),
}


@dataclass(frozen=True)
class FeatureFamily:
    name: str
    groups: tuple[str, ...]
    feature_names: tuple[str, ...]

    @property
    def conditional(self) -> bool:
        return bool(self.groups)

    @property
    def customer_context(self) -> bool:
        return "CUSTOMER_CONTEXT" in self.groups


def approved_conditional_groups(contract: dict[str, Any]) -> dict[str, list[str]]:
    """Return explicit, contract-backed Phase 4 conditional feature groups."""
    conditional = set(contract["feature_lists"].get("purchase_conditional_features", []))
    entries = {item["name"]: item for item in contract["features"]}
    groups: dict[str, list[str]] = {}
    for group_name, names in CONDITIONAL_GROUP_NAMES.items():
        missing = sorted(set(names) - conditional)
        if missing:
            raise ValueError(f"{group_name} contains features not approved by the contract: {missing}")
        invalid = [name for name in names if not entries[name].get("model_eligible", False)]
        if invalid:
            raise ValueError(f"{group_name} contains non-model-eligible features: {invalid}")
        # Canonical contract order is retained for deterministic Pool schemas.
        groups[group_name] = [name for name in contract["feature_lists"]["purchase_conditional_features"] if name in names]
    return groups


def build_feature_families(contract: dict[str, Any]) -> dict[str, FeatureFamily]:
    core = model_feature_columns(contract, population="purchase", include_conditional=False)
    groups = approved_conditional_groups(contract)
    conditional_order = list(contract["feature_lists"].get("purchase_conditional_features", []))

    def family(name: str, selected_groups: Iterable[str]) -> FeatureFamily:
        selected = set(selected_groups)
        selected_names = {
            feature for group_name in selected for feature in groups[group_name]
        }
        ordered = tuple(core + [name for name in conditional_order if name in selected_names])
        validate_model_feature_columns(ordered, contract)
        return FeatureFamily(name=name, groups=tuple(sorted(selected)), feature_names=ordered)

    return {
        "F0_CORE": family("F0_CORE", []),
        "F1_CORE_HIGH_CARDINALITY": family("F1_CORE_HIGH_CARDINALITY", ["HIGH_CARDINALITY_CONTEXT"]),
        "F2_CORE_COMPETITOR": family("F2_CORE_COMPETITOR", ["COMPETITOR_CONTEXT"]),
        "F3_CORE_BEHAVIOR": family("F3_CORE_BEHAVIOR", ["BEHAVIOR_CONTEXT"]),
        "F4_CORE_CUSTOMER": family("F4_CORE_CUSTOMER", ["CUSTOMER_CONTEXT"]),
        "F5_CORE_HIGH_CARDINALITY_COMPETITOR": family("F5_CORE_HIGH_CARDINALITY_COMPETITOR", ["HIGH_CARDINALITY_CONTEXT", "COMPETITOR_CONTEXT"]),
        "F6_CORE_HIGH_CARDINALITY_BEHAVIOR": family("F6_CORE_HIGH_CARDINALITY_BEHAVIOR", ["HIGH_CARDINALITY_CONTEXT", "BEHAVIOR_CONTEXT"]),
        "F7_CORE_HIGH_CARDINALITY_COMPETITOR_BEHAVIOR": family("F7_CORE_HIGH_CARDINALITY_COMPETITOR_BEHAVIOR", ["HIGH_CARDINALITY_CONTEXT", "COMPETITOR_CONTEXT", "BEHAVIOR_CONTEXT"]),
        "F8_CORE_ALL_APPROVED_CONTEXT": family("F8_CORE_ALL_APPROVED_CONTEXT", list(groups)),
    }


def categorical_feature_names(contract: dict[str, Any], feature_names: Iterable[str]) -> list[str]:
    allowed = set(contract["feature_lists"].get("categorical_features", []))
    return [name for name in feature_names if name in allowed]


def prepare_catboost_frame(
    frame: pd.DataFrame,
    contract: dict[str, Any],
    feature_names: Iterable[str],
) -> pd.DataFrame:
    """Prepare a named CatBoost frame without one-hot or target encoding."""
    names = list(feature_names)
    validate_model_feature_columns(names, contract)
    missing = sorted(set(names) - set(frame.columns))
    if missing:
        raise ValueError(f"CatBoost input is missing approved columns: {missing}")
    categorical = set(categorical_feature_names(contract, names))
    result = frame.loc[:, names].copy()
    for name in names:
        if name in categorical:
            # CatBoost does not accept null category values.  The sentinel is
            # stable across train, validation, candidate-price, and TEST paths.
            result[name] = result[name].astype("string").fillna(MISSING_CATEGORY).astype(str)
        else:
            # Numeric NaNs remain NaNs; CatBoost handles them natively.
            result[name] = pd.to_numeric(result[name], errors="coerce")
    return result


def make_catboost_pool(
    frame: pd.DataFrame,
    contract: dict[str, Any],
    feature_names: Iterable[str],
    labels: Iterable[Any] | None = None,
) -> Pool:
    names = list(feature_names)
    prepared = prepare_catboost_frame(frame, contract, names)
    label_array = None if labels is None else np.asarray(list(labels))
    return Pool(
        data=prepared,
        label=label_array,
        feature_names=names,
        cat_features=categorical_feature_names(contract, names),
    )


def build_purchase_model_features_for_candidate_price(
    frame: pd.DataFrame,
    candidate_price: Any,
    contract: dict[str, Any],
    feature_names: Iterable[str],
) -> pd.DataFrame:
    """Rebuild only candidate-dependent features using the Phase 2 formulas."""
    result = frame.copy()
    if np.isscalar(candidate_price) or candidate_price is None:
        prices = np.full(len(result), candidate_price, dtype=float)
    else:
        prices = np.asarray(candidate_price, dtype=float)
        if len(prices) != len(result):
            raise ValueError("candidate_price length must match frame rows")
    result["AppliedPrice"] = prices
    competitor = result["competitor_price"] if "competitor_price" in result else None
    rebuilt = build_price_dependent_features(
        result["AppliedPrice"], result["CurrentPrice"], result["BasePrice"], competitor
    )
    for name in PRICE_DEPENDENT_FEATURES + ["current_vs_base_pct"]:
        result[name] = rebuilt[name].to_numpy()
    return prepare_catboost_frame(result, contract, feature_names)


def validate_feature_schema(
    train_frame: pd.DataFrame,
    prediction_frame: pd.DataFrame,
    feature_names: Iterable[str],
) -> None:
    names = list(feature_names)
    if list(train_frame.columns) != names or list(prediction_frame.columns) != names:
        raise ValueError("CatBoost train/predict feature ordering mismatch")
    if train_frame.dtypes.tolist() != prediction_frame.dtypes.tolist():
        raise ValueError("CatBoost train/predict feature dtypes mismatch")

