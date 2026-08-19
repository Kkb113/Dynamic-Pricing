"""Historical pricing-rule replay kept separate from model decisioning."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .rule_constraints import derive_rule_bounds, round_price_half_up
from .rule_resolver import resolve_pricing_rule


def replay_historical_rule_id_application(
    historical: pd.DataFrame,
    rules: pd.DataFrame,
    *,
    percentage_convention: str = "PERCENT_POINTS",
) -> pd.DataFrame:
    """Replay the historical ``PricingRuleID`` directly, without resolving.

    This is deliberately separate from :func:`replay_historical_rule_application`.
    It answers the forensic question "does the recorded rule ID plus the
    canonical constraint math reproduce AppliedPrice?" independently of any
    hypothesis about how the source selected that rule.
    """

    required = {
        "PricingDecisionID", "PricingRuleID", "BasePrice", "CurrentPrice",
        "CostPrice", "RecommendedPrice", "AppliedPrice",
    }
    missing = sorted(required.difference(historical.columns))
    if missing:
        raise ValueError(f"HISTORICAL_RULE_ID_REPLAY_COLUMNS_MISSING: {missing}")
    rule_lookup = {
        str(record.get("PricingRuleID")): record
        for record in rules.to_dict("records")
        if record.get("PricingRuleID") is not None
    }
    rows: list[dict[str, Any]] = []
    for source in historical.to_dict("records"):
        historical_id = source.get("PricingRuleID")
        rule = None if pd.isna(historical_id) else rule_lookup.get(str(historical_id))
        if rule is None:
            replayed = np.nan
            conflict = False
            missing_rule = True
        else:
            bounds = derive_rule_bounds(
                rule,
                base_price=source["BasePrice"],
                current_price=source["CurrentPrice"],
                cost_price=source["CostPrice"],
                percentage_convention=percentage_convention,
            )
            conflict = bool(bounds["conflict"])
            missing_rule = False
            replayed = float(source["RecommendedPrice"])
            if conflict:
                replayed = np.nan
            else:
                if bounds["effective_price_floor"] is not None:
                    replayed = max(replayed, float(bounds["effective_price_floor"]))
                if bounds["effective_price_ceiling"] is not None:
                    replayed = min(replayed, float(bounds["effective_price_ceiling"]))
                replayed = round_price_half_up(replayed)
        historical_applied = float(source["AppliedPrice"])
        rows.append({
            "PricingDecisionID": source.get("PricingDecisionID"),
            "PricingRuleID": historical_id,
            "replayed_AppliedPrice": replayed,
            "historical_AppliedPrice": historical_applied,
            "absolute_delta": np.nan if pd.isna(replayed) else abs(float(replayed) - historical_applied),
            "constrained": bool(not np.isclose(float(source["RecommendedPrice"]), historical_applied, atol=0.005, rtol=0.0)),
            "rule_violation_count": int(1 if conflict else 0),
            "historical_rule_missing": bool(missing_rule),
        })
    return pd.DataFrame(rows)


def replay_historical_rule_application(
    historical: pd.DataFrame,
    rules: pd.DataFrame,
    *,
    policy: str = "P1_PRIORITY_DESC_SPECIFICITY_DESC",
    percentage_convention: str = "PERCENT_POINTS",
    category_column: str = "CategoryID",
) -> pd.DataFrame:
    """Replay source ``RecommendedPrice`` into a constrained ``AppliedPrice``.

    This function never reads outcomes and must not be used to create model
    features.  It is intentionally explicit about missing source columns.
    """

    required = {"DecisionTime", "ProductID", "StoreID", "Channel", "BasePrice", "CurrentPrice", "CostPrice", "RecommendedPrice", "AppliedPrice"}
    missing = sorted(required.difference(historical.columns))
    if missing:
        raise ValueError(f"HISTORICAL_RULE_REPLAY_COLUMNS_MISSING: {missing}")
    rows: list[dict[str, Any]] = []
    for source in historical.to_dict("records"):
        resolution = resolve_pricing_rule(
            source,
            rules,
            as_of=source["DecisionTime"],
            category_id=source.get(category_column),
            policy=policy,
            reference_price=source.get("RecommendedPrice"),
            percentage_convention=percentage_convention,
        )
        rule = resolution.get("rule")
        bounds = derive_rule_bounds(rule, base_price=source["BasePrice"], current_price=source["CurrentPrice"], cost_price=source["CostPrice"], percentage_convention=percentage_convention)
        recommended = float(source["RecommendedPrice"])
        replayed = recommended
        if bounds["conflict"]:
            replayed = np.nan
        else:
            if bounds["effective_price_floor"] is not None:
                replayed = max(replayed, float(bounds["effective_price_floor"]))
            if bounds["effective_price_ceiling"] is not None:
                replayed = min(replayed, float(bounds["effective_price_ceiling"]))
            replayed = round_price_half_up(replayed)
        historical_applied = float(source["AppliedPrice"])
        rows.append({
            "PricingDecisionID": source.get("PricingDecisionID"),
            "PricingRuleID": resolution.get("PricingRuleID"),
            "replayed_AppliedPrice": replayed,
            "historical_AppliedPrice": historical_applied,
            "absolute_delta": np.nan if pd.isna(replayed) else abs(float(replayed) - historical_applied),
            "constrained": bool(not np.isclose(recommended, historical_applied, atol=0.005, rtol=0.0)),
            "rule_violation_count": int(1 if bounds["conflict"] else 0),
        })
    return pd.DataFrame(rows)


def replay_metrics(replay: pd.DataFrame) -> dict[str, Any]:
    if replay.empty:
        return {"rows": 0, "exact_cent_match_rate": None, "rule_violation_count": 0}
    delta = pd.to_numeric(replay["absolute_delta"], errors="coerce")
    exact = delta.le(0.005 + 1e-12)
    return {
        "rows": int(len(replay)),
        "exact_cent_match_rate": float(exact.mean()),
        "absolute_delta_mean": float(delta.mean()),
        "absolute_delta_median": float(delta.median()),
        "absolute_delta_p95": float(delta.quantile(0.95)),
        "absolute_delta_max": float(delta.max()),
        "constrained_decision_count": int(replay["constrained"].sum()),
        "constrained_decision_rate": float(replay["constrained"].mean()),
        "rule_violation_count": int(replay["rule_violation_count"].sum()),
        "historical_rule_missing_count": int(replay.get("historical_rule_missing", pd.Series(False, index=replay.index)).astype(bool).sum()),
    }


__all__ = ["replay_historical_rule_application", "replay_historical_rule_id_application", "replay_metrics"]
