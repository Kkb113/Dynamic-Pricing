"""Frozen Phase 4/5 inference adapter used only for exact Phase 7 candidates.

The adapter loads accepted artifacts; it never fits, tunes, or calibrates a
model.  It is deliberately lazy so deterministic CI policy tests do not need
CatBoost or a live SQL source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class FrozenPhase7Scorer:
    """Score one exact-cent candidate through the accepted Phase 4/5 stack."""

    def __init__(self, root: Path):
        from catboost import CatBoostClassifier

        from features.feature_contract import load_contract
        from models.catboost_data import build_purchase_model_features_for_candidate_price, make_catboost_pool

        self._build_features = build_purchase_model_features_for_candidate_price
        self._make_pool = make_catboost_pool
        self.contract = load_contract(root / "contracts/phase2_feature_contract_v1.yaml")
        self.spec = json.loads((root / "artifacts/phase4/frozen_model_spec.json").read_text(encoding="utf-8"))
        self.feature_names = tuple(self.spec["ordered_feature_names"])
        self.model = CatBoostClassifier()
        self.model.load_model(str(root / "artifacts/phase4/models/purchase_catboost.cbm"))
        quantity_spec = json.loads((root / "artifacts/phase5/models/quantity_estimator_metadata.json").read_text(encoding="utf-8"))
        self.quantity_mean = float(quantity_spec["mean_value"])

    def __call__(self, source: pd.Series, candidate_price: float) -> dict[str, Any]:
        frame = pd.DataFrame([source.to_dict() if isinstance(source, pd.Series) else dict(source)])
        prepared = self._build_features(frame, float(candidate_price), self.contract, self.feature_names)
        pool = self._make_pool(prepared, self.contract, self.feature_names)
        probability = float(np.asarray(self.model.predict_proba(pool), dtype=float)[0, 1])
        units = float(probability * self.quantity_mean)
        cost = float(source.get("CostPrice", 0.0))
        price = float(candidate_price)
        return {
            "raw_purchase_probability": probability,
            "conditional_quantity": self.quantity_mean,
            "raw_expected_units": units,
            "safe_expected_units": units,
            "raw_expected_revenue": price * units,
            "expected_revenue": price * units,
            "unit_gross_profit": price - cost,
            "candidate_margin_pct": None if price <= 0 else (price - cost) / price,
            "raw_expected_gross_profit": (price - cost) * units,
            "expected_gross_profit": (price - cost) * units,
            "negative_unit_margin_candidate": bool(price < cost),
            "response_guard_adjusted_flag": False,
            "number_of_adjusted_candidates": 0,
            "maximum_expected_units_adjustment": 0.0,
            "mean_expected_units_adjustment": 0.0,
            "inventory_constraint_applied": False,
            "available_inventory": np.nan,
        }


def recompute_response_safety(surface: pd.DataFrame) -> pd.DataFrame:
    """Recompute cumulative-minimum response safety after adding candidates."""

    if surface.empty:
        return surface.copy()
    result = surface.copy()
    result["raw_expected_units"] = pd.to_numeric(result["raw_expected_units"], errors="coerce")
    result["CandidatePrice"] = pd.to_numeric(result["CandidatePrice"], errors="coerce")
    result["CostPrice"] = pd.to_numeric(result["CostPrice"], errors="coerce")
    result["safe_expected_units"] = np.nan
    for _, group in result.groupby("PricingDecisionID", sort=False):
        ordered = group.sort_values("CandidatePrice", kind="mergesort")
        result.loc[ordered.index, "safe_expected_units"] = np.minimum.accumulate(ordered["raw_expected_units"].to_numpy(float))
    result["expected_revenue"] = result["CandidatePrice"] * result["safe_expected_units"]
    result["raw_expected_revenue"] = result["CandidatePrice"] * result["raw_expected_units"]
    result["unit_gross_profit"] = result["CandidatePrice"] - result["CostPrice"]
    result["candidate_margin_pct"] = np.where(result["CandidatePrice"] > 0, result["unit_gross_profit"] / result["CandidatePrice"], np.nan)
    result["expected_gross_profit"] = result["unit_gross_profit"] * result["safe_expected_units"]
    result["raw_expected_gross_profit"] = result["unit_gross_profit"] * result["raw_expected_units"]
    return result


__all__ = ["FrozenPhase7Scorer", "recompute_response_safety"]
