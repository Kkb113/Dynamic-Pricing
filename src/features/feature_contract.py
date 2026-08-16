from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml


ROLES = {
    "ROW_IDENTIFIER",
    "AUDIT_ONLY",
    "TARGET",
    "CORE_MODEL_FEATURE",
    "CONDITIONAL_MODEL_FEATURE",
    "OPTIONAL_MODEL_FEATURE",
    "OPTIMIZATION_ONLY",
    "JOIN_ONLY",
    "PROHIBITED",
}
FORBIDDEN_MODEL_COLUMNS = {
    "RecommendedPrice", "ExpectedDemand", "PurchaseProbability", "PriceElasticity",
    "ExpectedRevenue", "ExpectedMarginPct", "ModelVersion", "ReasonCode", "ActualRevenue",
    "OutcomeTime", "OrderLineID", "PurchasedFlag", "QuantityPurchased", "CustomerID",
    "SessionID", "PricingDecisionID", "CostPrice", "MarginPct", "Inventory",
    "FirstName", "LastName", "Email", "BirthDate", "Gender", "ReviewText",
}
FORBIDDEN_PREFIXES = ("Pricing_Rules.", "Inventory.")


def load_contract(path: Path) -> dict[str, Any]:
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or not isinstance(contract.get("features"), list):
        raise ValueError("Phase 2 feature contract must contain a features list")
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    features = contract.get("features", [])
    names: set[str] = set()
    for feature in features:
        required = {
            "name", "role", "feature_group", "source_tables", "dtype", "formula_or_semantics",
            "point_in_time_rule", "window", "price_dependent", "conditional", "model_eligible",
            "null_semantics", "fallback_policy",
        }
        missing = required - set(feature)
        if missing:
            raise ValueError(f"Feature {feature.get('name')} is missing {sorted(missing)}")
        name = feature["name"]
        if name in names:
            raise ValueError(f"Duplicate feature contract entry: {name}")
        names.add(name)
        if feature["role"] not in ROLES:
            raise ValueError(f"Unknown role for {name}: {feature['role']}")
        if bool(feature["model_eligible"]) != (feature["role"] in {
            "CORE_MODEL_FEATURE", "CONDITIONAL_MODEL_FEATURE", "OPTIONAL_MODEL_FEATURE"
        }):
            raise ValueError(f"Model eligibility and role disagree for {name}")
        if not isinstance(feature["price_dependent"], bool) or not isinstance(feature["conditional"], bool):
            raise ValueError(f"Boolean contract fields are invalid for {name}")
    lists = contract.get("feature_lists", {})
    model = set(lists.get("purchase_core_features", [])) | set(lists.get("purchase_conditional_features", []))
    model |= set(lists.get("quantity_core_features", [])) | set(lists.get("quantity_conditional_features", []))
    unknown = model - names
    if unknown:
        raise ValueError(f"Feature lists contain unknown features: {sorted(unknown)}")
    for name in model:
        if name in FORBIDDEN_MODEL_COLUMNS or any(name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            raise ValueError(f"Forbidden model feature admitted: {name}")
        entry = next(item for item in features if item["name"] == name)
        if not entry["model_eligible"]:
            raise ValueError(f"Non-eligible feature admitted: {name}")


def model_feature_columns(contract: dict[str, Any], population: str = "purchase") -> list[str]:
    lists = contract["feature_lists"]
    if population == "quantity":
        names = list(lists["quantity_core_features"]) + list(lists["quantity_conditional_features"])
    else:
        names = list(lists["purchase_core_features"]) + list(lists["purchase_conditional_features"])
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate model feature names for {population}")
    validate_model_feature_columns(names, contract)
    return names


def validate_model_feature_columns(columns: Iterable[str], contract: dict[str, Any]) -> None:
    allowed = {feature["name"] for feature in contract["features"] if feature["model_eligible"]}
    columns = list(columns)
    unknown = set(columns) - allowed
    if unknown:
        raise ValueError(f"Unknown or unapproved model columns: {sorted(unknown)}")
    forbidden = [
        column for column in columns
        if column in FORBIDDEN_MODEL_COLUMNS or any(column.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
    ]
    if forbidden:
        raise ValueError(f"Forbidden model columns: {sorted(forbidden)}")
