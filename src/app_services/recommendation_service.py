"""Authoritative read-only recommendation lookups."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from .artifact_registry import ArtifactRegistry


def json_value(value: Any) -> Any:
    """Convert Arrow/numpy/decimal values to safe JSON primitives."""

    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.generic, Decimal)):
        return json_value(value.item() if hasattr(value, "item") else float(value))
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_value(item) for item in value]
    return value


def _codes(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, np.ndarray)):
        return [str(item) for item in value if item is not None and str(item) not in {"nan", "None"}]
    return [str(value)]


class RecommendationService:
    """Expose final Phase 7 decisions without recomputing or mutating them."""

    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry

    def _row(self, decision_id: str, *, split: str = "validation") -> pd.Series:
        frame = self.registry.load_decisions(split)
        matches = frame.loc[frame["PricingDecisionID"].astype(str) == str(decision_id)]
        if matches.empty:
            raise KeyError(f"Unknown PricingDecisionID: {decision_id}")
        return matches.iloc[0]

    def get_pricing_recommendation(self, decision_id: str, *, split: str = "validation") -> dict[str, Any]:
        row = self._row(decision_id, split=split)
        reasons = _codes(row.get("phase7_change_reason_codes"))
        violations = _codes(row.get("rule_violation_reasons"))
        warnings: list[str] = []
        if bool(row.get("manual_review_flag", False)):
            warnings.append("MANUAL_REVIEW_REQUIRED")
        if violations:
            warnings.append("RULE_VIOLATION_REVIEW")
        if str(row.get("context_mode", "")).upper() == "CURRENT_INVENTORY_MODE" and pd.notna(row.get("InventorySnapshotDate")):
            warnings.append("CURRENT_SNAPSHOT_INVENTORY_CONTEXT")
        recommendation = {
            "PricingDecisionID": str(row["PricingDecisionID"]),
            "ProductID": json_value(row.get("ProductID")),
            "StoreID": json_value(row.get("StoreID")),
            "Channel": json_value(row.get("Channel")),
            "CategoryID": json_value(row.get("CategoryID")),
            "DecisionTime": json_value(row.get("DecisionTime")),
            "CurrentPrice": json_value(row.get("CurrentPrice")),
            "ModelOptimalCandidatePrice": json_value(row.get("Phase6ModelOptimalCandidatePrice")),
            "FinalRecommendedPrice": json_value(row.get("FinalRecommendedPrice")),
            "FinalAction": json_value(row.get("FinalAction")),
            "ExpectedUnits": json_value(row.get("inventory_capped_expected_units")) if pd.notna(row.get("inventory_capped_expected_units")) else json_value(row.get("expected_units")),
            "ExpectedRevenue": json_value(row.get("inventory_capped_expected_revenue")) if pd.notna(row.get("inventory_capped_expected_revenue")) else json_value(row.get("expected_revenue")),
            "ExpectedGrossProfit": json_value(row.get("inventory_capped_expected_gross_profit")) if pd.notna(row.get("inventory_capped_expected_gross_profit")) else json_value(row.get("expected_gross_profit")),
            "PricingRuleID": json_value(row.get("PricingRuleID")),
            "RuleName": json_value(row.get("RuleName")),
            "PromotionAction": json_value(row.get("PromotionAction")),
            "MarkdownAction": json_value(row.get("MarkdownAction")),
            "manual_review_flag": bool(row.get("manual_review_flag", False)),
            "reason_codes": reasons,
            "warnings": sorted(set(warnings)),
        }
        return recommendation

    def explain_pricing_recommendation(self, decision_id: str, *, split: str = "validation") -> dict[str, Any]:
        rec = self.get_pricing_recommendation(decision_id, split=split)
        current = float(rec["CurrentPrice"] or 0.0)
        final = float(rec["FinalRecommendedPrice"] or 0.0)
        change = final - current
        change_pct = None if current == 0 else change / current
        expected_units = float(rec["ExpectedUnits"] or 0.0)
        mean_quantity = float(self.registry.phase6_spec.get("phase5_mean_value", 1.0) or 1.0)
        purchase_probability = max(0.0, min(1.0, expected_units / mean_quantity))
        manual = bool(rec["manual_review_flag"])
        if manual:
            text = "This decision is flagged for manual review; the frozen business policy does not authorize an automatic replacement price."
        elif change > 0:
            text = "The governed recommendation increases the current price after applying the frozen model economics and business-rule constraints."
        elif change < 0:
            text = "The governed recommendation decreases the current price after applying the frozen model economics and business-rule constraints."
        else:
            text = "The governed recommendation holds the current price after applying the frozen model economics and business-rule constraints."
        return {
            "PricingDecisionID": rec["PricingDecisionID"],
            "current_price": current,
            "model_optimal_price": rec["ModelOptimalCandidatePrice"],
            "final_price": final,
            "price_change_amount": change,
            "price_change_percentage": change_pct,
            "purchase_probability": purchase_probability,
            "expected_demand": rec["ExpectedUnits"],
            "expected_revenue": rec["ExpectedRevenue"],
            "expected_gross_profit": rec["ExpectedGrossProfit"],
            "business_rule": {"PricingRuleID": rec["PricingRuleID"], "RuleName": rec["RuleName"]},
            "promotion_context": {"PromotionAction": rec["PromotionAction"]},
            "markdown_context": {"MarkdownAction": rec["MarkdownAction"]},
            "inventory_context": self._inventory_context(decision_id, split=split),
            "reason_codes": rec["reason_codes"],
            "warnings": rec["warnings"],
            "explanation_text": text,
            "model_implied": True,
        }

    def get_business_rule_details(self, decision_id: str, *, split: str = "validation") -> dict[str, Any]:
        row = self._row(decision_id, split=split)
        policy = self.registry.phase7_policy
        return {
            "PricingRuleID": json_value(row.get("PricingRuleID")),
            "RuleName": json_value(row.get("RuleName")),
            "Priority": json_value(row.get("RulePriority")),
            "Specificity": json_value(row.get("RuleSpecificity")),
            "MinPrice": json_value(row.get("effective_price_floor")),
            "MaxPrice": json_value(row.get("effective_price_ceiling")),
            "MinMarginPct": policy.get("rule_formulas", {}).get("MinMarginPct"),
            "MaxDiscountPct": policy.get("rule_formulas", {}).get("MaxDiscountPct"),
            "MaxPriceChangePct": policy.get("rule_formulas", {}).get("MaxPriceChangePct"),
            "effective_price_floor": json_value(row.get("effective_price_floor")),
            "effective_price_ceiling": json_value(row.get("effective_price_ceiling")),
            "FinalRecommendedPrice compliant?": bool(row.get("passes_all_pricing_rules", False)),
        }

    def _inventory_context(self, decision_id: str, *, split: str = "validation") -> dict[str, Any] | None:
        if split != "current":
            return None
        row = self._row(decision_id, split="current")
        return {
            "label": "Current snapshot inventory context",
            "AvailableQty": json_value(row.get("AvailableQty")),
            "StockStatus": json_value(row.get("StockStatus")),
            "slow_moving": bool(row.get("slow_moving_flag", False)),
            "seasonal": bool(row.get("seasonal_product_flag", False)),
            "MarkdownAction": json_value(row.get("MarkdownAction")),
            "FinalRecommendedPrice": json_value(row.get("FinalRecommendedPrice")),
        }

    def get_current_inventory_insight(
        self,
        *,
        ProductID: str | None = None,
        StoreID: str | None = None,
        CategoryID: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        frame = self.registry.load_current_inventory().copy()
        for column, value in (("ProductID", ProductID), ("StoreID", StoreID), ("CategoryID", CategoryID)):
            if value:
                frame = frame.loc[frame[column].astype(str) == str(value)]
        if action:
            frame = frame.loc[frame["FinalAction"].astype(str).str.contains(str(action), case=False, regex=False)]
        return [
            {
                "PricingDecisionID": str(row.PricingDecisionID),
                "ProductID": json_value(row.ProductID),
                "StoreID": json_value(row.StoreID),
                "CategoryID": json_value(row.CategoryID),
                "AvailableQty": json_value(row.AvailableQty),
                "StockStatus": json_value(row.StockStatus),
                "slow_moving": bool(row.slow_moving_flag),
                "seasonal": bool(row.seasonal_product_flag),
                "MarkdownAction": json_value(row.MarkdownAction),
                "FinalRecommendedPrice": json_value(row.FinalRecommendedPrice),
                "FinalAction": json_value(row.FinalAction),
            }
            for row in frame.head(min(max(int(limit), 1), 100)).itertuples()
        ]

    def search_recommendations(self, *, limit: int = 100, split: str = "validation", **filters: Any) -> list[dict[str, Any]]:
        frame = self.registry.load_decisions(split).copy()
        allowed = {"PricingDecisionID", "ProductID", "StoreID", "Channel", "CategoryID", "FinalAction"}
        for column, value in filters.items():
            if value in (None, "", []):
                continue
            if column == "manual_review_flag":
                frame = frame.loc[frame["manual_review_flag"].astype(bool) == bool(value)]
            elif column in allowed:
                frame = frame.loc[frame[column].astype(str).str.contains(str(value), case=False, regex=False)]
        rows: list[dict[str, Any]] = []
        for _, row in frame.head(min(max(int(limit), 1), 100)).iterrows():
            rec = self.get_pricing_recommendation(str(row["PricingDecisionID"]), split=split)
            rows.append({key: rec[key] for key in ("PricingDecisionID", "ProductID", "StoreID", "Channel", "CategoryID", "CurrentPrice", "ModelOptimalCandidatePrice", "FinalRecommendedPrice", "FinalAction", "ExpectedUnits", "ExpectedRevenue", "ExpectedGrossProfit", "manual_review_flag")})
        return rows


__all__ = ["RecommendationService", "json_value"]
