"""Deterministic effective-rule resolver."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from .rule_semantics import PRECEDENCE_POLICIES, SCOPE_COLUMNS, is_null, rule_specificity


def resolve_pricing_rule(
    context: Mapping[str, Any],
    rules: pd.DataFrame,
    *,
    as_of: Any | None = None,
    category_id: Any | None = None,
    policy: str = "P1_PRIORITY_DESC_SPECIFICITY_DESC",
) -> dict[str, Any]:
    """Resolve one rule; NULL scope values are wildcards and IDs break ties."""

    when = context.get("DecisionTime") if as_of is None else as_of
    if when is None or pd.isna(when):
        return {"status": "NO_APPLICABLE_RULE", "PricingRuleID": None, "RuleName": None, "RulePriority": None, "RuleSpecificity": None}
    if policy not in PRECEDENCE_POLICIES:
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
        return {"status": "NO_APPLICABLE_RULE", "PricingRuleID": None, "RuleName": None, "RulePriority": None, "RuleSpecificity": None}
    priority_ascending = PRECEDENCE_POLICIES[policy][0]
    if policy.startswith("P3") or policy.startswith("P4"):
        key = (lambda item: (-int(item["_specificity"]), float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), str(item["PricingRuleID"]))) if priority_ascending else (lambda item: (-int(item["_specificity"]), -float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), str(item["PricingRuleID"])))
    else:
        key = (lambda item: (float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), -int(item["_specificity"]), str(item["PricingRuleID"]))) if priority_ascending else (lambda item: (-float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), -int(item["_specificity"]), str(item["PricingRuleID"])))
    ordered = sorted(candidates, key=key)
    selected = ordered[0]
    return {
        "status": "RESOLVED",
        "PricingRuleID": selected.get("PricingRuleID"),
        "RuleName": selected.get("RuleName"),
        "RulePriority": selected.get("Priority"),
        "RuleSpecificity": int(selected.get("_specificity", rule_specificity(selected))),
        "eligible_rule_count": int(len(ordered)),
        "candidate_rule_ids": [str(value["PricingRuleID"]) for value in ordered],
        "rule": selected,
    }


__all__ = ["resolve_pricing_rule"]
