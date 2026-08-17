"""Auditable rule scope, date, percentage, and precedence semantics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


SCOPE_COLUMNS = ("ProductID", "CategoryID", "StoreID", "Channel")
PRECEDENCE_POLICIES = {
    "P1_PRIORITY_DESC_SPECIFICITY_DESC": (False, False),
    "P2_PRIORITY_ASC_SPECIFICITY_DESC": (True, False),
    "P3_SPECIFICITY_DESC_PRIORITY_DESC": (False, True),
    "P4_SPECIFICITY_DESC_PRIORITY_ASC": (True, True),
}


def is_null(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def rule_specificity(rule: Mapping[str, Any]) -> int:
    """Count populated scope keys; NULL is the documented wildcard."""

    return int(sum(not is_null(rule.get(column)) for column in SCOPE_COLUMNS))


def scope_matches(rule: Mapping[str, Any], context: Mapping[str, Any], *, category_id: Any | None = None) -> bool:
    for column in SCOPE_COLUMNS:
        required = rule.get(column)
        if is_null(required):
            continue
        actual = category_id if column == "CategoryID" and category_id is not None else context.get(column)
        if is_null(actual) or str(required) != str(actual):
            return False
    return True


def effective_date_matches(rule: Mapping[str, Any], as_of: Any) -> bool:
    timestamp = pd.Timestamp(as_of)
    start = rule.get("EffectiveFrom")
    end = rule.get("EffectiveTo")
    if is_null(start):
        return False
    start_ts = pd.Timestamp(start)
    end_ts = None if is_null(end) else pd.Timestamp(end)
    return bool(bool(rule.get("ActiveFlag")) and start_ts <= timestamp and (end_ts is None or timestamp < end_ts))


def eligible_rules(rules: pd.DataFrame, context: Mapping[str, Any], *, as_of: Any, category_id: Any | None = None) -> pd.DataFrame:
    if rules.empty:
        return rules.copy()
    mask = [
        effective_date_matches(row, as_of) and scope_matches(row, context, category_id=category_id)
        for row in rules.to_dict("records")
    ]
    result = rules.loc[mask].copy()
    if not result.empty:
        result["_specificity"] = [rule_specificity(row) for row in result.to_dict("records")]
    return result


def sort_eligible_rules(rules: pd.DataFrame, policy: str) -> pd.DataFrame:
    if policy not in PRECEDENCE_POLICIES:
        raise ValueError(f"UNKNOWN_RULE_PRECEDENCE_POLICY: {policy}")
    if rules.empty:
        return rules.copy()
    priority_ascending, specificity_priority_order = PRECEDENCE_POLICIES[policy]
    result = rules.copy()
    if "_specificity" not in result:
        result["_specificity"] = [rule_specificity(row) for row in result.to_dict("records")]
    # P1/P2 order by priority then specificity; P3/P4 reverse the keys.
    if policy.startswith("P1") or policy.startswith("P2"):
        columns = ["Priority", "_specificity", "PricingRuleID"]
        ascending = [priority_ascending, False, True]
    else:
        columns = ["_specificity", "Priority", "PricingRuleID"]
        ascending = [False, priority_ascending, True]
    return result.sort_values(columns, ascending=ascending, kind="mergesort").reset_index(drop=True)


def infer_rule_precedence(
    rules: pd.DataFrame,
    historical: pd.DataFrame,
    *,
    category_column: str = "CategoryID",
    target_column: str = "PricingRuleID",
    decision_time_column: str = "DecisionTime",
    min_reconciliation: float = 0.995,
) -> dict[str, Any]:
    """Score all required precedence hypotheses on TRAIN-only policy history.

    The returned payload explicitly marks ambiguity instead of silently picking a
    policy when the data cannot distinguish priority direction.
    """

    required = {target_column, decision_time_column, *SCOPE_COLUMNS}
    missing = sorted(required.difference(historical.columns))
    if missing:
        raise ValueError(f"RULE_SEMANTICS_HISTORY_MISSING: {missing}")
    observed = historical.loc[historical[target_column].notna()].copy()
    if observed.empty:
        return {
            "status": "BLOCKED",
            "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
            "rows_evaluated": 0,
            "policies": {},
        }
    # Build the applicable rule list once per TRAIN row.  The previous
    # implementation rebuilt DataFrames inside all four hypotheses; this
    # bounded list approach keeps the exact same semantics while making the
    # 35k-row acceptance replay practical.
    rule_records = rules.to_dict("records")

    def _eligible_for_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
        when = pd.Timestamp(row[decision_time_column])
        category = row.get(category_column)
        candidates: list[dict[str, Any]] = []
        for rule in rule_records:
            if not bool(rule.get("ActiveFlag")) or is_null(rule.get("EffectiveFrom")):
                continue
            start = pd.Timestamp(rule["EffectiveFrom"])
            end = None if is_null(rule.get("EffectiveTo")) else pd.Timestamp(rule["EffectiveTo"])
            if not (start <= when and (end is None or when < end)):
                continue
            if any(
                not is_null(rule.get(column))
                and (is_null(category if column == "CategoryID" else row.get(column))
                     or str(rule.get(column)) != str(category if column == "CategoryID" else row.get(column)))
                for column in SCOPE_COLUMNS
            ):
                continue
            candidate = dict(rule)
            candidate["_specificity"] = rule_specificity(rule)
            candidates.append(candidate)
        return candidates

    applicable_by_row: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for row in observed.to_dict("records"):
        applicable_by_row.append((row, _eligible_for_row(row)))
    # Null-rule reconciliation is kept separate from the policy-ID score but
    # uses exactly the same active/date/scope resolver.
    historical_null_rule_rows = int(historical[target_column].isna().sum())
    resolver_null_rule_rows = 0
    false_positive_rule_assignments = 0
    false_negative_rule_assignments = 0
    for row in historical.to_dict("records"):
        has_rule = bool(_eligible_for_row(row))
        historical_rule = row.get(target_column)
        if historical_rule is None or is_null(historical_rule):
            if has_rule:
                false_positive_rule_assignments += 1
            else:
                resolver_null_rule_rows += 1
        elif not has_rule:
            false_negative_rule_assignments += 1
    policy_scores: dict[str, dict[str, Any]] = {}
    for policy in PRECEDENCE_POLICIES:
        matched = 0
        no_rule = 0
        priority_ascending = PRECEDENCE_POLICIES[policy][0]
        specificity_first = policy.startswith("P3") or policy.startswith("P4")
        for row, candidates in applicable_by_row:
            if not candidates:
                no_rule += 1
                continue
            if specificity_first:
                if priority_ascending:
                    ordered = sorted(candidates, key=lambda item: (-int(item["_specificity"]), float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), str(item[target_column])))
                else:
                    ordered = sorted(candidates, key=lambda item: (-int(item["_specificity"]), -float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), str(item[target_column])))
            else:
                ordered = sorted(candidates, key=lambda item: (float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), -int(item["_specificity"]), str(item[target_column])), reverse=not priority_ascending)
                # ``reverse`` would also reverse the deterministic ID tie-break;
                # sort keys explicitly to keep PricingRuleID ascending.
                if priority_ascending:
                    ordered = sorted(candidates, key=lambda item: (float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), -int(item["_specificity"]), str(item[target_column])))
                else:
                    ordered = sorted(candidates, key=lambda item: (-float(item.get("Priority", 0) if not is_null(item.get("Priority")) else 0), -int(item["_specificity"]), str(item[target_column])))
            matched += int(str(ordered[0][target_column]) == str(row[target_column]))
        rate = matched / len(observed)
        policy_scores[policy] = {
            "matched_rows": int(matched),
            "rows_evaluated": int(len(observed)),
            "no_applicable_rule_rows": int(no_rule),
            "reconciliation_rate": float(rate),
        }
    best = max(value["reconciliation_rate"] for value in policy_scores.values())
    winners = [policy for policy, value in policy_scores.items() if np.isclose(value["reconciliation_rate"], best, atol=1e-15, rtol=0.0)]
    status = "PASS" if best >= min_reconciliation and len(winners) == 1 else "BLOCKED"
    return {
        "status": status,
        "blocker": None if status == "PASS" else "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
        "rows_evaluated": int(len(observed)),
        "best_reconciliation_rate": float(best),
        "selected_policy": winners[0] if status == "PASS" else None,
        "unique_best_policy": len(winners) == 1,
        "policies": policy_scores,
        "historical_null_rule_rows": historical_null_rule_rows,
        "resolver_null_rule_rows": int(resolver_null_rule_rows),
        "false_positive_rule_assignments": int(false_positive_rule_assignments),
        "false_negative_rule_assignments": int(false_negative_rule_assignments),
        # Backward-compatible alias retained for consumers of the initial
        # Phase 7 draft artifact.
        "null_historical_rule_rows": historical_null_rule_rows,
    }


def audit_percentage_semantics(
    frame: pd.DataFrame,
    *,
    columns: tuple[str, ...] = ("MinMarginPct", "MaxDiscountPct", "MaxPriceChangePct", "DiscountPct"),
    historical_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit percentage units and freeze a single source convention.

    Values above one prove percentage points.  A frame containing only values in
    [0, 1] is intentionally marked ambiguous unless explicit replay evidence is
    supplied; this prevents an arbitrary 100x interpretation.
    """

    distributions: dict[str, Any] = {}
    conventions: set[str] = set()
    for column in columns:
        if column not in frame:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            distributions[column] = {"count": 0, "min": None, "max": None, "fraction_candidate": False}
            continue
        minimum, maximum = float(values.min()), float(values.max())
        points = bool(maximum > 1.0 + 1e-12)
        distributions[column] = {
            "count": int(len(values)),
            "min": minimum,
            "max": maximum,
            "p01": float(values.quantile(0.01)),
            "p50": float(values.quantile(0.50)),
            "p99": float(values.quantile(0.99)),
            "fraction_candidate": not points,
        }
        conventions.add("PERCENT_POINTS" if points else "FRACTION_CANDIDATE")
    if "PERCENT_POINTS" in conventions and "FRACTION_CANDIDATE" not in conventions:
        selected, status, blocker = "PERCENT_POINTS", "PASS", None
    elif conventions == {"FRACTION_CANDIDATE"} and historical_evidence:
        selected = str(historical_evidence.get("selected_convention", "")) or None
        status, blocker = ("PASS", None) if selected in {"PERCENT_POINTS", "FRACTION"} else ("BLOCKED", "PERCENTAGE_UNIT_SEMANTICS_UNRESOLVED")
    else:
        selected, status, blocker = None, "BLOCKED", "PERCENTAGE_UNIT_SEMANTICS_UNRESOLVED"
    return {"status": status, "blocker": blocker, "selected_convention": selected, "distributions": distributions}


def normalize_percentage(value: Any, convention: str) -> float | None:
    if is_null(value):
        return None
    number = float(value)
    if not np.isfinite(number):
        raise ValueError("PERCENTAGE_VALUE_NOT_FINITE")
    if convention == "PERCENT_POINTS":
        return number / 100.0
    if convention == "FRACTION":
        return number
    raise ValueError(f"UNKNOWN_PERCENTAGE_CONVENTION: {convention}")


__all__ = [
    "PRECEDENCE_POLICIES",
    "SCOPE_COLUMNS",
    "audit_percentage_semantics",
    "effective_date_matches",
    "eligible_rules",
    "infer_rule_precedence",
    "normalize_percentage",
    "rule_specificity",
    "scope_matches",
    "sort_eligible_rules",
]
