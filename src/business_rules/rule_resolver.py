"""Deterministic effective-rule resolver."""

from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

import pandas as pd

from .rule_semantics import CONSTRAINT_ADJUSTMENT_POLICY, PRECEDENCE_POLICIES, SCOPE_COLUMNS, is_null, rule_specificity, select_rule_record


def resolve_pricing_rule(
    context: Mapping[str, Any],
    rules: pd.DataFrame,
    *,
    as_of: Any | None = None,
    category_id: Any | None = None,
    policy: str = "P1_PRIORITY_DESC_SPECIFICITY_DESC",
    reference_price: Any | None = None,
    percentage_convention: str = "PERCENT_POINTS",
) -> dict[str, Any]:
    """Resolve one rule; NULL scope values are wildcards and IDs break ties."""

    when = context.get("DecisionTime") if as_of is None else as_of
    if when is None or pd.isna(when):
        return {"status": "NO_APPLICABLE_RULE", "PricingRuleID": None, "RuleName": None, "RulePriority": None, "RuleSpecificity": None}
    if policy not in PRECEDENCE_POLICIES and policy != CONSTRAINT_ADJUSTMENT_POLICY:
        raise ValueError(f"UNKNOWN_RULE_PRECEDENCE_POLICY: {policy}")
    # Resolve against a cached list of scalar records.  Constructing a pandas
    # DataFrame for every one of the 5k decision contexts dominates acceptance
    # runtime and does not add semantics.
    records = rules.attrs.get("_phase7_rule_records")
    if records is None:
        records = rules.to_dict("records")
        rules.attrs["_phase7_rule_records"] = records
    actual_category = category_id if category_id is not None else context.get("CategoryID")
    timestamp = pd.Timestamp(when)
    reference_key = None if reference_price is None or pd.isna(reference_price) else round(float(reference_price), 2)
    cache = rules.attrs.setdefault("_phase7_resolution_cache", {})
    cache_key = (
        policy,
        str(timestamp),
        str(context.get("ProductID")),
        str(actual_category),
        str(context.get("StoreID")),
        str(context.get("Channel")),
        reference_key,
        percentage_convention,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)
    candidates: list[dict[str, Any]] = []
    for candidate in records:
        if not bool(candidate.get("ActiveFlag")) or is_null(candidate.get("EffectiveFrom")):
            continue
        start = pd.Timestamp(candidate["EffectiveFrom"])
        end = None if is_null(candidate.get("EffectiveTo")) else pd.Timestamp(candidate["EffectiveTo"])
        if not (start <= timestamp and (end is None or timestamp < end)):
            continue
        matched = True
        for column in SCOPE_COLUMNS:
            required = candidate.get(column)
            if is_null(required):
                continue
            actual = actual_category if column == "CategoryID" else context.get(column)
            if is_null(actual) or str(required) != str(actual):
                matched = False
                break
        if matched:
            item = dict(candidate)
            item["_specificity"] = rule_specificity(candidate)
            candidates.append(item)
    if not candidates:
        result = {"status": "NO_APPLICABLE_RULE", "PricingRuleID": None, "RuleName": None, "RulePriority": None, "RuleSpecificity": None}
        cache[cache_key] = result
        return copy.deepcopy(result)
    selected = select_rule_record(
        context,
        candidates,
        policy,
        reference_price=reference_price,
        percentage_convention=percentage_convention,
    )
    if selected is None:
        result = {"status": "NO_APPLICABLE_RULE", "PricingRuleID": None, "RuleName": None, "RulePriority": None, "RuleSpecificity": None}
        cache[cache_key] = result
        return copy.deepcopy(result)
    ordered = candidates
    result = {
        "status": "RESOLVED",
        "PricingRuleID": selected.get("PricingRuleID"),
        "RuleName": selected.get("RuleName"),
        "RulePriority": selected.get("Priority"),
        "RuleSpecificity": int(selected.get("_specificity", rule_specificity(selected))),
        "eligible_rule_count": int(len(ordered)),
        "candidate_rule_ids": [str(value["PricingRuleID"]) for value in ordered],
        "rule": selected,
    }
    cache[cache_key] = copy.deepcopy(result)
    return copy.deepcopy(result)


__all__ = ["resolve_pricing_rule"]
