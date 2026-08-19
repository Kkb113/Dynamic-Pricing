"""Controlled exact-cent candidate augmentation with a scoring contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from business_rules.rule_constraints import round_price_half_up


def _support_bounds(group: pd.DataFrame) -> tuple[float, float]:
    low = float(pd.to_numeric(group["support_low"], errors="coerce").iloc[0])
    high = float(pd.to_numeric(group["support_high"], errors="coerce").iloc[0])
    current = float(group["CurrentPrice"].iloc[0])
    return current * low, current * high


def augment_rule_boundary_candidates(
    surface: pd.DataFrame,
    bounds_by_decision: Mapping[Any, Mapping[str, Any]],
    *,
    score_candidate: Callable[[pd.Series, float], Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Add rule-floor/ceiling candidates only when a frozen scorer is supplied.

    A boundary outside the Phase 6 support envelope is retained as a diagnostic
    blocker, never emitted as an unsimulated price.
    """

    if surface.empty or not bounds_by_decision:
        result = surface.copy()
        if "candidate_origin" not in result:
            result["candidate_origin"] = "PHASE6_GRID"
        return result
    base = surface.copy()
    if "candidate_origin" not in base:
        base["candidate_origin"] = "PHASE6_GRID"
    additions: list[dict[str, Any]] = []
    pending_scores: list[tuple[pd.Series, float, str]] = []
    out_of_support: list[dict[str, Any]] = []
    for decision_id, group in base.groupby("PricingDecisionID", sort=False):
        bound = bounds_by_decision.get(decision_id)
        if not bound:
            continue
        support_low, support_high = _support_bounds(group)
        for key, origin in (("effective_price_floor", "RULE_FLOOR"), ("effective_price_ceiling", "RULE_CEILING")):
            value = bound.get(key)
            if value is None or pd.isna(value):
                continue
            price = round_price_half_up(value)
            if price < support_low - 0.005 - 1e-12 or price > support_high + 0.005 + 1e-12:
                out_of_support.append({"PricingDecisionID": decision_id, "boundary": key, "price": price, "support_low": support_low, "support_high": support_high})
                continue
            if np.isclose(pd.to_numeric(group["CandidatePrice"], errors="coerce"), price, atol=0.005, rtol=0).any():
                continue
            if score_candidate is None:
                raise ValueError("RULE_BOUNDARY_REQUIRES_MODEL_SCORING")
            source = group.iloc[0].copy()
            pending_scores.append((source, price, origin))
    if pending_scores:
        if hasattr(score_candidate, "score_candidates"):
            score_inputs = pd.DataFrame([source.to_dict() for source, _, _ in pending_scores])
            scored_values = list(score_candidate.score_candidates(score_inputs, [price for _, price, _ in pending_scores]))
        else:
            scored_values = [dict(score_candidate(source, price)) for source, price, _ in pending_scores]
        for (source, price, origin), scored in zip(pending_scores, scored_values):
            row = source.to_dict()
            row.update(dict(scored))
            row.update({
                "CandidatePrice": price,
                "candidate_origin": origin,
                "candidate_multiplier": price / float(source["CurrentPrice"]),
                "is_current_price_candidate": bool(np.isclose(price, float(source["CurrentPrice"]), atol=0.005, rtol=0)),
                "candidate_vs_current_pct": price / float(source["CurrentPrice"]) - 1.0,
                "candidate_vs_base_pct": price / float(source["BasePrice"]) - 1.0,
            })
            additions.append(row)
    if not additions:
        base.attrs["phase7_augmentation"] = {"added_candidates": 0, "out_of_support_boundaries": out_of_support, "status": "NO_IN_SUPPORT_BOUNDARIES" if not out_of_support else "OUT_OF_SUPPORT_BOUNDARY"}
        return base
    result = pd.concat([base, pd.DataFrame(additions)], ignore_index=True, sort=False)
    result = result.sort_values(["PricingDecisionID", "CandidatePrice", "candidate_origin"], kind="mergesort").drop_duplicates(["PricingDecisionID", "CandidatePrice"], keep="first").reset_index(drop=True)
    result["candidate_rank_by_price"] = result.groupby("PricingDecisionID", sort=False).cumcount()
    result["is_support_lower_boundary"] = result.groupby("PricingDecisionID")["CandidatePrice"].transform("min").eq(result["CandidatePrice"])
    result["is_support_upper_boundary"] = result.groupby("PricingDecisionID")["CandidatePrice"].transform("max").eq(result["CandidatePrice"])
    result.attrs["phase7_augmentation"] = {"added_candidates": int(len(additions)), "out_of_support_boundaries": out_of_support, "status": "PASS" if not out_of_support else "OUT_OF_SUPPORT_BOUNDARY"}
    return result


__all__ = ["augment_rule_boundary_candidates"]
