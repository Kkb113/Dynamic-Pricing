"""Rule-compliant business candidate selection preserving Phase 6 economics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


TIE_ABSOLUTE = 1e-8
TIE_RELATIVE = 0.001
MATERIALITY = 0.005


def _best(group: pd.DataFrame, *, objective: str = "expected_gross_profit") -> pd.Series:
    ordered = group.sort_values(["CandidatePrice", "candidate_rank_by_price"], kind="mergesort")
    values = ordered[objective].astype(float).to_numpy()
    best = float(np.nanmax(values))
    band = max(TIE_ABSOLUTE, abs(best) * TIE_RELATIVE)
    near = ordered.loc[(best - ordered[objective].astype(float)) <= band].copy()
    current = float(ordered["CurrentPrice"].iloc[0])
    near["_distance"] = (near["CandidatePrice"].astype(float) / current - 1.0).abs()
    return near.sort_values(["_distance", "CandidatePrice", "candidate_rank_by_price"], kind="mergesort").iloc[0]


def select_business_candidates(
    surface: pd.DataFrame,
    *,
    materiality: float = MATERIALITY,
    directional: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Select only candidates that passed all hard rule constraints."""

    directional = directional or {}
    rows: list[dict[str, Any]] = []
    for decision_id, group in surface.groupby("PricingDecisionID", sort=False):
        group = group.sort_values(["CandidatePrice", "candidate_rank_by_price"], kind="mergesort")
        current_rows = group.loc[np.isclose(group["CandidatePrice"].astype(float), group["CurrentPrice"].astype(float), atol=0.005, rtol=0)]
        current = current_rows.iloc[0] if len(current_rows) else None
        compliant = group.loc[group["passes_all_pricing_rules"].astype(bool)].copy()
        current_compliant = current is not None and bool(current["passes_all_pricing_rules"])
        direction = directional.get(str(decision_id))
        if direction == "NON_INCREASING":
            compliant = compliant.loc[compliant["CandidatePrice"].astype(float) <= compliant["CurrentPrice"].astype(float) + 0.005]
        elif direction == "NON_DECREASING":
            compliant = compliant.loc[compliant["CandidatePrice"].astype(float) >= compliant["CurrentPrice"].astype(float) - 0.005]
        if compliant.empty:
            rows.append({"PricingDecisionID": decision_id, "selection_status": "MANUAL_REVIEW_NO_COMPLIANT_CANDIDATE", "selected": None, "current_compliant": current_compliant})
            continue
        best = _best(compliant)
        if current is not None and current_compliant:
            current_gp = float(current["expected_gross_profit"])
            uplift = float(best["expected_gross_profit"]) - current_gp
            relative = uplift / max(abs(current_gp), 1e-8)
            if uplift <= 0 or relative < materiality:
                best = current
                selection_status = "KEEP_CURRENT_NO_MATERIAL_UPLIFT"
            else:
                selection_status = "CHANGE_CANDIDATE"
        else:
            selection_status = "RULE_FORCED_CHANGE" if current is not None and not current_compliant else "CHANGE_CANDIDATE"
        row = best.to_dict()
        row.update({
            "selection_status": selection_status,
            "current_compliant": current_compliant,
            "rule_forced_change": bool(current is not None and not current_compliant),
        })
        rows.append(row)
    return pd.DataFrame(rows)


__all__ = ["MATERIALITY", "TIE_ABSOLUTE", "TIE_RELATIVE", "select_business_candidates"]
