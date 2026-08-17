"""Date-exact category promotion resolver with explicit overlap conflicts."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import numpy as np
import pandas as pd


CENT = Decimal("0.01")


def _fraction(value: Any, convention: str = "PERCENT_POINTS") -> float:
    number = float(value)
    if convention == "PERCENT_POINTS":
        return number / 100.0
    if convention == "FRACTION":
        return number
    raise ValueError(f"UNKNOWN_PERCENTAGE_CONVENTION: {convention}")


def round_promotion_price(base_price: Any, discount: Any, *, percentage_convention: str = "PERCENT_POINTS") -> float:
    fraction = _fraction(discount, percentage_convention)
    value = Decimal(str(float(base_price))) * (Decimal("1") - Decimal(str(fraction)))
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def eligible_promotions(promotions: pd.DataFrame, *, category_id: Any, decision_date: Any) -> pd.DataFrame:
    if promotions.empty:
        return promotions.copy()
    day = pd.Timestamp(decision_date).normalize()
    mask = (
        promotions["ActiveFlag"].astype(bool)
        & promotions["CategoryID"].astype(str).eq(str(category_id))
        & (promotions["StartDate"] <= day)
        & (day <= promotions["EndDate"])
    )
    return promotions.loc[mask].sort_values("PromotionID", kind="mergesort").reset_index(drop=True)


def audit_promotion_semantics(
    promotions: pd.DataFrame,
    historical: pd.DataFrame,
    *,
    category_column: str = "CategoryID",
    season_column: str = "Season",
    base_column: str = "BasePrice",
    price_evidence_columns: tuple[str, ...] = ("active_history_selling_price", "CurrentPrice", "SellingPrice"),
    percentage_convention: str = "PERCENT_POINTS",
) -> dict[str, Any]:
    """Audit season metadata, overlap rates, and defined-discount price agreement."""

    overlap_counts: list[int] = []
    price_matches: list[bool] = []
    season_matches: list[bool] = []
    for row in historical.to_dict("records"):
        date = row.get("DecisionTime", row.get("DecisionDate"))
        if date is None or category_column not in row:
            continue
        candidates = eligible_promotions(promotions, category_id=row.get(category_column), decision_date=date)
        overlap_counts.append(int(len(candidates)))
        product_season = row.get(season_column)
        for promo in candidates.to_dict("records"):
            season = promo.get("Season")
            if product_season is not None and season is not None:
                season_matches.append(str(season).casefold() in {str(product_season).casefold(), "all", "year-round", "year round"})
        if len(candidates) == 1 and base_column in row:
            expected = round_promotion_price(row[base_column], candidates.iloc[0]["DiscountPct"], percentage_convention=percentage_convention)
            evidence = next((row.get(column) for column in price_evidence_columns if row.get(column) is not None and not pd.isna(row.get(column))), None)
            if evidence is not None:
                price_matches.append(abs(float(evidence) - expected) <= 0.005 + 1e-12)
    counts = pd.Series(overlap_counts, dtype="int64")
    conflict_rows = int(sum(value > 1 for value in overlap_counts))
    conflict_rate = float(conflict_rows / len(overlap_counts)) if overlap_counts else 0.0
    agreement = float(np.mean(price_matches)) if price_matches else None
    mode = "ENFORCE_DEFINED_DISCOUNT" if agreement is not None and agreement >= 0.99 else "CONTEXT_ONLY"
    return {
        "status": "PASS",
        "rows_evaluated": int(len(overlap_counts)),
        "zero_active_rate": float((counts == 0).mean()) if len(counts) else None,
        "one_active_rate": float((counts == 1).mean()) if len(counts) else None,
        "overlap_rate": float((counts > 1).mean()) if len(counts) else 0.0,
        "conflict_rate": conflict_rate,
        "overlap_count_distribution": {str(int(k)): int(v) for k, v in counts.value_counts().sort_index().items()},
        "season_match_rate": float(np.mean(season_matches)) if season_matches else None,
        "season_semantics": "AUDIT_ONLY_DESCRIPTIVE" if not season_matches or float(np.mean(season_matches)) < 0.99 else "EXACT_OR_ALL_MATCH",
        "defined_price_exact_cent_agreement": agreement,
        "promotion_pricing_mode": mode,
    }


def resolve_promotion(
    *,
    promotions: pd.DataFrame,
    category_id: Any,
    decision_date: Any,
    base_price: Any,
    percentage_convention: str = "PERCENT_POINTS",
    pricing_mode: str = "CONTEXT_ONLY",
) -> dict[str, Any]:
    """Resolve a promotion without inventing priority or choosing a larger discount."""

    candidates = eligible_promotions(promotions, category_id=category_id, decision_date=decision_date)
    if candidates.empty:
        return {
            "PromotionAction": "NO_ACTIVE_PROMOTION",
            "RecommendedPromotionID": None,
            "RecommendedPromotionName": None,
            "RecommendedPromotionDiscountPct": None,
            "promotion_pricing_mode": pricing_mode,
            "promotion_price": None,
            "promotion_conflict_flag": False,
            "promotion_equivalent_overlap": False,
            "promotion_rule_conflict_flag": False,
        }
    discounts = candidates["DiscountPct"].astype(float).round(12)
    equivalent = len(set(discounts.tolist())) == 1
    selected = candidates.iloc[0]
    if len(candidates) > 1 and not equivalent:
        action = "PROMOTION_CONFLICT_REVIEW"
        selected_id = None
    else:
        action = "HONOR_ACTIVE_PROMOTION" if pricing_mode == "ENFORCE_DEFINED_DISCOUNT" else "ACTIVE_PROMOTION_CONTEXT_ONLY"
        selected_id = selected["PromotionID"]
    price = None if selected_id is None else round_promotion_price(base_price, selected["DiscountPct"], percentage_convention=percentage_convention)
    return {
        "PromotionAction": action,
        "RecommendedPromotionID": selected_id,
        "RecommendedPromotionName": None if selected_id is None else selected["PromotionName"],
        "RecommendedPromotionDiscountPct": None if selected_id is None else float(selected["DiscountPct"]),
        "promotion_pricing_mode": pricing_mode,
        "promotion_price": price,
        "promotion_conflict_flag": bool(len(candidates) > 1 and not equivalent),
        "promotion_equivalent_overlap": bool(len(candidates) > 1 and equivalent),
        "promotion_rule_conflict_flag": False,
        "active_promotion_count": int(len(candidates)),
        "active_promotion_ids": [str(value) for value in candidates["PromotionID"].tolist()],
    }


__all__ = [
    "audit_promotion_semantics",
    "eligible_promotions",
    "resolve_promotion",
    "round_promotion_price",
]
