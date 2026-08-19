"""Integrity and observed-economics audits for Phase 8 outcomes."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd


def validate_outcome_join(
    outcomes: pd.DataFrame,
    decision_ids: Iterable[Any],
    *,
    expected_rows: int = 5250,
) -> dict[str, Any]:
    ids = {str(value) for value in decision_ids}
    actual = outcomes["PricingDecisionID"].astype(str) if "PricingDecisionID" in outcomes else pd.Series(dtype=str)
    duplicate_ids = int(actual.duplicated().sum())
    missing_ids = int(len(ids.difference(set(actual))))
    unexpected_ids = int(len(set(actual).difference(ids)))
    return {
        "expected_rows": expected_rows,
        "rows": int(len(outcomes)),
        "unique_ids": int(actual.nunique()),
        "duplicate_ids": duplicate_ids,
        "missing_ids": missing_ids,
        "unexpected_ids": unexpected_ids,
        "one_to_one": bool(
            len(outcomes) == expected_rows
            and len(outcomes) == len(ids)
            and duplicate_ids == 0
            and missing_ids == 0
            and unexpected_ids == 0
        ),
    }


def audit_outcome_quality(outcomes: pd.DataFrame) -> dict[str, Any]:
    frame = outcomes.copy()
    purchased = pd.to_numeric(frame.get("PurchasedFlag"), errors="coerce")
    quantity = pd.to_numeric(frame.get("QuantityPurchased"), errors="coerce")
    revenue = pd.to_numeric(frame.get("ActualRevenue"), errors="coerce")
    applied = pd.to_numeric(frame.get("AppliedPrice"), errors="coerce")
    invalid_flag = int((purchased.isna() | ~purchased.isin([0, 1])).sum())
    invalid_quantity = int((quantity.isna() | ~np.isfinite(quantity) | (quantity < 0) | (quantity.round(0) != quantity)).sum())
    invalid_revenue = int((revenue.isna() | ~np.isfinite(revenue) | (revenue < 0)).sum())
    invalid_price = int((applied.isna() | ~np.isfinite(applied) | (applied <= 0)).sum())
    nonpurchase_positive_quantity = int(((purchased == 0) & (quantity != 0)).sum())
    nonpurchase_positive_revenue = int(((purchased == 0) & (revenue != 0)).sum())
    purchase_zero_quantity = int(((purchased == 1) & (quantity < 1)).sum())
    contradictions = {
        "nonpurchase_positive_quantity": nonpurchase_positive_quantity,
        "nonpurchase_positive_revenue": nonpurchase_positive_revenue,
        "purchase_zero_quantity": purchase_zero_quantity,
    }
    return {
        "rows": int(len(frame)),
        "purchased_flag_values": sorted({int(value) for value in purchased.dropna().unique()}),
        "invalid_purchased_flag_rows": invalid_flag,
        "invalid_quantity_rows": invalid_quantity,
        "invalid_revenue_rows": invalid_revenue,
        "invalid_applied_price_rows": invalid_price,
        "contradictions": contradictions,
        "contradictory_rows": int(sum(contradictions.values())),
        "status": "PASS" if not any([invalid_flag, invalid_quantity, invalid_revenue, invalid_price, sum(contradictions.values())]) else "BLOCKED",
    }


def revenue_consistency_audit(outcomes: pd.DataFrame, tolerance: float = 0.01) -> dict[str, Any]:
    frame = outcomes.copy()
    computed = pd.to_numeric(frame["AppliedPrice"], errors="coerce") * pd.to_numeric(frame["QuantityPurchased"], errors="coerce")
    actual = pd.to_numeric(frame["ActualRevenue"], errors="coerce")
    delta = computed - actual
    absolute = delta.abs()
    mismatch = absolute > tolerance
    return {
        "tolerance": tolerance,
        "exact_cent_match_rate": float((~mismatch).mean()) if len(frame) else 1.0,
        "mean_delta": float(delta.mean()) if len(frame) else 0.0,
        "p95_absolute_delta": float(absolute.quantile(0.95)) if len(frame) else 0.0,
        "max_absolute_delta": float(absolute.max()) if len(frame) else 0.0,
        "mismatch_count": int(mismatch.sum()),
        "mismatch_rate": float(mismatch.mean()) if len(frame) else 0.0,
        "status": "PASS" if not mismatch.any() or float(mismatch.mean()) <= 0.001 else "BLOCKED",
    }


def attach_observed_economics(outcomes: pd.DataFrame, cost_lookup: pd.DataFrame) -> pd.DataFrame:
    """Attach static Product.CostPrice and define the gross-profit proxy."""

    result = outcomes.copy()
    costs = cost_lookup[["PricingDecisionID", "CostPrice"]].drop_duplicates("PricingDecisionID")
    result = result.merge(costs, on="PricingDecisionID", how="left", validate="one_to_one")
    result["CostPrice"] = pd.to_numeric(result["CostPrice"], errors="coerce")
    result["ObservedGrossProfit"] = pd.to_numeric(result["ActualRevenue"], errors="coerce") - result["CostPrice"] * pd.to_numeric(result["QuantityPurchased"], errors="coerce")
    result["ObservedGrossProfit_formula_check"] = (
        pd.to_numeric(result["AppliedPrice"], errors="coerce") - result["CostPrice"]
    ) * pd.to_numeric(result["QuantityPurchased"], errors="coerce")
    return result


def gross_profit_consistency_audit(outcomes: pd.DataFrame, cost_lookup: pd.DataFrame, tolerance: float = 1e-9) -> dict[str, Any]:
    """Audit the static-cost gross-profit proxy against its price-margin form."""

    attached = attach_observed_economics(outcomes, cost_lookup)
    delta = pd.to_numeric(attached["ObservedGrossProfit"], errors="coerce") - pd.to_numeric(attached["ObservedGrossProfit_formula_check"], errors="coerce")
    absolute = delta.abs()
    mismatch = absolute > tolerance
    return {
        "tolerance": tolerance,
        "rows": int(len(attached)),
        "exact_match_rate": float((~mismatch).mean()) if len(attached) else 1.0,
        "mean_delta": float(delta.mean()) if len(attached) else 0.0,
        "p95_absolute_delta": float(absolute.quantile(0.95)) if len(attached) else 0.0,
        "max_absolute_delta": float(absolute.max()) if len(attached) else 0.0,
        "mismatch_count": int(mismatch.sum()),
        "status": "PASS" if not mismatch.any() else "BLOCKED",
    }


def integrity_blockers(join: dict[str, Any], quality: dict[str, Any], revenue: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not join.get("one_to_one"):
        blockers.append("OUTCOME_JOIN_INTEGRITY_FAILURE")
    if quality.get("status") != "PASS":
        blockers.append("OUTCOME_INTEGRITY_FAILURE")
    if revenue.get("status") != "PASS":
        blockers.append("ACTUAL_REVENUE_INTEGRITY_FAILURE")
    return blockers


__all__ = [
    "attach_observed_economics",
    "audit_outcome_quality",
    "gross_profit_consistency_audit",
    "integrity_blockers",
    "revenue_consistency_audit",
    "validate_outcome_join",
]
