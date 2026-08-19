"""Frozen Phase 6 candidate economics and Phase 7 rule checks."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from .artifact_registry import ArtifactRegistry
from .recommendation_service import json_value


class SimulationError(ValueError):
    """Controlled simulation input or support-envelope failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SimulationService:
    """Score prices through the accepted Phase 6/7 stack only."""

    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry

    def _decision(self, decision_id: str, split: str = "validation") -> pd.Series:
        frame = self.registry.load_decisions(split)
        rows = frame.loc[frame["PricingDecisionID"].astype(str) == str(decision_id)]
        if rows.empty:
            raise KeyError(f"Unknown PricingDecisionID: {decision_id}")
        return rows.iloc[0]

    def _surface_rows(self, decision_id: str) -> pd.DataFrame:
        surface = self.registry.load_candidate_surface("validation")
        return surface.loc[surface["PricingDecisionID"].astype(str) == str(decision_id)].copy()

    def support_envelope(self, decision_id: str, *, split: str = "validation") -> dict[str, float]:
        decision = self._decision(decision_id, split=split)
        rows = self._surface_rows(decision_id)
        current = float(decision["CurrentPrice"])
        if rows.empty:
            low = float(self.registry.phase6_spec.get("effective_support_low", 0.0))
            high = float(self.registry.phase6_spec.get("effective_support_high", 0.0))
        else:
            low = float(pd.to_numeric(rows["support_low"], errors="coerce").dropna().iloc[0])
            high = float(pd.to_numeric(rows["support_high"], errors="coerce").dropna().iloc[0])
        return {"support_low_multiplier": low, "support_high_multiplier": high, "support_low_price": current * low, "support_high_price": current * high}

    @staticmethod
    def _validate_price(price: Any) -> float:
        try:
            value = float(price)
        except (TypeError, ValueError) as exc:
            raise SimulationError("INVALID_CANDIDATE_PRICE", "CandidatePrice must be finite and greater than zero") from exc
        if not math.isfinite(value) or value <= 0:
            raise SimulationError("INVALID_CANDIDATE_PRICE", "CandidatePrice must be finite and greater than zero")
        return round(value, 2)

    def _within_support(self, decision_id: str, price: float, split: str) -> bool:
        envelope = self.support_envelope(decision_id, split=split)
        return envelope["support_low_price"] - 0.005 <= price <= envelope["support_high_price"] + 0.005

    @staticmethod
    def _rule_check(decision: pd.Series, price: float) -> tuple[bool, list[str]]:
        violations: list[str] = []
        floor = pd.to_numeric(pd.Series([decision.get("effective_price_floor")]), errors="coerce").iloc[0]
        ceiling = pd.to_numeric(pd.Series([decision.get("effective_price_ceiling")]), errors="coerce").iloc[0]
        if pd.notna(floor) and price < float(floor) - 0.005:
            violations.append("RULE_MIN_PRICE")
        if pd.notna(ceiling) and price > float(ceiling) + 0.005:
            violations.append("RULE_MAX_PRICE")
        cost = pd.to_numeric(pd.Series([decision.get("CostPrice")]), errors="coerce").iloc[0]
        if pd.notna(cost) and price < float(cost):
            violations.append("NEGATIVE_UNIT_MARGIN")
        return not violations, violations

    def _surface_match(self, rows: pd.DataFrame, price: float) -> pd.Series | None:
        if rows.empty:
            return None
        values = pd.to_numeric(rows["CandidatePrice"], errors="coerce")
        matches = rows.loc[(values - price).abs() <= 0.005]
        if matches.empty:
            return None
        return matches.sort_values("candidate_rank_by_price", kind="mergesort").iloc[0]

    @lru_cache(maxsize=1)
    def _frozen_scorer(self):
        from phase7.frozen_scorer import FrozenPhase7Scorer

        return FrozenPhase7Scorer(self.registry.root)

    def simulate_price(self, decision_id: str, candidate_price: Any, *, split: str = "validation") -> dict[str, Any]:
        price = self._validate_price(candidate_price)
        if not self._within_support(decision_id, price, split):
            raise SimulationError("MODEL_SUPPORT_LIMIT", "This price lies outside the range supported by the historical training data and will not be scored automatically.")
        decision = self._decision(decision_id, split=split)
        rows = self._surface_rows(decision_id)
        matched = self._surface_match(rows, price)
        if matched is not None:
            values = {
                "purchase_probability": matched.get("raw_purchase_probability"),
                "expected_quantity_if_purchase": matched.get("conditional_quantity"),
                "expected_units": matched.get("safe_expected_units"),
                "expected_revenue": matched.get("expected_revenue"),
                "expected_gross_profit": matched.get("expected_gross_profit"),
                "candidate_margin_pct": matched.get("candidate_margin_pct"),
            }
        else:
            context = self.registry.load_feature_context(split)
            context = context.loc[context["PricingDecisionID"].astype(str) == str(decision_id)]
            if context.empty:
                raise SimulationError("MISSING_FEATURE_CONTEXT", "No frozen feature context is available for this decision")
            scored = self._frozen_scorer().score_candidates(context.iloc[[0]], [price])[0]
            values = {
                "purchase_probability": scored["raw_purchase_probability"],
                "expected_quantity_if_purchase": scored["conditional_quantity"],
                "expected_units": scored["safe_expected_units"],
                "expected_revenue": scored["expected_revenue"],
                "expected_gross_profit": scored["expected_gross_profit"],
                "candidate_margin_pct": scored["candidate_margin_pct"],
            }
        compliant, violations = self._rule_check(decision, price)
        return {
            "PricingDecisionID": str(decision_id),
            "CandidatePrice": price,
            **{key: json_value(value) for key, value in values.items()},
            "within_model_support": True,
            "business_rule_compliance": compliant,
            "rule_violations": violations,
            "model_implied": True,
        }

    def candidate_surface(self, decision_id: str) -> pd.DataFrame:
        rows = self._surface_rows(decision_id)
        if rows.empty:
            raise KeyError(f"No candidate surface for PricingDecisionID: {decision_id}")
        return rows.sort_values("CandidatePrice", kind="mergesort").reset_index(drop=True)

    def compare_price_scenarios(self, decision_id: str, *, split: str = "validation") -> list[dict[str, Any]]:
        decision = self._decision(decision_id, split=split)
        rows = self._surface_rows(decision_id)
        prices: list[tuple[str, float | None]] = [
            ("Historical AppliedPrice", float(pd.to_numeric(rows["HistoricalAppliedPrice"], errors="coerce").dropna().iloc[0]) if not rows.empty and pd.to_numeric(rows["HistoricalAppliedPrice"], errors="coerce").notna().any() else None),
            ("CurrentPrice", float(decision["CurrentPrice"])),
            ("Phase6 Model-Optimal Price", float(decision["Phase6ModelOptimalCandidatePrice"]) if pd.notna(decision.get("Phase6ModelOptimalCandidatePrice")) else None),
            ("Phase7 Final Recommended Price", float(decision["FinalRecommendedPrice"]) if pd.notna(decision.get("FinalRecommendedPrice")) else None),
        ]
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, float]] = set()
        for label, price in prices:
            if price is None or not math.isfinite(price):
                continue
            key = (label, round(price, 2))
            if key in seen:
                continue
            seen.add(key)
            try:
                scored = self.simulate_price(decision_id, price, split=split)
            except SimulationError as exc:
                scored = {"CandidatePrice": round(price, 2), "error_code": exc.code, "error": exc.message, "model_implied": True}
            result.append({"scenario": label, **scored})
        return result


__all__ = ["SimulationError", "SimulationService"]
