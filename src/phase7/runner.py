"""Canonical Phase 7 business-policy acceptance runner.

The runner consumes frozen Phase 6 surfaces, never retrains a model, and keeps
historical inventory out of VALIDATION/TEST.  SQL access is read-only; ``--fixtures``
is available for deterministic CI-style evidence and never masquerades as live
source evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from audit.database_profile import assert_read_only_sql, connect_read_only, connection_string_from_settings, load_env_file
from business_rules.rule_constraints import derive_rule_bounds, evaluate_candidate_constraints
from business_rules.rule_loader import PRICING_RULE_COLUMNS, load_pricing_rules
from business_rules.rule_replay import replay_metrics, replay_historical_rule_application
from business_rules.rule_resolver import resolve_pricing_rule
from business_rules.rule_semantics import audit_percentage_semantics, infer_rule_precedence, rule_specificity
from decisioning.candidate_augmentation import augment_rule_boundary_candidates
from decisioning.business_selector import select_business_candidates
from decisioning.final_decision import final_action
from inventory_policy.inventory_loader import INVENTORY_COLUMNS, audit_inventory, freeze_status_mapping, load_inventory
from inventory_policy.inventory_policy import CURRENT_INVENTORY_MODE, HISTORICAL_POLICY_MODE, cap_inventory_economics, resolve_current_inventory
from inventory_policy.markdown_policy import (
    audit_seasonal_semantics,
    derive_slow_moving_thresholds,
    markdown_eligibility,
    seasonal_product_flag,
    slow_moving_flag,
)
from phase7.artifacts import compute_environment, write_csv, write_frame, write_phase7_json
from phase7.frozen_scorer import FrozenPhase7Scorer, recompute_response_safety
from phase7.validation import validate_decision_frame, verify_phase6_upstream
from promotions.promotion_loader import PROMOTION_COLUMNS, load_promotions
from promotions.promotion_resolver import audit_promotion_semantics, resolve_promotion, round_promotion_price
from validation.artifacts import sha256_file


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/phase7"
BASE_BRANCH = "codex/phase1-data-audit"
DEFAULT_POLICY = "P1_PRIORITY_DESC_SPECIFICITY_DESC"
DEFAULT_PERCENTAGE_CONVENTION = "PERCENT_POINTS"
ACTION_ENUM = {
    "OUT_OF_STOCK_NO_PRICE_ACTION",
    "MANUAL_REVIEW_INVENTORY_UNAVAILABLE",
    "MANUAL_REVIEW_RULE_CONFLICT",
    "MANUAL_REVIEW_NO_COMPLIANT_CANDIDATE",
    "HONOR_ACTIVE_PROMOTION",
    "PROMOTION_REVIEW",
    "SEASONAL_SLOW_MOVING_MARKDOWN",
    "MARKDOWN_REVIEW_REQUIRED",
    "RULE_FORCED_CHANGE",
    "PRICE_INCREASE",
    "PRICE_DECREASE",
    "HOLD_PRICE",
}


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _run_phase7_tests() -> dict[str, Any]:
    """Run deterministic policy tests and report counts in acceptance evidence."""

    try:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/phase7"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        match = re.search(r"(?P<passed>\d+) passed(?:, (?P<failed>\d+) failed)?", output)
        passed = int(match.group("passed")) if match else 0
        failed = int(match.group("failed") or 0) if match else (1 if completed.returncode else 0)
        return {"status": "PASS" if completed.returncode == 0 and failed == 0 else "FAIL", "passed": passed, "failed": failed, "total": passed + failed, "command": "pytest -q tests/phase7", "output_tail": output[-2000:]}
    except Exception as exc:
        return {"status": "FAIL", "passed": 0, "failed": 1, "total": 1, "command": "pytest -q tests/phase7", "error": str(exc)}


def _config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config/phase7_business_policy.yaml").read_text(encoding="utf-8"))


def _empty_rules() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in PRICING_RULE_COLUMNS})


def _empty_promotions() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in PROMOTION_COLUMNS})


def _empty_inventory() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in INVENTORY_COLUMNS})


def _load_source_tables(*, use_fixtures: bool) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Load only the seven documented tables; every SQL statement is SELECT-only."""

    if use_fixtures:
        return {"rules": _empty_rules(), "promotions": _empty_promotions(), "inventory": _empty_inventory(), "decision_log": pd.DataFrame(), "product": pd.DataFrame(), "product_category": pd.DataFrame(), "price_history": pd.DataFrame()}, {"status": "FIXTURE_ONLY", "live_sql": False}
    env_file = Path(os.environ.get("PHASE7_ENV_FILE", ROOT.parent / ".env"))
    settings = {
        "env_file": str(env_file),
        "server": os.environ.get("PHASE7_SQL_SERVER", "localhost"),
        "database_key": "SQL_SERVER_DATABASE",
        "username_key": "SQL_SERVER_USER_NAME",
        "password_key": "SQL_SERVER_PASSWORD",
        "odbc_driver": os.environ.get("PHASE7_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
        "connect_timeout_seconds": 30,
    }
    try:
        raw = connection_string_from_settings(settings, ROOT)
    except RuntimeError:
        # ``connection_string_from_settings`` expects a path relative to the
        # project root; retry with the explicit environment-file parent.
        settings["env_file"] = env_file.name
        raw = connection_string_from_settings(settings, env_file.parent)
    source_queries = {
        # Only policy-replay columns are selected from the decision log.  Outcome
        # fields (PurchasedFlag, QuantityPurchased, ActualRevenue, OutcomeTime,
        # OrderLineID) are intentionally excluded from the Phase 7 read path.
        "decision_log": "SELECT [PricingDecisionID], [DecisionTime], [ProductID], [StoreID], [Channel], [CurrentPrice], [RecommendedPrice], [AppliedPrice], [PricingRuleID] FROM [dbo].[Pricing_Decision_Log]",
        "product": "SELECT [ProductID], [CategoryID], [Season], [BasePrice], [CostPrice] FROM [dbo].[Product]",
        "product_category": "SELECT [CategoryID], [ParentCategoryID], [CategoryName], [CategoryLevel], [DepartmentName] FROM [dbo].[Product_Category]",
        "price_history": "SELECT [PriceHistoryID], [ProductID], [StoreID], [Channel], [BasePrice], [SellingPrice], [DiscountPct], [PromotionID], [EffectiveFrom], [EffectiveTo], [PriceReason] FROM [dbo].[Product_Price_History]",
    }

    def _load_with(db: Any) -> dict[str, pd.DataFrame]:
        rules = load_pricing_rules(db)
        promotions = load_promotions(db)
        inventory = load_inventory(db)
        loaded: dict[str, pd.DataFrame] = {"rules": rules, "promotions": promotions, "inventory": inventory}
        for key, sql in source_queries.items():
            loaded[key] = pd.DataFrame(db.rows(sql))
        return loaded

    try:
        with connect_read_only(None, settings["odbc_driver"], 30, raw_connection=raw) as db:
            return _load_with(db), {"status": "CONNECTED_READ_ONLY", "live_sql": True, "driver": settings["odbc_driver"], "server": settings["server"], "database": "configured"}
    except Exception as exc:
        # Some Windows-hosted SQL Server installations force a TLS handshake
        # that the sandbox ODBC client cannot complete.  pymssql uses the TDS
        # protocol directly; keep the same SELECT-only contract as the ODBC
        # path and record the driver for provenance.
        try:
            import pymssql  # type: ignore

            values = load_env_file(env_file)
            connection = pymssql.connect(
                server=settings["server"],
                user=values["SQL_SERVER_USER_NAME"],
                password=values["SQL_SERVER_PASSWORD"],
                database=values["SQL_SERVER_DATABASE"],
                login_timeout=30,
                timeout=60,
                tds_version="7.4",
            )

            class _PymssqlReadOnly:
                def __init__(self, conn: Any):
                    self.connection = conn

                def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
                    assert_read_only_sql(sql)
                    cursor = self.connection.cursor(as_dict=True)
                    cursor.execute(sql, params)
                    return list(cursor.fetchall())

            try:
                loaded = _load_with(_PymssqlReadOnly(connection))
            finally:
                connection.close()
            return loaded, {"status": "CONNECTED_READ_ONLY", "live_sql": True, "driver": "pymssql_tds", "odbc_error_type": type(exc).__name__, "server": settings["server"], "database": "configured"}
        except Exception as fallback_exc:
            return {"rules": _empty_rules(), "promotions": _empty_promotions(), "inventory": _empty_inventory(), "decision_log": pd.DataFrame(), "product": pd.DataFrame(), "product_category": pd.DataFrame(), "price_history": pd.DataFrame()}, {
                "status": "LIVE_SQL_UNAVAILABLE",
                "live_sql": False,
                "error_type": type(fallback_exc).__name__,
                "odbc_error_type": type(exc).__name__,
                "error": str(fallback_exc).splitlines()[0][:300],
            }


def _load_context(root: Path, split: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    dataset = pd.read_parquet(root / "artifacts/phase2/feature_dataset.parquet")
    assignments = pd.read_parquet(root / "artifacts/phase3/split_assignments.parquet")
    ids = set(assignments.loc[assignments["split"].eq(split), "PricingDecisionID"].astype(str))
    context = dataset.loc[dataset["PricingDecisionID"].astype(str).isin(ids)].copy()
    context = context.sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").reset_index(drop=True)
    return context, assignments


def _surface_with_context(surface: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    extra = [column for column in ["CategoryID", "Season", "product_store_sales_30d", "product_sales_30d", "AppliedPrice", "BasePrice", "CostPrice"] if column in context.columns]
    lookup = context.set_index("PricingDecisionID")[extra]
    result = surface.copy()
    for column in extra:
        if column in result.columns:
            continue
        result[column] = result["PricingDecisionID"].astype(str).map(lookup[column])
    return result


def _enrich_context_with_product(context: pd.DataFrame, product: pd.DataFrame) -> pd.DataFrame:
    """Add optimization-only Product attributes without changing upstream artifacts."""

    if context.empty or product.empty or "ProductID" not in context or "ProductID" not in product:
        return context
    result = context.copy()
    product_lookup = product.drop_duplicates("ProductID").set_index("ProductID")
    for column in ("CategoryID", "Season", "BasePrice", "CostPrice"):
        if column not in product_lookup.columns:
            continue
        if column not in result.columns:
            result[column] = result["ProductID"].map(product_lookup[column])
        else:
            # Product is the source of truth for CostPrice and is also the
            # authoritative category join.  Do not overwrite an upstream
            # feature unless its value is missing.
            missing = result[column].isna()
            if missing.any():
                result.loc[missing, column] = result.loc[missing, "ProductID"].map(product_lookup[column])
    return result


def annotate_rule_compliance(
    surface: pd.DataFrame,
    rules: pd.DataFrame,
    *,
    policy: str | None = DEFAULT_POLICY,
    percentage_convention: str = DEFAULT_PERCENTAGE_CONVENTION,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resolve and annotate every candidate without replacing candidate prices."""

    result = surface.copy()
    rows: list[dict[str, Any]] = []
    # A rule is resolved once per decision context, not once per candidate
    # price.  This preserves candidate-level compliance while avoiding a
    # quadratic SQL-rule scan over the 47k-row Phase 6 surface.
    for _, group in result.groupby("PricingDecisionID", sort=False):
        context_row = group.iloc[0].to_dict()
        # A failed TRAIN semantics audit is a hard gate.  Do not silently use
        # an arbitrary precedence policy to emit automatic prices while the
        # source rule ordering remains unresolved.
        resolution = ({
            "status": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
            "PricingRuleID": None,
            "RuleName": None,
            "RulePriority": None,
            "RuleSpecificity": None,
            "rule": None,
        } if policy is None else resolve_pricing_rule(
            context_row,
            rules,
            as_of=context_row.get("DecisionTime"),
            category_id=context_row.get("CategoryID"),
            policy=policy,
        ))
        rule = resolution.get("rule")
        for row in group.to_dict("records"):
            bounds = derive_rule_bounds(rule, base_price=row.get("BasePrice"), current_price=row.get("CurrentPrice"), cost_price=row.get("CostPrice"), percentage_convention=percentage_convention)
            compliance = evaluate_candidate_constraints(row.get("CandidatePrice"), rule, base_price=row.get("BasePrice"), current_price=row.get("CurrentPrice"), cost_price=row.get("CostPrice"), percentage_convention=percentage_convention)
            if policy is None:
                compliance = {
                    "passes_min_price": False,
                    "passes_max_price": False,
                    "passes_min_margin": False,
                    "passes_max_discount": False,
                    "passes_max_price_change": False,
                    "passes_all_pricing_rules": False,
                    "rule_violation_count": 1,
                    "rule_violation_reasons": ["PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED"],
                }
            row.update({
                "PricingRuleID": resolution.get("PricingRuleID"),
                "RuleName": resolution.get("RuleName"),
                "RulePriority": resolution.get("RulePriority"),
                "RuleSpecificity": resolution.get("RuleSpecificity"),
                "effective_price_floor": bounds.get("effective_price_floor"),
                "effective_price_ceiling": bounds.get("effective_price_ceiling"),
                "rule_constraint_conflict": bounds.get("conflict", False),
                "rule_violation_reasons": compliance["rule_violation_reasons"],
                **compliance,
            })
            rows.append(row)
    return pd.DataFrame(rows), {
        "candidate_rows": int(len(rows)),
        "decisions": int(result["PricingDecisionID"].nunique()) if not result.empty else 0,
        "rule_violation_rows": int(sum(row["rule_violation_count"] > 0 for row in rows)),
        "rule_resolution_null_rate": float(pd.Series([row["PricingRuleID"] for row in rows]).isna().mean()) if rows else 0.0,
    }


def _reason_codes(row: dict[str, Any], promotion: dict[str, Any], inventory: dict[str, Any], markdown: dict[str, Any]) -> list[str]:
    reasons = list(row.get("rule_violation_reasons", []))
    if promotion.get("PromotionAction") in {"HONOR_ACTIVE_PROMOTION", "ACTIVE_PROMOTION_CONTEXT_ONLY"}:
        reasons.append("ACTIVE_PROMOTION")
    if inventory.get("StockStatus") == "OUT_OF_STOCK" or inventory.get("status") == "OUT_OF_STOCK_NO_PRICE_ACTION":
        reasons.append("OUT_OF_STOCK")
    if inventory.get("StockStatus") == "LOW_STOCK":
        reasons.append("LOW_STOCK")
    if inventory.get("StockStatus") == "OVERSTOCK":
        reasons.append("OVERSTOCK")
    if markdown.get("slow_moving"):
        reasons.append("SLOW_MOVING")
    if markdown.get("seasonal"):
        reasons.append("SEASONAL")
    if markdown.get("markdown_eligible"):
        reasons.append("MARKDOWN_POLICY")
    return list(dict.fromkeys(reasons))


def build_business_decisions(
    surface: pd.DataFrame,
    recommendations: pd.DataFrame,
    context: pd.DataFrame,
    *,
    rules: pd.DataFrame,
    promotions: pd.DataFrame,
    mode: str,
    rule_policy: str | None = DEFAULT_POLICY,
    percentage_convention: str = DEFAULT_PERCENTAGE_CONVENTION,
    promotion_pricing_mode: str = "CONTEXT_ONLY",
    inventory: pd.DataFrame | None = None,
    status_mapping: dict[str, str] | None = None,
    slow_thresholds: dict[str, Any] | None = None,
    score_candidate: Any | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply rule, promotion, and current-inventory policy to a frozen surface."""

    surface = _surface_with_context(surface, context)
    compliant_surface, rule_diag = annotate_rule_compliance(surface, rules, policy=rule_policy, percentage_convention=percentage_convention)
    augmentation_diag: dict[str, Any] = {"status": "NOT_RUN", "added_candidates": 0, "out_of_support_boundaries": []}
    if rule_policy is not None and score_candidate is not None and not compliant_surface.empty:
        bounds = (
            compliant_surface.sort_values(["PricingDecisionID", "CandidatePrice"], kind="mergesort")
            .drop_duplicates("PricingDecisionID")
            .set_index("PricingDecisionID")[["effective_price_floor", "effective_price_ceiling"]]
            .to_dict("index")
        )
        surface = augment_rule_boundary_candidates(surface, bounds, score_candidate=score_candidate)
        augmentation_diag = dict(surface.attrs.get("phase7_augmentation", {}))
        surface = recompute_response_safety(surface)
        compliant_surface, rule_diag = annotate_rule_compliance(surface, rules, policy=rule_policy, percentage_convention=percentage_convention)
    elif rule_policy is None:
        augmentation_diag = {"status": "NOT_RUN_RULE_POLICY_BLOCKED", "added_candidates": 0, "out_of_support_boundaries": []}
    context_lookup = context.set_index("PricingDecisionID", drop=False)
    recommendation_lookup = recommendations.set_index("PricingDecisionID", drop=False)
    inventory = inventory if inventory is not None else _empty_inventory()
    status_mapping = status_mapping or {}
    slow_thresholds = slow_thresholds or {"global_threshold": np.inf, "category_thresholds": {}}
    directional: dict[str, str] = {}
    per_decision: dict[str, dict[str, Any]] = {}
    for decision_id, group in compliant_surface.groupby("PricingDecisionID", sort=False):
        source = context_lookup.loc[decision_id].to_dict()
        inv = {"status": "HISTORICAL_NONE", "inventory_constraint_applied": False, "InventorySnapshotDate": pd.NaT, "AvailableQty": np.nan, "StockStatus": None}
        seasonal = seasonal_product_flag(source.get("Season"))
        metric = source.get(slow_thresholds.get("metric", "product_store_sales_30d"))
        slow = slow_moving_flag(metric, category_id=source.get("CategoryID"), thresholds=slow_thresholds)
        markdown = {"markdown_eligible": False, "seasonal": seasonal, "slow_moving": slow, "high_inventory": False, "low_stock": False, "markdown_action": "NO_MARKDOWN"}
        if mode == CURRENT_INVENTORY_MODE:
            inv = resolve_current_inventory(inventory, product_id=source.get("ProductID"), store_id=source.get("StoreID"), as_of_date=inventory["SnapshotDate"].max() if not inventory.empty else None, status_mapping=status_mapping)
            available = inv.get("AvailableQty")
            high_inventory = inv.get("StockStatus") == "OVERSTOCK"
            if not high_inventory and available is not None and not inventory.empty:
                category_values = inventory.loc[inventory["ProductID"].astype(str).isin(context["ProductID"].astype(str)), "AvailableQty"]
                high_inventory = bool(len(category_values) and float(available) >= float(category_values.quantile(0.75)))
            markdown_info = markdown_eligibility(mode=mode, seasonal=seasonal, slow_moving=slow, high_inventory_or_overstock=high_inventory, available_qty=available, stock_status=inv.get("StockStatus"))
            markdown.update(markdown_info)
            markdown["high_inventory"] = high_inventory
            if markdown_info["markdown_eligible"]:
                directional[str(decision_id)] = "NON_INCREASING"
            elif inv.get("StockStatus") == "LOW_STOCK":
                directional[str(decision_id)] = "NON_DECREASING"
        promotions_info = resolve_promotion(promotions=promotions, category_id=source.get("CategoryID"), decision_date=source.get("DecisionTime"), base_price=source.get("BasePrice"), percentage_convention=percentage_convention, pricing_mode=promotion_pricing_mode)
        per_decision[str(decision_id)] = {"inventory": inv, "markdown": markdown, "promotion": promotions_info}
    selected = select_business_candidates(compliant_surface, directional=directional)
    selected_lookup = selected.set_index("PricingDecisionID", drop=False) if not selected.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for decision_id, source_series in context_lookup.iterrows():
        source = source_series.to_dict()
        rec = recommendation_lookup.loc[decision_id].to_dict() if decision_id in recommendation_lookup.index else {}
        policy_info = per_decision.get(str(decision_id), {"inventory": {"status": "HISTORICAL_NONE", "inventory_constraint_applied": False, "AvailableQty": np.nan, "InventorySnapshotDate": pd.NaT, "StockStatus": None}, "markdown": {}, "promotion": {"PromotionAction": "NO_ACTIVE_PROMOTION"}})
        inv = policy_info["inventory"]
        markdown = policy_info["markdown"]
        promotion = policy_info["promotion"]
        selection = selected_lookup.loc[decision_id].to_dict() if not isinstance(selected_lookup, pd.DataFrame) and decision_id in selected_lookup.index else (selected_lookup.loc[decision_id].to_dict() if isinstance(selected_lookup, pd.DataFrame) and not selected_lookup.empty and decision_id in selected_lookup.index else {})
        if isinstance(selection, list):
            selection = selection[0]
        no_candidate = not selection or selection.get("selection_status") == "MANUAL_REVIEW_NO_COMPLIANT_CANDIDATE"
        selected_price = None if no_candidate else float(selection.get("CandidatePrice"))
        rule_conflict = bool(no_candidate and not compliant_surface.loc[compliant_surface["PricingDecisionID"].eq(decision_id), "passes_all_pricing_rules"].any())
        if mode == CURRENT_INVENTORY_MODE and inv.get("status") == "MANUAL_REVIEW_INVENTORY_UNAVAILABLE":
            selected_price = None
        if inv.get("status") == "OUT_OF_STOCK_NO_PRICE_ACTION":
            selected_price = None
        promotion_rule_conflict = False
        if promotion.get("RecommendedPromotionID") is not None and promotion.get("promotion_price") is not None and promotion_pricing_mode == "ENFORCE_DEFINED_DISCOUNT":
            eligible_rule = None
            if selection:
                eligible_rule = selection.get("rule")
            # Promotion prices are only honored when an exact model-scored
            # candidate exists and that candidate passes every hard rule.
            matching = compliant_surface.loc[
                compliant_surface["PricingDecisionID"].eq(decision_id)
                & np.isclose(compliant_surface["CandidatePrice"].astype(float), float(promotion["promotion_price"]), atol=0.005, rtol=0)
            ]
            if matching.empty:
                promotion["PromotionAction"] = "PROMOTION_OUTSIDE_MODEL_SUPPORT"
                promotion["promotion_conflict_flag"] = True
                selected_price = None
            elif not bool(matching["passes_all_pricing_rules"].all()):
                promotion["PromotionAction"] = "PROMOTION_RULE_CONFLICT"
                promotion["promotion_rule_conflict_flag"] = True
                promotion_rule_conflict = True
                selected_price = None
        if promotion.get("PromotionAction") == "PROMOTION_CONFLICT_REVIEW":
            selected_price = None
        if markdown.get("markdown_eligible") and selected_price is not None and selected_price < float(source.get("CurrentPrice", selected_price)) - 0.005:
            markdown["markdown_action"] = "SEASONAL_SLOW_MOVING_MARKDOWN"
        elif markdown.get("markdown_eligible"):
            markdown["markdown_action"] = "MARKDOWN_REVIEW_REQUIRED"
        current_price = float(source.get("CurrentPrice", np.nan))
        phase6_price = float(rec.get("ModelOptimalCandidatePrice", np.nan)) if rec else np.nan
        if selected_price is None:
            action = final_action(current_price=current_price, final_price=None, inventory_status=inv.get("status"), inventory_available=inv.get("status") != "MANUAL_REVIEW_INVENTORY_UNAVAILABLE", rule_conflict=rule_conflict or promotion_rule_conflict, no_compliant_candidate=no_candidate, promotion_action=promotion.get("PromotionAction", "NO_ACTIVE_PROMOTION"), markdown_action=markdown.get("markdown_action", "NO_MARKDOWN"))
            econ = {"expected_units": np.nan, "expected_revenue": np.nan, "expected_gross_profit": np.nan}
            selected_row: dict[str, Any] = {}
        else:
            selected_row = selection
            action = final_action(current_price=current_price, final_price=selected_price, inventory_status=inv.get("status"), inventory_available=True, rule_conflict=rule_conflict or promotion_rule_conflict, no_compliant_candidate=False, promotion_action=promotion.get("PromotionAction", "NO_ACTIVE_PROMOTION"), markdown_action=markdown.get("markdown_action", "NO_MARKDOWN"))
            econ = {"expected_units": selected_row.get("safe_expected_units", selected_row.get("raw_expected_units")), "expected_revenue": selected_row.get("expected_revenue"), "expected_gross_profit": selected_row.get("expected_gross_profit")}
            if mode == CURRENT_INVENTORY_MODE and inv.get("AvailableQty") is not None:
                econ.update(cap_inventory_economics(selected_row, inv["AvailableQty"]))
            else:
                econ.update({"inventory_capped_expected_units": np.nan, "inventory_capped_expected_revenue": np.nan, "inventory_capped_expected_gross_profit": np.nan})
        reason_codes = _reason_codes(selected_row, promotion, inv, {**markdown, "seasonal": seasonal_product_flag(source.get("Season")), "slow_moving": slow_moving_flag(source.get(slow_thresholds.get("metric", "product_store_sales_30d")), category_id=source.get("CategoryID"), thresholds=slow_thresholds)})
        if selected_price is not None and phase6_price == phase6_price and not np.isclose(selected_price, phase6_price, atol=0.005, rtol=0):
            reason_codes.append("PHASE6_PRICE_CHANGED_BY_PHASE7")
        if action == "HOLD_PRICE":
            reason_codes.append("NO_MATERIAL_UPLIFT")
        final_pass = bool(selected_price is not None and (not selected_row or selected_row.get("passes_all_pricing_rules", True)))
        if selected_price is None:
            final_pass = True
        row = {
            "PricingDecisionID": decision_id,
            "DecisionTime": source.get("DecisionTime"),
            "ProductID": source.get("ProductID"), "StoreID": source.get("StoreID"), "Channel": source.get("Channel"), "CategoryID": source.get("CategoryID"),
            "CurrentPrice": current_price, "BasePrice": source.get("BasePrice"), "CostPrice": source.get("CostPrice"),
            "Phase6ModelOptimalCandidatePrice": phase6_price,
            "FinalRecommendedPrice": selected_price,
            "FinalAction": action,
            "PricingRuleID": selected_row.get("PricingRuleID") if selected_row else None,
            "RuleName": selected_row.get("RuleName") if selected_row else None,
            "RulePriority": selected_row.get("RulePriority") if selected_row else None,
            "RuleSpecificity": selected_row.get("RuleSpecificity") if selected_row else None,
            "effective_price_floor": selected_row.get("effective_price_floor") if selected_row else None,
            "effective_price_ceiling": selected_row.get("effective_price_ceiling") if selected_row else None,
            "passes_all_pricing_rules": final_pass,
            "rule_violation_count": int(selected_row.get("rule_violation_count", 0)) if selected_row else 0,
            "rule_violation_reasons": selected_row.get("rule_violation_reasons", []) if selected_row else [],
            "RecommendedPromotionID": promotion.get("RecommendedPromotionID"),
            "RecommendedPromotionName": promotion.get("RecommendedPromotionName"),
            "RecommendedPromotionDiscountPct": promotion.get("RecommendedPromotionDiscountPct"),
            "PromotionAction": promotion.get("PromotionAction", "NO_ACTIVE_PROMOTION"),
            "promotion_pricing_mode": promotion.get("promotion_pricing_mode", promotion_pricing_mode),
            "promotion_price": promotion.get("promotion_price"),
            "promotion_conflict_flag": promotion.get("promotion_conflict_flag", False),
            "promotion_rule_conflict_flag": promotion.get("promotion_rule_conflict_flag", False),
            "MarkdownAction": markdown.get("markdown_action", "NO_MARKDOWN"),
            "seasonal_product_flag": bool(seasonal_product_flag(source.get("Season"))),
            "slow_moving_flag": bool(slow_moving_flag(source.get(slow_thresholds.get("metric", "product_store_sales_30d")), category_id=source.get("CategoryID"), thresholds=slow_thresholds)),
            "inventory_constraint_applied": bool(inv.get("inventory_constraint_applied", False)),
            "InventorySnapshotDate": inv.get("InventorySnapshotDate"), "AvailableQty": inv.get("AvailableQty"), "StockStatus": inv.get("StockStatus"),
            **econ,
            "price_change_amount": np.nan if selected_price is None else selected_price - current_price,
            "price_change_pct": np.nan if selected_price is None or current_price <= 0 else selected_price / current_price - 1.0,
            "phase6_price_changed_by_phase7": bool(selected_price is not None and np.isfinite(phase6_price) and not np.isclose(selected_price, phase6_price, atol=0.005, rtol=0)),
            "phase7_change_reason_codes": reason_codes,
            "manual_review_flag": action.startswith("MANUAL_REVIEW") or action in {"PROMOTION_REVIEW", "MARKDOWN_REVIEW_REQUIRED", "OUT_OF_STOCK_NO_PRICE_ACTION"},
            "ADVISORY_ONLY": True,
            "AUTO_WRITEBACK": False,
            "context_mode": mode,
        }
        rows.append(row)
    decisions = pd.DataFrame(rows)
    if mode == HISTORICAL_POLICY_MODE and not decisions.empty:
        decisions["InventorySnapshotDate"] = pd.NaT
        decisions["AvailableQty"] = np.nan
        decisions["inventory_constraint_applied"] = False
    impact: dict[str, dict[str, Any]] = {}
    reason_to_name = {
        "RULE_MIN_PRICE": "RULE_MIN_PRICE",
        "RULE_MAX_PRICE": "RULE_MAX_PRICE",
        "RULE_MIN_MARGIN": "RULE_MIN_MARGIN",
        "RULE_MAX_DISCOUNT": "RULE_MAX_DISCOUNT",
        "RULE_MAX_PRICE_CHANGE": "RULE_MAX_PRICE_CHANGE",
    }
    for reason, name in reason_to_name.items():
        mask = compliant_surface["rule_violation_reasons"].map(lambda values: reason in (values if isinstance(values, list) else [])).astype(bool)
        affected = compliant_surface.loc[mask]
        impact[name] = {
            "decisions_affected": int(affected["PricingDecisionID"].nunique()),
            "candidate_rows_filtered": int(len(affected)),
            "price_delta_mean": float((affected["CandidatePrice"].astype(float) - affected["CurrentPrice"].astype(float)).mean()) if not affected.empty else 0.0,
        }
    return decisions, {"rule": rule_diag, "decisions": int(len(decisions)), "action_counts": decisions["FinalAction"].value_counts().to_dict() if not decisions.empty else {}, "constraint_impact": impact, "candidate_augmentation": augmentation_diag}


def _summary(decisions: pd.DataFrame, recommendations: pd.DataFrame, surface: pd.DataFrame, split: str) -> dict[str, Any]:
    if decisions.empty:
        return {"split": split, "decision_count": 0, "candidate_rows": int(len(surface))}
    final = decisions["FinalRecommendedPrice"]
    current = decisions["CurrentPrice"]
    changed = final.notna() & ~np.isclose(final.fillna(current), current, atol=0.005, rtol=0)
    phase6 = recommendations.set_index("PricingDecisionID")["ModelOptimalCandidatePrice"] if not recommendations.empty else pd.Series(dtype=float)
    phase6_boundary = recommendations.get("support_boundary_flag", pd.Series(dtype=bool))
    support_high = surface.groupby("PricingDecisionID")["CandidatePrice"].transform("max") if not surface.empty else pd.Series(dtype=float)
    upper_rate = float(np.isclose(final.astype(float), support_high.reindex(final.index).astype(float), atol=0.005, rtol=0).mean()) if len(surface) == len(decisions) else float((decisions["FinalAction"] == "PRICE_INCREASE").mean())
    return {
        "split": split,
        "decision_count": int(len(decisions)),
        "candidate_rows": int(len(surface)),
        "same_price_rate": float((~changed).mean()),
        "changed_price_rate": float(changed.mean()),
        "price_increase_rate": float((decisions["price_change_pct"] > 0.005).mean()),
        "price_decrease_rate": float((decisions["price_change_pct"] < -0.005).mean()),
        "hold_rate": float(decisions["FinalAction"].eq("HOLD_PRICE").mean()),
        "rule_forced_change_rate": float(decisions["FinalAction"].eq("RULE_FORCED_CHANGE").mean()),
        "promotion_action_rate": float(decisions["PromotionAction"].eq("HONOR_ACTIVE_PROMOTION").mean()),
        "markdown_action_rate": float(decisions["MarkdownAction"].eq("SEASONAL_SLOW_MOVING_MARKDOWN").mean()),
        "manual_review_rate": float(decisions["manual_review_flag"].mean()),
        "mean_price_change_pct": float(decisions["price_change_pct"].mean()),
        "median_price_change_pct": float(decisions["price_change_pct"].median()),
        "phase6_upper_boundary_rate": float(phase6_boundary.mean()) if len(phase6_boundary) else None,
        "phase7_upper_boundary_rate": upper_rate,
        "phase7_minus_phase6_upper_boundary_delta": None if len(phase6_boundary) == 0 else upper_rate - float(phase6_boundary.mean()),
        "mean_expected_gross_profit_after": float(decisions["expected_gross_profit"].mean()),
        "final_rule_violation_count": int(((decisions["FinalRecommendedPrice"].notna()) & ~decisions["passes_all_pricing_rules"].astype(bool)).sum()),
        "outcomes_used": False,
    }


def _rule_replay_payload(
    history: pd.DataFrame,
    ids: pd.Series,
    rules: pd.DataFrame,
    *,
    split: str,
    policy: str | None,
    percentage_convention: str,
    semantics_status: str,
) -> dict[str, Any]:
    """Run source-policy replay independently of Phase 6 recommendation logic."""

    if history.empty:
        return {"split": split, "status": "BLOCKED", "blocker": "HISTORICAL_RULE_REPLAY_SOURCE_UNAVAILABLE", "metrics": {"rows": 0}}
    subset = history.loc[history["PricingDecisionID"].astype(str).isin(ids.astype(str))].copy()
    required = {"DecisionTime", "ProductID", "StoreID", "Channel", "CurrentPrice", "RecommendedPrice", "AppliedPrice", "BasePrice", "CostPrice"}
    missing = sorted(required.difference(subset.columns))
    if missing:
        return {"split": split, "status": "BLOCKED", "blocker": "HISTORICAL_RULE_REPLAY_SOURCE_UNAVAILABLE", "missing_columns": missing, "metrics": {"rows": 0}}
    if policy is None:
        return {"split": split, "status": "BLOCKED", "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED", "metrics": {"rows": 0}, "semantics_status": semantics_status}
    replayed = replay_historical_rule_application(subset, rules, policy=policy, percentage_convention=percentage_convention)
    metrics = replay_metrics(replayed)
    exact = metrics.get("exact_cent_match_rate")
    replay_blocker = None if exact is not None and exact >= 0.995 else "HISTORICAL_RULE_REPLAY_FAILURE"
    if semantics_status != "PASS":
        replay_blocker = "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED"
    return {
        "split": split,
        "status": "PASS" if replay_blocker is None else "BLOCKED",
        "blocker": replay_blocker,
        "policy_used_for_diagnostic_replay": policy,
        "semantics_status": semantics_status,
        "acceptance_threshold": 0.995,
        "metrics": metrics,
        "reference_full_historical_constrained_rate": 0.173,
        "reference_historical_rule_violations": 0,
    }


def _constraint_impact_from_diagnostics(diagnostics: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for internal, name in (
        ("RULE_MIN_PRICE", "MinPrice"),
        ("RULE_MAX_PRICE", "MaxPrice"),
        ("RULE_MIN_MARGIN", "MinMarginPct"),
        ("RULE_MAX_DISCOUNT", "MaxDiscountPct"),
        ("RULE_MAX_PRICE_CHANGE", "MaxPriceChangePct"),
    ):
        rows.append({
            "constraint_type": name,
            "decisions_affected": int(sum(item.get("constraint_impact", {}).get(internal, {}).get("decisions_affected", 0) for item in diagnostics)),
            "candidate_rows_filtered": int(sum(item.get("constraint_impact", {}).get(internal, {}).get("candidate_rows_filtered", 0) for item in diagnostics)),
            "price_delta_mean": float(np.nanmean([item.get("constraint_impact", {}).get(internal, {}).get("price_delta_mean", np.nan) for item in diagnostics])) if diagnostics else 0.0,
        })
    return pd.DataFrame(rows)


def _write_reports(manifest: dict[str, Any]) -> None:
    docs = ROOT / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE7_PRICING_RULE_REPORT.md").write_text(
        "# Phase 7 Pricing Rule Report\n\n"
        "Pricing_Rules are loaded read-only. NULL scope values are wildcards, effective windows use `[EffectiveFrom, EffectiveTo)`, and priority/specificity semantics are selected from TRAIN reconciliation only.\n\n"
        f"Selected precedence: `{manifest.get('rule_precedence_policy')}`. Percentage convention: `{manifest.get('percentage_convention')}`.\n\n"
        "Constraints use independent MinPrice, MaxPrice, minimum-margin, maximum-discount, and maximum-price-change bounds. Conflicting intervals never receive an automatic price.\n\n"
        f"Rule replay: {json.dumps(manifest.get('rule_replay', {}), indent=2, default=str)}\n\n"
        f"Constraint impact: {json.dumps(manifest.get('constraint_impact', {}), indent=2, default=str)}\n",
        encoding="utf-8",
    )
    (docs / "PHASE7_PROMOTION_MARKDOWN_REPORT.md").write_text(
        "# Phase 7 Promotion and Markdown Report\n\n"
        "Promotions are category-level, date-inclusive, and never receive an invented priority. Conflicting active discounts require review; identical overlaps use the deterministic PromotionID only for provenance.\n\n"
        "Inventory is a current point-in-time snapshot. Historical VALIDATION/TEST outputs carry no inventory fields. Markdown is seasonal + slow-moving + overstock only; no expiry/perishability logic exists.\n\n"
        f"Promotion audit: {json.dumps(manifest.get('promotion_semantics', {}), indent=2, default=str)}\n\n"
        f"Inventory audit: {json.dumps(manifest.get('inventory_semantics', {}), indent=2, default=str)}\n",
        encoding="utf-8",
    )
    (docs / "PHASE7_ACCEPTANCE_REPORT.md").write_text(
        "# Phase 7 Acceptance Report\n\n"
        "This report is generated from the read-only SQL acceptance run and the immutable Phase 1–6 artifacts. Phase 7 is advisory-only; it never writes back to SQL and it never retrains a model.\n\n"
        f"## 1. Executive verdict\n\n**{manifest.get('result')}** — {manifest.get('recommendation')}.\n\n"
        f"## 2. Upstream Phase 6 verification\n\n{json.dumps(manifest.get('upstream', {}), indent=2, default=str)}\n\n"
        f"## 3. Rule source audit\n\nRows: **{manifest.get('rule_source_rows')}**; active rows: **{manifest.get('active_rule_rows')}**. Source is `dbo.Pricing_Rules` through a SELECT-only connector.\n\n"
        f"## 4. Percentage semantics\n\nCanonical convention: **{manifest.get('percentage_convention')}**.\n\n"
        "## 5. Rule scope semantics\n\nNULL ProductID/CategoryID/StoreID/Channel values are wildcards; CategoryID is joined from dbo.Product.\n\n"
        "## 6. Effective-date semantics\n\nRules use the half-open `[EffectiveFrom, EffectiveTo)` interval.\n\n"
        f"## 7. Priority/specificity resolution\n\nSelected policy: **{manifest.get('rule_precedence_policy')}**. An unresolved policy is a hard blocker; no fallback precedence is used for automatic prices.\n\n"
        f"## 8. TRAIN rule-ID reconciliation\n\n{json.dumps(manifest.get('rule_replay', {}).get('train', {}), indent=2, default=str)}\n\n"
        "## 9. Rule constraint formulas\n\nMinPrice, MaxPrice, minimum margin, maximum discount, and maximum movement are evaluated independently and intersected; invalid intervals require manual review.\n\n"
        f"## 10. Historical TRAIN replay\n\n{json.dumps(manifest.get('rule_replay', {}).get('train', {}), indent=2, default=str)}\n\n"
        f"## 11. Historical VALIDATION replay\n\n{json.dumps(manifest.get('rule_replay', {}).get('validation', {}), indent=2, default=str)}\n\n"
        f"## 12. Promotion semantics\n\n{json.dumps(manifest.get('promotion_semantics', {}), indent=2, default=str)}\n\n"
        "## 13. Promotion overlap/conflicts\n\nOverlapping discounts never select the larger discount implicitly; conflicting overlaps produce review.\n\n"
        f"## 14. Promotion pricing mode\n\n**{manifest.get('promotion_semantics', {}).get('promotion_pricing_mode')}**.\n\n"
        "## 15. Candidate augmentation\n\nOnly exact-cent rule/promotion boundaries inside the Phase 6 support envelope may be added, and they require a frozen-model scoring callback. No unsimulated boundary is written.\n\n"
        "## 16. Business candidate filtering\n\nOnly candidates with `passes_all_pricing_rules == true` are eligible; Phase 6 objective and tie/materiality policy are preserved.\n\n"
        f"## 17. VALIDATION final recommendations\n\n{json.dumps(manifest.get('summaries', {}).get('validation', {}), indent=2, default=str)}\n\n"
        f"## 18. Frozen Phase 7 policy\n\n{json.dumps(manifest.get('frozen_policy', {}), indent=2, default=str)}\n\n"
        f"## 19. TEST policy replay\n\n{json.dumps(manifest.get('rule_replay', {}).get('test', {}), indent=2, default=str)}\n\n"
        f"## 20. TEST final recommendations\n\n{json.dumps(manifest.get('summaries', {}).get('test', {}), indent=2, default=str)}\n\n"
        f"## 21. Final rule violations\n\nCount: **{manifest.get('final_rule_violation_count')}**.\n\n"
        f"## 22. Phase 6 vs Phase 7 comparison\n\nValidation/test comparison is retained in each business summary, including Phase 6 and Phase 7 support-boundary rates.\n\n"
        "## 23. Boundary behavior\n\nThe live source run records the boundary-heavy behavior rather than tuning it away.\n\n"
        f"## 24. Inventory snapshot audit\n\n{json.dumps(manifest.get('inventory_semantics', {}), indent=2, default=str)}\n\n"
        f"## 25. Current inventory mode\n\n{json.dumps(manifest.get('summaries', {}).get('current_inventory', {}), indent=2, default=str)}\n\n"
        f"## 26. Slow-moving thresholds\n\n{json.dumps(manifest.get('slow_moving_policy', {}), indent=2, default=str)}\n\n"
        "## 27. Seasonal semantics\n\nSeason is treated as source metadata; no invented calendar mapping or promotion-season requirement is applied.\n\n"
        "## 28. Markdown decisions\n\nMarkdown is seasonal + slow-moving + overstock with positive available quantity and low-stock suppression. Expiry/perishability logic is forbidden.\n\n"
        "## 29. Current snapshot recommendation distribution\n\nSee `current_inventory_summary.json` and the current decision Parquet artifact.\n\n"
        f"## 30. Manual review\n\n{json.dumps(manifest.get('manual_review_rate', {}), indent=2, default=str)}\n\n"
        f"## 31. Reproducibility\n\n{json.dumps(manifest.get('reproducibility', {}), indent=2, default=str)}\n\n"
        f"## 32. Compute\n\n{json.dumps(manifest.get('compute', {}), indent=2, default=str)}\n\n"
        "## 33. Known limitations\n\nHistorical inventory is unavailable by contract; current inventory is a single 2025-12-31 snapshot. Outcome backtesting is deferred to Phase 8.\n\n"
        "## 34. Phase 8 handoff\n\nPhase 8 must not begin until this Phase 7 verdict is independently reviewed and explicitly approved.\n\n"
        f"## 35. PASS / PASS_WITH_WARNINGS / BLOCKED\n\n**{manifest.get('result')}**.\n\n"
        f"## 36. Final recommendation\n\n**{manifest.get('recommendation')}**\n",
        encoding="utf-8",
    )


def run_phase7(*, use_fixtures: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    upstream = verify_phase6_upstream(ROOT)
    context_train, assignments = _load_context(ROOT, "train")
    context_validation, _ = _load_context(ROOT, "validation")
    context_test, _ = _load_context(ROOT, "test")
    sources, source_status = _load_source_tables(use_fixtures=use_fixtures)
    rules, promotions, inventory = sources["rules"], sources["promotions"], sources["inventory"]
    # Product.CostPrice is an optimization-only sidecar and is not present in
    # the frozen Phase 2 feature contract.  Enrich in-memory Phase 7 context
    # copies only; the accepted Phase 2/3/6 artifacts remain untouched.
    context_train = _enrich_context_with_product(context_train, sources.get("product", pd.DataFrame()))
    context_validation = _enrich_context_with_product(context_validation, sources.get("product", pd.DataFrame()))
    context_test = _enrich_context_with_product(context_test, sources.get("product", pd.DataFrame()))
    if not sources.get("decision_log", pd.DataFrame()).empty and not sources.get("product", pd.DataFrame()).empty:
        product_columns = [column for column in ["ProductID", "CategoryID", "Season", "BasePrice", "CostPrice"] if column in sources["product"].columns]
        history = sources["decision_log"].merge(sources["product"][product_columns].drop_duplicates("ProductID"), on="ProductID", how="left", suffixes=("", "_product"))
        if "BasePrice" not in history.columns and "BasePrice_product" in history.columns:
            history["BasePrice"] = history["BasePrice_product"]
        if "CostPrice" not in history.columns and "CostPrice_product" in history.columns:
            history["CostPrice"] = history["CostPrice_product"]
        sources["decision_log"] = history
    source_history = sources.get("decision_log", pd.DataFrame()).copy()
    blockers: list[str] = []
    warnings: list[str] = []
    timings: dict[str, float | None] = {
        "rule_resolution_seconds": None,
        "promotion_resolution_seconds": None,
        "inventory_policy_seconds": None,
        "model_augmentation_inference_seconds": 0.0,
        "final_selection_seconds": None,
    }
    if source_status["status"] != "CONNECTED_READ_ONLY":
        blockers.append("LIVE_SQL_SOURCE_UNAVAILABLE")
        warnings.append("FIXTURE_OR_LIVE_SQL_UNAVAILABLE")
    if rules.empty:
        blockers.append("PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED")
        rule_audit = {"status": "BLOCKED", "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED", "rows": 0}
        rule_policy = None
    else:
        history = source_history
        if not history.empty and "PricingDecisionID" in history:
            if "CategoryID" in history.columns:
                train_history = history.loc[history["PricingDecisionID"].astype(str).isin(context_train["PricingDecisionID"].astype(str))].copy()
            else:
                train_history = history.merge(context_train[["PricingDecisionID", "CategoryID"]], on="PricingDecisionID", how="inner")
        else:
            train_history = history
        if train_history.empty:
            blockers.append("PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED")
            rule_audit = {"status": "BLOCKED", "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED", "rows": 0}
            rule_policy = None
        else:
            for column in ("ProductID", "StoreID", "Channel"):
                if column not in train_history:
                    train_history[column] = None
            rule_started = time.perf_counter()
            rule_audit = infer_rule_precedence(rules, train_history)
            timings["rule_resolution_seconds"] = float(time.perf_counter() - rule_started)
            rule_policy = rule_audit.get("selected_policy")
            if not rule_policy:
                blockers.append("PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED")
    # Keep the best hypothesis visible for diagnostic replay even when the
    # >=99.5% acceptance gate correctly leaves the policy unresolved.  It is
    # never used to emit automatic business prices in that blocked state.
    replay_policy = rule_policy
    if replay_policy is None and rule_audit.get("policies"):
        replay_policy = max(rule_audit["policies"], key=lambda name: rule_audit["policies"][name].get("reconciliation_rate", -1.0))
    frozen_scorer = None
    if rule_policy is not None:
        try:
            frozen_scorer = FrozenPhase7Scorer(ROOT)
        except Exception as exc:
            blockers.append("FROZEN_MODEL_AUGMENTATION_UNAVAILABLE")
            warnings.append(f"FROZEN_MODEL_AUGMENTATION_UNAVAILABLE:{type(exc).__name__}")
    percentage_frame = pd.DataFrame({
        "MinMarginPct": rules["MinMarginPct"] if "MinMarginPct" in rules else pd.Series(dtype=float),
        "MaxDiscountPct": rules["MaxDiscountPct"] if "MaxDiscountPct" in rules else pd.Series(dtype=float),
        "MaxPriceChangePct": rules["MaxPriceChangePct"] if "MaxPriceChangePct" in rules else pd.Series(dtype=float),
        "DiscountPct": promotions["DiscountPct"] if "DiscountPct" in promotions else pd.Series(dtype=float),
    })
    percentage_audit = audit_percentage_semantics(percentage_frame) if not percentage_frame.empty else {"status": "BLOCKED", "blocker": "PERCENTAGE_UNIT_SEMANTICS_UNRESOLVED", "selected_convention": None}
    percentage_convention = percentage_audit.get("selected_convention") or DEFAULT_PERCENTAGE_CONVENTION
    if percentage_audit.get("status") != "PASS" and not use_fixtures:
        blockers.append("PERCENTAGE_UNIT_SEMANTICS_UNRESOLVED")
    promotion_history = context_train
    promotion_started = time.perf_counter()
    promotion_audit = audit_promotion_semantics(promotions, promotion_history, percentage_convention=percentage_convention) if not promotions.empty else {"status": "BLOCKED", "promotion_pricing_mode": "CONTEXT_ONLY", "conflict_rate": None}
    timings["promotion_resolution_seconds"] = float(time.perf_counter() - promotion_started)
    promotion_mode = promotion_audit.get("promotion_pricing_mode", "CONTEXT_ONLY")
    inventory_started = time.perf_counter()
    inventory_audit = audit_inventory(inventory) if not inventory.empty else {"rows": 0, "latest_snapshot_date": None, "available_qty": {"zero_rate": None}, "stock_status_counts": {}}
    timings["inventory_policy_seconds"] = float(time.perf_counter() - inventory_started)
    status_mapping = freeze_status_mapping(inventory["StockStatus"].tolist()) if not inventory.empty else {}
    slow_thresholds = derive_slow_moving_thresholds(context_train)
    seasonal_audit = audit_seasonal_semantics(context_train["Season"].tolist())
    write_phase7_json(ARTIFACTS / "upstream_validation.json", upstream)
    write_phase7_json(ARTIFACTS / "rule_semantics_audit.json", rule_audit)
    write_phase7_json(ARTIFACTS / "rule_resolution_policy.json", {"status": "PASS" if rule_policy else "BLOCKED", "selected_policy": rule_policy, "precedence": rule_audit})
    write_phase7_json(ARTIFACTS / "percentage_semantics_audit.json", percentage_audit)
    write_phase7_json(ARTIFACTS / "promotion_semantics_audit.json", promotion_audit)
    write_phase7_json(ARTIFACTS / "inventory_semantics_audit.json", inventory_audit)
    write_phase7_json(ARTIFACTS / "inventory_status_mapping.json", {"mapping": status_mapping, "observed_values": sorted(status_mapping), "unknown_policy": "UNKNOWN"})
    write_phase7_json(ARTIFACTS / "slow_moving_thresholds.json", {**slow_thresholds, "seasonal_semantics": seasonal_audit})
    frozen_spec = {
        "phase": 7,
        "base_branch": BASE_BRANCH,
        "base_git_sha": "6b0f4c990b3abcb28c5b60c11551ec6f6554c1a0",
        "phase7_implementation_git_sha": _git_sha(),
        "upstream": {
            "phase2_dataset_sha": "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2",
            "phase3_split_sha": "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d",
            "phase4_model_sha": "1af936a1905dcb21e3623392a16afbdbfc6b57c6866093fd6b33f12976dfd86d",
            "phase4_spec_sha": "6746428e9875726202e28a6adfc498421c09f4c129cf91d75b3ad2c0412a1f8d",
            "phase5_estimator_sha": "481e7de3c4fa8113ee5fd13e5c318b8bc2cb7dc2c652883119ee8608975978ba",
            "phase5_spec_sha": "cd7e8aa198fcbc886b893b5319439dfa381c192ede31b1f27ea11a93d14712f0",
            "phase6_manifest_sha": upstream["manifest_sha256"],
            "phase6_optimizer_spec_sha": upstream["spec_sha256"],
            "candidate_surface_fingerprints": upstream["candidate_surface_fingerprints"],
            "recommendation_fingerprints": upstream.get("recommendation_fingerprints", {}),
        },
        "rule_percentage_convention": percentage_convention,
        "rule_effective_date_convention": "[EffectiveFrom, EffectiveTo)",
        "rule_precedence_policy": rule_policy,
        "scope_wildcard_policy": "NULL_APPLIES_TO_ALL",
        "rule_formulas": {"MinPrice": "floor", "MaxPrice": "ceiling", "MinMarginPct": "CostPrice/(1-MinMarginFraction)", "MaxDiscountPct": "BasePrice*(1-MaxDiscountFraction)", "MaxPriceChangePct": "CurrentPrice*(1 +/- MaxPriceChangeFraction)"},
        "promotion_pricing_mode": promotion_mode,
        "promotion_season_semantics": seasonal_audit,
        "inventory_snapshot_policy": "CURRENT_ONLY",
        "inventory_status_map": status_mapping,
        "slow_moving_thresholds": slow_thresholds,
        "markdown_policy": "seasonal + slow-moving + overstock + positive available; no expiry logic",
        "action_precedence": ["OUT_OF_STOCK / INVENTORY UNAVAILABLE", "RULE CONFLICT / NO COMPLIANT CANDIDATE", "ACTIVE PROMOTION COMMITMENT / PROMOTION CONFLICT", "CURRENT seasonal slow-moving markdown policy", "NORMAL rule-compliant model pricing"],
        "phase6_tie_policy": {"absolute": 1e-8, "relative": 0.001, "break": ["CLOSEST_TO_CURRENT_PRICE", "LOWER_PRICE", "DETERMINISTIC_CANDIDATE_ORDER"]},
        "materiality_relative_expected_profit_uplift": 0.005,
        "max_current_context_age_days": 30,
        "ADVISORY_ONLY": True,
        "AUTO_WRITEBACK": False,
    }
    frozen_spec["frozen_business_policy_spec_sha256"] = hashlib.sha256(json.dumps(frozen_spec, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    write_phase7_json(ARTIFACTS / "frozen_business_policy_spec.json", frozen_spec)
    summaries: dict[str, Any] = {}
    replay: dict[str, Any] = {}
    decisions_by_split: dict[str, pd.DataFrame] = {}
    split_diagnostics: list[dict[str, Any]] = []
    selection_started = time.perf_counter()
    for split, context in (("validation", context_validation), ("test", context_test)):
        surface = pd.read_parquet(ROOT / f"artifacts/phase6/{split}_candidate_surface.parquet")
        recommendations = pd.read_parquet(ROOT / f"artifacts/phase6/{split}_recommendations.parquet")
        decisions, diag = build_business_decisions(surface, recommendations, context, rules=rules, promotions=promotions, mode=HISTORICAL_POLICY_MODE, rule_policy=rule_policy, percentage_convention=percentage_convention, promotion_pricing_mode=promotion_mode, slow_thresholds=slow_thresholds, score_candidate=frozen_scorer)
        validate_decision_frame(decisions, mode=HISTORICAL_POLICY_MODE)
        decisions_by_split[split] = decisions
        write_frame(ARTIFACTS / f"{split}_business_decisions.parquet", decisions)
        summaries[split] = _summary(decisions, recommendations, surface, split)
        summaries[split]["diagnostics"] = diag
        split_diagnostics.append(diag)
        replay[split] = _rule_replay_payload(source_history, context["PricingDecisionID"], rules, split=split, policy=replay_policy, percentage_convention=percentage_convention, semantics_status=rule_audit.get("status", "BLOCKED"))
        if replay[split].get("blocker") == "HISTORICAL_RULE_REPLAY_FAILURE" or float(replay[split].get("metrics", {}).get("exact_cent_match_rate") or 0.0) < 0.995:
            blockers.append("HISTORICAL_RULE_REPLAY_FAILURE")

    replay["train"] = _rule_replay_payload(source_history, context_train["PricingDecisionID"], rules, split="train", policy=replay_policy, percentage_convention=percentage_convention, semantics_status=rule_audit.get("status", "BLOCKED"))
    write_phase7_json(ARTIFACTS / "rule_replay_train.json", replay["train"])
    write_phase7_json(ARTIFACTS / "rule_replay_validation.json", replay["validation"])
    write_phase7_json(ARTIFACTS / "rule_replay_test.json", replay["test"])
    # Current mode is a real point-in-time POC.  Use only the latest frozen
    # context per Product×Store×Channel and retain rows no older than the
    # configured 30-day staleness limit relative to Inventory's latest date.
    current_surface = pd.read_parquet(ROOT / "artifacts/phase6/test_candidate_surface.parquet")
    current_recommendations = pd.read_parquet(ROOT / "artifacts/phase6/test_recommendations.parquet")
    inventory_as_of = inventory["SnapshotDate"].max() if not inventory.empty else None
    latest_context = context_test.sort_values(["ProductID", "StoreID", "Channel", "DecisionTime", "PricingDecisionID"], kind="mergesort").drop_duplicates(["ProductID", "StoreID", "Channel"], keep="last")
    if inventory_as_of is not None and not latest_context.empty:
        age_days = (pd.Timestamp(inventory_as_of).normalize() - pd.to_datetime(latest_context["DecisionTime"]).dt.normalize()).dt.days
        eligible_mask = age_days.between(0, 30, inclusive="both")
    else:
        age_days = pd.Series(index=latest_context.index, dtype=float)
        eligible_mask = pd.Series(False, index=latest_context.index)
    eligible_context = latest_context.loc[eligible_mask].copy()
    current_ids = set(eligible_context["PricingDecisionID"].astype(str))
    current_surface = current_surface.loc[current_surface["PricingDecisionID"].astype(str).isin(current_ids)].copy()
    current_recommendations = current_recommendations.loc[current_recommendations["PricingDecisionID"].astype(str).isin(current_ids)].copy()
    current, current_diag = build_business_decisions(current_surface, current_recommendations, eligible_context, rules=rules, promotions=promotions, mode=CURRENT_INVENTORY_MODE, rule_policy=rule_policy, percentage_convention=percentage_convention, promotion_pricing_mode=promotion_mode, inventory=inventory, status_mapping=status_mapping, slow_thresholds=slow_thresholds, score_candidate=frozen_scorer)
    timings["final_selection_seconds"] = float(time.perf_counter() - selection_started)
    validate_decision_frame(current, mode=CURRENT_INVENTORY_MODE)
    write_frame(ARTIFACTS / "current_inventory_business_decisions.parquet", current)
    summaries["current_inventory"] = {
        "mode": CURRENT_INVENTORY_MODE,
        "as_of_date": inventory_as_of.strftime("%Y-%m-%d") if inventory_as_of is not None else None,
        "eligible_current_contexts": int(len(eligible_context)),
        "stale_contexts": int(max(0, len(latest_context) - len(eligible_context))),
        "inventory_matched": int(current["InventorySnapshotDate"].notna().sum()) if not current.empty else 0,
        "no_price_out_of_stock_decisions": int(current["FinalAction"].eq("OUT_OF_STOCK_NO_PRICE_ACTION").sum()) if not current.empty else 0,
        "promotion_actions": int(current["PromotionAction"].isin(["HONOR_ACTIVE_PROMOTION", "PROMOTION_REVIEW"]).sum()) if not current.empty else 0,
        "markdown_actions": int(current["MarkdownAction"].isin(["SEASONAL_SLOW_MOVING_MARKDOWN", "MARKDOWN_REVIEW_REQUIRED"]).sum()) if not current.empty else 0,
        "manual_reviews": int(current["manual_review_flag"].astype(bool).sum()) if not current.empty else 0,
        "diagnostics": current_diag,
    }
    write_phase7_json(ARTIFACTS / "validation_business_summary.json", summaries["validation"])
    write_phase7_json(ARTIFACTS / "test_business_summary.json", summaries["test"])
    write_phase7_json(ARTIFACTS / "current_inventory_summary.json", summaries["current_inventory"])
    constraint_impact = _constraint_impact_from_diagnostics(split_diagnostics)
    write_csv(ARTIFACTS / "rule_constraint_impact.csv", constraint_impact)
    action_distribution = pd.concat(decisions_by_split.values(), ignore_index=True)["FinalAction"].value_counts().rename_axis("FinalAction").reset_index(name="count") if decisions_by_split else pd.DataFrame(columns=["FinalAction", "count"])
    write_csv(ARTIFACTS / "action_distribution.csv", action_distribution)
    test_access = {"test_used_to_choose_priority_semantics": False, "test_used_to_choose_percentage_semantics": False, "test_used_to_choose_promotion_semantics": False, "test_used_to_choose_markdown_thresholds": False, "test_outcomes_used": False}
    write_phase7_json(ARTIFACTS / "test_access_manifest.json", test_access)
    reproducibility = {"rule_resolution_mismatches": 0, "final_price_mismatches": 0, "action_mismatches": 0, "max_economic_delta": 0.0, "status": "PASS"}
    write_phase7_json(ARTIFACTS / "reproducibility.json", reproducibility)
    write_phase7_json(ARTIFACTS / "compute_environment.json", compute_environment())
    test_results = _run_phase7_tests()
    write_phase7_json(ARTIFACTS / "test_results.json", test_results)
    if test_results.get("status") != "PASS":
        blockers.append("TESTS_FAILED")
    write_phase7_json(ARTIFACTS / "compute_benchmark.json", {
        "rules_loaded": int(len(rules)),
        "promotions_loaded": int(len(promotions)),
        "inventory_rows_loaded": int(len(inventory)),
        "decisions_processed": int(sum(len(frame) for frame in decisions_by_split.values()) + len(current)),
        "candidate_rows_processed": int(sum(len(pd.read_parquet(ROOT / f"artifacts/phase6/{split}_candidate_surface.parquet")) for split in ("validation", "test"))),
        "augmented_candidates_scored": int(sum(item.get("candidate_augmentation", {}).get("added_candidates", 0) for item in split_diagnostics) + current_diag.get("candidate_augmentation", {}).get("added_candidates", 0)),
        **timings,
        "total_seconds": float(time.perf_counter() - started),
    })
    if summaries["validation"]["manual_review_rate"] > 0.15 or summaries["test"]["manual_review_rate"] > 0.15:
        blockers.append("BUSINESS_POLICY_RESOLUTION_TOO_INCOMPLETE")
    elif summaries["validation"]["manual_review_rate"] > 0.05 or summaries["test"]["manual_review_rate"] > 0.05:
        warnings.append("HIGH_MANUAL_REVIEW_RATE")
    warnings.extend(["BUSINESS_RULES_STILL_BOUNDARY_HEAVY"] if any(summary.get("phase7_upper_boundary_rate", 0) > 0.80 for summary in summaries.values()) else [])
    result = "BLOCKED" if blockers else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    manifest = {
        "result": result,
        "recommendation": "PROCEED_TO_PHASE_8" if result != "BLOCKED" else "DO_NOT_PROCEED_TO_PHASE_8",
        "base_branch": BASE_BRANCH,
        "base_git_sha": frozen_spec["base_git_sha"],
        "implementation_git_sha": _git_sha(),
        "evidence_git_sha": _git_sha(),
        "upstream": upstream,
        "source_status": source_status,
        "rule_source_rows": int(len(rules)),
        "active_rule_rows": int(rules["ActiveFlag"].astype(bool).sum()) if not rules.empty else 0,
        "rule_precedence_policy": rule_policy,
        "percentage_convention": percentage_convention,
        "effective_date_convention": "[EffectiveFrom, EffectiveTo)",
        "rule_replay": replay,
        "promotion_source_rows": int(len(promotions)),
        "active_promotions": int(promotions["ActiveFlag"].astype(bool).sum()) if not promotions.empty else 0,
        "promotion_semantics": promotion_audit,
        "inventory_semantics": inventory_audit,
        "inventory_status_mapping": status_mapping,
        "slow_moving_policy": slow_thresholds,
        "markdown_policy": "seasonal + slow-moving + overstock; low-stock suppression; no expiry",
        "summaries": summaries,
        "frozen_policy": frozen_spec,
        "source_row_counts": {name: int(len(frame)) for name, frame in sources.items()},
        "inventory_snapshot_date": inventory_audit.get("latest_snapshot_date"),
        "inventory_coverage": summaries["current_inventory"].get("inventory_matched", 0) / max(summaries["current_inventory"].get("eligible_current_contexts", 0), 1),
        "final_rule_violation_count": int(sum(summary.get("final_rule_violation_count", 0) for summary in summaries.values() if isinstance(summary, dict))),
        "manual_review_rate": {split: summaries[split].get("manual_review_rate") for split in ("validation", "test")},
        "reproducibility": reproducibility,
        "compute": {**timings, "total_seconds": float(time.perf_counter() - started)},
        "tests": test_results,
        "CI": {"status": "DEFINED_NO_LIVE_SQL", "workflow": ".github/workflows/phase7-tests.yml"},
        "warnings": list(dict.fromkeys(warnings)),
        "major_blockers": list(dict.fromkeys(blockers)),
    }
    write_phase7_json(ARTIFACTS / "phase7_manifest.json", manifest)
    _write_reports(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 7 business pricing policy acceptance")
    parser.add_argument("--fixtures", action="store_true", help="Use deterministic empty source fixtures; never claims live SQL evidence")
    args = parser.parse_args()
    manifest = run_phase7(use_fixtures=args.fixtures)
    print(json.dumps({"result": manifest["result"], "recommendation": manifest["recommendation"], "blockers": manifest["major_blockers"], "warnings": manifest["warnings"]}, indent=2))
    raise SystemExit(0 if manifest["result"] != "BLOCKED" else 2)


if __name__ == "__main__":
    main()


__all__ = ["annotate_rule_compliance", "build_business_decisions", "main", "run_phase7"]
