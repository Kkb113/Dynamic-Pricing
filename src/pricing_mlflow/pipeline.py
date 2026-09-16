"""The frozen pricing decision unit, shared by batch and interactive callers.

Inputs are point-in-time features and explicit business source projections.
No database, customer dataset, training operation, or writeback is embedded.
"""
from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from threading import RLock

import numpy as np
import pandas as pd

from app_services.recommendation_service import json_value
from business_rules.rule_loader import PRICING_RULE_COLUMNS, validate_pricing_rules
from inventory_policy.inventory_loader import INVENTORY_COLUMNS, validate_inventory
from inventory_policy.inventory_policy import CURRENT_INVENTORY_MODE, HISTORICAL_POLICY_MODE
from optimization.candidate_grid import CandidateGrid, generate_candidate_rows, round_price_half_up
from optimization.price_selector import select_model_optimal_prices
from phase7.frozen_scorer import FrozenPhase7Scorer, recompute_response_safety
from phase7.runner import build_business_decisions, annotate_rule_compliance
from promotions.promotion_loader import PROMOTION_COLUMNS, validate_promotions
from pricing_mlflow.release import fingerprint

VERSION = "pricing.scoring.v1"
FORBIDDEN = {"CustomerID", "SessionID", "PurchasedFlag", "QuantityPurchased", "ActualRevenue", "CustomerEmail"}
MAX_CONTEXTS = 1000
MAX_REQUEST_BYTES = 2_000_000


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    return json_value(value)


def records(frame):
    return [clean(row) for row in frame.to_dict("records")]


class PricingPipeline:
    """A bounded, deterministic, advisory-only decision pipeline."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.scorer = FrozenPhase7Scorer(self.root)
        self.release_fingerprint = fingerprint(self.root)
        self.optimizer = json.loads((self.root / "artifacts/phase6/frozen_optimizer_spec.json").read_text())
        self.policy = json.loads((self.root / "artifacts/phase7/frozen_business_policy_spec.json").read_text())
        self.grid = CandidateGrid(*[float(self.optimizer[k]) for k in
            ("technical_multiplier_low", "technical_multiplier_high", "training_ratio_p01", "training_ratio_p99",
             "effective_support_low", "effective_support_high")], tuple(self.optimizer["candidate_multiplier_template"]))
        self.lock = RLock()
        # Existing App is small. No nested parallelism or unbounded cache.
        self.scorer.model.predict_proba = partial(self.scorer.model.predict_proba, thread_count=2)

    def _context(self, value):
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_CONTEXTS:
            raise ValueError("CONTEXT_COUNT_INVALID")
        context = pd.DataFrame(value)
        if FORBIDDEN.intersection(context.columns):
            raise ValueError("FORBIDDEN_CONTEXT_FIELDS")
        required = set(self.scorer.feature_names) | {"PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "CostPrice"}
        audit = {"selected_price_effective_from", "selected_sales_order_date", "selected_behavior_event_at",
                 "selected_competitor_observed_at"}
        if set(context.columns).difference(required | audit):
            raise ValueError("UNCONTRACTED_CONTEXT_FIELDS")
        if required.difference(context.columns):
            raise ValueError("FEATURE_CONTRACT_INCOMPLETE")
        if context.PricingDecisionID.isna().any() or context.PricingDecisionID.astype(str).duplicated().any():
            raise ValueError("DECISION_ID_INVALID")
        for name in ("PricingDecisionID", "ProductID", "StoreID", "Channel"):
            if context[name].isna().any() or not context[name].astype(str).str.len().between(1, 128).all():
                raise ValueError("IDENTITY_CONTEXT_INVALID")
        if not set(context.Channel).issubset({"Email", "Kiosk", "Mobile", "Online", "Store", "Web"}):
            raise ValueError("CHANNEL_NOT_OBSERVED_IN_RELEASE")
        context["DecisionTime"] = pd.to_datetime(context.DecisionTime, errors="coerce")
        if context.DecisionTime.isna().any():
            raise ValueError("AS_OF_REQUIRED")
        for name in ("CurrentPrice", "AppliedPrice", "BasePrice", "CostPrice"):
            values = pd.to_numeric(context[name], errors="coerce")
            if not np.isfinite(values).all() or not values.gt(0).all():
                raise ValueError("PRICE_CONTEXT_INVALID")
        for name in ("selected_price_effective_from", "selected_sales_order_date", "selected_behavior_event_at",
                     "selected_competitor_observed_at"):
            if name in context:
                dates = pd.to_datetime(context[name], errors="coerce")
                if (dates > context.DecisionTime).any():
                    raise ValueError("FUTURE_CONTEXT_REJECTED")
        return context

    @staticmethod
    def _source(payload, name, columns, validate):
        values = payload.get(name)
        if not isinstance(values, list) or len(values) > 20000:
            raise ValueError("BUSINESS_SOURCE_REQUIRED:" + name)
        if not values:
            return validate(pd.DataFrame(columns=list(columns)))
        if any(not isinstance(row, dict) or set(row) != set(columns) for row in values):
            raise ValueError("BUSINESS_SOURCE_SCHEMA:" + name)
        numeric = {"MinPrice", "MaxPrice", "MinMarginPct", "MaxDiscountPct", "MaxPriceChangePct", "Priority", "DiscountPct",
                   "OpeningQty", "ReceivedQty", "SoldQty", "ReturnedQty", "AdjustmentQty", "ReservedQty", "OnHandQty", "AvailableQty"}
        for row in values:
            for key in numeric.intersection(row):
                v = row[key]
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v)):
                    raise ValueError("BUSINESS_SOURCE_VALUE_INVALID:" + key)
            if "ActiveFlag" in row and not isinstance(row["ActiveFlag"], bool):
                raise ValueError("BUSINESS_SOURCE_ACTIVE_FLAG_INVALID")
            for key in {"EffectiveFrom", "EffectiveTo", "StartDate", "EndDate", "SnapshotDate"}.intersection(row):
                if row[key] is not None and pd.isna(pd.to_datetime(row[key], errors="coerce")):
                    raise ValueError("BUSINESS_SOURCE_DATE_INVALID")
        return validate(pd.DataFrame(values))

    def score(self, payload: dict):
        if not isinstance(payload, dict) or set(payload).difference({"schema_version", "context", "rules", "promotions", "inventory", "mode", "candidate_prices"}):
            raise ValueError("REQUEST_SCHEMA_INVALID")
        if payload.get("schema_version") != VERSION:
            raise ValueError("REQUEST_VERSION_INVALID")
        context = self._context(payload.get("context"))
        mode = payload.get("mode")
        if mode not in {HISTORICAL_POLICY_MODE, CURRENT_INVENTORY_MODE}:
            raise ValueError("MODE_REQUIRED")
        if mode == CURRENT_INVENTORY_MODE:
            age = (pd.Timestamp("2025-12-31") - context.DecisionTime.dt.normalize()).dt.days
            if not age.between(0, self.policy["max_current_context_age_days"]).all():
                raise ValueError("CURRENT_CONTEXT_STALE_OR_FUTURE")
        rules = self._source(payload, "rules", PRICING_RULE_COLUMNS, validate_pricing_rules)
        promotions = self._source(payload, "promotions", PROMOTION_COLUMNS, validate_promotions)
        inventory = self._source(payload, "inventory", INVENTORY_COLUMNS, validate_inventory)
        if mode == HISTORICAL_POLICY_MODE and not inventory.empty:
            raise ValueError("HISTORICAL_INVENTORY_LEAKAGE")
        if not inventory.empty and not inventory.SnapshotDate.eq(pd.Timestamp("2025-12-31")).all():
            raise ValueError("UNAPPROVED_INVENTORY_SNAPSHOT")
        requested = payload.get("candidate_prices", {})
        if not isinstance(requested, dict) or set(requested).difference(set(context.PricingDecisionID)):
            raise ValueError("SIMULATION_DECISION_INVALID")
        for decision_id, value in requested.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError("SIMULATION_PRICE_INVALID")
            current = float(context.loc[context.PricingDecisionID.eq(decision_id), "CurrentPrice"].iloc[0])
            price = round_price_half_up(value)
            if not current * self.grid.effective_low - .005 <= price <= current * self.grid.effective_high + .005:
                raise ValueError("MODEL_SUPPORT_LIMIT")
        with self.lock:
            self.scorer._score_cache.clear()
            surface = generate_candidate_rows(context, self.grid)
            sources = context.set_index("PricingDecisionID").loc[surface.PricingDecisionID].reset_index()
            economics = self.scorer.score_candidates(sources, surface.CandidatePrice.to_numpy(float))
            for name in economics[0]:
                surface[name] = [row[name] for row in economics]
            surface = recompute_response_safety(surface)
            recommendations = select_model_optimal_prices(surface)
            decisions, diagnostics = build_business_decisions(surface, recommendations, context,
                rules=rules, promotions=promotions, mode=mode,
                rule_policy=self.policy["rule_precedence_policy"],
                percentage_convention=self.policy["rule_percentage_convention"],
                promotion_pricing_mode=self.policy["promotion_pricing_mode"], inventory=inventory,
                status_mapping=self.policy["inventory_status_map"],
                slow_thresholds=self.policy["slow_moving_thresholds"],
                inventory_category_p75=self.policy["high_inventory_category_p75"],
                inventory_global_p75=self.policy["high_inventory_global_p75_fallback"],
                score_candidate=self.scorer if self.policy["boundary_scoring_enabled"] else None)
            simulations = []
            for decision_id, value in requested.items():
                price = round_price_half_up(value)
                source = context.loc[context.PricingDecisionID.eq(decision_id)].iloc[0]
                base = surface.loc[surface.PricingDecisionID.eq(decision_id)].copy()
                candidate = {**base.iloc[0].to_dict(), **self.scorer(source, price),
                             "CandidatePrice": price, "__requested": True}
                base["__requested"] = False
                combined = recompute_response_safety(pd.concat([base, pd.DataFrame([candidate])], ignore_index=True))
                combined["_phase7_rule_reference_price"] = float(recommendations.loc[
                    recommendations.PricingDecisionID.eq(decision_id), "ModelOptimalCandidatePrice"].iloc[0])
                checked, _ = annotate_rule_compliance(combined, rules,
                    policy=self.policy["rule_precedence_policy"], percentage_convention=self.policy["rule_percentage_convention"])
                selected = checked.loc[checked["__requested"]].copy()
                decision = decisions.loc[decisions.PricingDecisionID.eq(decision_id)].iloc[0]
                selected["simulation_only"] = True
                selected["eligible_for_action"] = selected.passes_all_pricing_rules & (not bool(decision.manual_review_flag)) & (selected.CandidatePrice >= float(source.CostPrice)) & selected.CandidatePrice.eq(decision.FinalRecommendedPrice)
                selected["all_business_policies_approved"] = selected.eligible_for_action
                selected["governed_recommendation_action"] = decision.FinalAction
                selected["stock_capped"] = False
                simulations.extend(records(selected))
            self.scorer._score_cache.clear()
        # Keep raw probability/demand separate from guarded and stock-capped values.
        selected_prices = decisions[["PricingDecisionID", "FinalRecommendedPrice"]].copy()
        selected_prices["FinalRecommendedPrice"] = pd.to_numeric(selected_prices.FinalRecommendedPrice, errors="raise").astype(float)
        final = selected_prices.merge(surface,
            left_on=["PricingDecisionID", "FinalRecommendedPrice"],
            right_on=["PricingDecisionID", "CandidatePrice"], how="left", validate="one_to_one")
        for name in ("raw_purchase_probability", "conditional_quantity", "raw_expected_units",
                     "raw_expected_revenue", "raw_expected_gross_profit"):
            decisions[name] = final[name].to_numpy()
        decisions["currency_code"] = None
        decisions["currency_status"] = "UNVERIFIED_SOURCE_UNIT"
        decisions["model_release"] = self.release_fingerprint
        return clean({"schema_version": VERSION, "decisions": records(decisions),
                "model_recommendations": records(recommendations), "simulations": simulations, "diagnostics": diagnostics,
                "advisory_only": True, "auto_writeback": False,
                "warnings": ["FROZEN_SYNTHETIC_SNAPSHOT", "MODEL_IMPLIED_NOT_REALIZED_UPLIFT",
                             "UPPER_BOUND_PRICE_TENDENCY", "CURRENCY_UNVERIFIED"]})

    def predict(self, frame: pd.DataFrame):
        if not isinstance(frame, pd.DataFrame) or list(frame.columns) != ["request_json"] or len(frame) > 10:
            raise ValueError("MLFLOW_INPUT_SCHEMA_INVALID")
        output = []
        for value in frame.request_json:
            if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_REQUEST_BYTES:
                raise ValueError("REQUEST_SIZE_INVALID")
            payload = json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
            output.append(json.dumps(self.score(payload), sort_keys=True, allow_nan=False))
        return pd.DataFrame({"response_json": output})
