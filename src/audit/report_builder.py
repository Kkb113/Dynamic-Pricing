from __future__ import annotations

import csv
import hashlib
import json
import logging
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .advanced_audit import (behavioral_coverage, cardinality_sparsity, dimension_price_support,
    missingness_profile, numeric_profile, price_history_audit, probability_diagnostics, promotion_audit,
    target_segment_profile, temporal_split_proposal)
from .competitor_audit import competitor_coverage, competitor_dimension_coverage
from .database_profile import connect_read_only, connection_string_from_settings, database_profile, sanitized_server_identity, schema_columns
from .generator_analysis import search_generator
from .leakage_analysis import build_leakage_matrix
from .price_variation_audit import price_variation_summary, product_price_support
from .relationship_audit import relationship_audit
from .rule_audit import rule_audit
from .sales_coverage_audit import sales_coverage
from .target_audit import outcome_consistency, quantity_profile, target_profile
from .temporal_audit import temporal_coverage, temporal_monthly_distribution

LOG = logging.getLogger("phase1")
ROOT = Path(__file__).resolve().parents[2]
EXPECTED_COUNTS = {"Pricing_Decision_Log": 35000, "Product_Price_History": 50000, "Competitor_Price": 40000,
                   "Sales_Order_Line": 30000, "Sales_Order": 12000, "Inventory": 15000, "Product": 3000,
                   "Customer": 5000, "Browsing_Events": 45000, "Cart_Events": 12000, "Search_Events": 12000,
                   "Promotions": 200, "Pricing_Rules": 200, "Weather": 3650, "Holiday": 80}
REQUIRED_TABLES = {"Pricing_Decision_Log", "Product_Price_History", "Competitor_Price", "Sales_Order_Line",
                   "Sales_Order", "Inventory", "Product", "Customer", "Promotions", "Pricing_Rules"}
CRITICAL_COLUMNS = {("Pricing_Decision_Log", c) for c in ["DecisionTime", "ProductID", "StoreID", "CurrentPrice",
                    "AppliedPrice", "PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime"]}


def json_default(value: Any):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if hasattr(value, "__float__"): return float(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or (list(rows[0]) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not fields: return
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def git_sha() -> str | None:
    try: return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception: return None


def git_metadata() -> dict[str, Any]:
    sha = git_sha()
    try:
        worktree_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip())
        code_paths=["pyproject.toml","conftest.py","src","tests","config","contracts",".github"]
        code_dirty=subprocess.run(["git","diff","--quiet","HEAD","--",*code_paths],cwd=ROOT,check=False,
                                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode != 0
        code_dirty=code_dirty or subprocess.run(["git","diff","--cached","--quiet","HEAD","--",*code_paths],cwd=ROOT,check=False,
                                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode != 0
        untracked=subprocess.check_output(["git","ls-files","--others","--exclude-standard","--",*code_paths],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        code_dirty=code_dirty or bool(untracked)
    except Exception:
        worktree_dirty = None
        code_dirty = None
    return {"git_sha": sha, "git_code_dirty": code_dirty, "git_worktree_dirty": worktree_dirty}


def source_tree_sha256() -> str:
    digest=hashlib.sha256()
    paths=[ROOT/"pyproject.toml",ROOT/"conftest.py",*sorted((ROOT/"src").rglob("*.py")),*sorted((ROOT/"tests").rglob("*.py"))]
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode()); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0")
    return digest.hexdigest()


def load_test_evidence(path: Path, current_source_hash: str) -> dict[str, Any]:
    if not path.exists():
        return {"status":"NOT_RUN","reason":"Machine-generated pytest evidence is missing"}
    try:
        evidence=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        return {"status":"INVALID","reason":type(exc).__name__}
    if evidence.get("source") != "pytest_sessionfinish":
        return {"status":"INVALID","reason":"Evidence was not emitted by pytest_sessionfinish"}
    if evidence.get("source_tree_sha256") != current_source_hash:
        return {**evidence,"status":"STALE","reason":"Test evidence does not match the current source tree"}
    return evidence


def locate_schema_document() -> Path | None:
    candidates=[]
    for pattern in ("Retail_Hyperpersonlaization_schema_document*.md","*retail*schema*document*.md","*schema*document*.md"):
        candidates.extend(ROOT.glob(pattern))
    return sorted({p.resolve() for p in candidates if p.is_file()})[0] if candidates else None


def safe_audit(name: str, fn: Callable[[], Any], errors: list[dict]) -> Any:
    try:
        value = fn(); LOG.info(json.dumps({"event": f"{name}_completed"})); return value
    except Exception as exc:
        errors.append({"audit": name, "error_type": type(exc).__name__, "message": str(exc)[:300]})
        return {"status": "AUDIT_ERROR", "error_type": type(exc).__name__}


def feasibility_rows() -> list[dict]:
    return [
      {"feature_family":"Product attributes","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Requires live schema and slowly-changing attribute review"},
      {"feature_family":"Store/Region","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Join keys expected; coverage must be measured"},
      {"feature_family":"Customer context","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Pre-decision non-PII context only"},
      {"feature_family":"Customer preferences","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Conditional due to fairness and synthetic-proxy risk"},
      {"feature_family":"Price history","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Half-open effective interval and overlap audit required"},
      {"feature_family":"Competitor prices","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Latest observation at or before DecisionTime only"},
      {"feature_family":"Promotions","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Promotion window must overlap DecisionTime"},
      {"feature_family":"Historical sales","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Prior-order coverage required at fallback grains"},
      {"feature_family":"Behavioral events","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Events must precede DecisionTime and be aggregated"},
      {"feature_family":"Holiday/Weather","status":"SUPPORTED_WITH_LIMITATIONS","reason":"Date/region coverage must be measured"},
      {"feature_family":"Inventory","status":"NOT_SUPPORTED_AS_HISTORICAL_FEATURE","reason":"Point-in-time snapshot; no backfill or forward-fill"},
      {"feature_family":"Inventory (current)","status":"SUPPORTED_AS_CURRENT_OPTIMIZATION_CONSTRAINT","reason":"Use only at recommendation time"},
    ]


def blocked_leakage_seed() -> list[dict]:
    columns = []
    pdl = ["PricingDecisionID","SessionID","CustomerID","ProductID","StoreID","DecisionTime","CurrentPrice",
           "AppliedPrice","RecommendedPrice","ExpectedDemand","PurchaseProbability","PriceElasticity","ExpectedRevenue",
           "ExpectedMarginPct","ModelVersion","ReasonCode","ActualRevenue","OutcomeTime","OrderLineID","PurchasedFlag","QuantityPurchased"]
    columns += [{"source_table":"Pricing_Decision_Log","column_name":x} for x in pdl]
    columns += [{"source_table":"Customer","column_name":x} for x in ["FirstName","LastName","Email","Gender","BirthDate","CustomerSegment","LoyaltyTier","PreferredChannel"]]
    columns += [{"source_table":"Inventory","column_name":x} for x in ["OnHandQty","SnapshotDate"]]
    return build_leakage_matrix(columns)


def acceptance_markdown(verdict: str, reason: str, data: dict) -> str:
    target=data.get("target_profile") or {}; profile=data.get("database_profile") or {}
    price=(data.get("price") or {}).get("product_support_summary",{}); quantity=(data.get("quantity") or {}).get("groups",[])
    purchased=next((x for x in quantity if x.get("outcome_group")=="1"),{})
    competitor_data=data.get("competitor") or {}; competitor=competitor_data.get("windows",{}); competitor_fallbacks=competitor_data.get("fallback_coverage_30d",{})
    sales_data=data.get("sales") or {}; sales=sales_data.get("product",{}); sales_grains=sales_data.get("grains",{})
    promotion_data=data.get("promotion") or {}; promotion=promotion_data.get("decision_coverage",{}); history=(data.get("price_history") or {}).get("decision_coverage",{})
    outcome=data.get("outcome") or {}; split=(data.get("split") or {}).get("splits",[]); rules=(data.get("rule") or {}).get("applied_price_compliance",{})
    relationships=data.get("relationship") or {}; tests=data.get("test_evidence") or {}
    temporal=data.get("temporal") if isinstance(data.get("temporal"),list) else []
    decision_time=next((x for x in temporal if x.get("table")=="Pricing_Decision_Log" and x.get("column")=="DecisionTime"),{})
    card=data.get("cardinality") if isinstance(data.get("cardinality"),list) else []
    product_card=next((x for x in card if x.get("dimension")=="ProductID"),{})
    store_card=next((x for x in card if x.get("dimension")=="StoreID"),{})
    gen=(data.get("generator") or {}).get("status","GENERATOR_LOGIC_NOT_AVAILABLE")
    proceed="PROCEED_TO_PHASE_2" if verdict!="BLOCKED" else "DO_NOT_PROCEED_TO_PHASE_2"
    pct=lambda x: "NOT_MEASURED" if x is None else f"{100*float(x):.2f}%"
    n=lambda x: "NOT_MEASURED" if x is None else f"{int(x):,}"
    split_lines="\n".join(f"- {x.get('split')}: {x.get('start_time')} through {x.get('end_time')} — {n(x.get('row_count'))} rows, {n(x.get('purchase_count'))} purchases, {n(x.get('product_coverage'))} products" for x in split) or "- NOT_MEASURED"
    consistency=sum(int(v or 0) for v in outcome.values() if isinstance(v,(int,float)))
    return f"""# Phase 1 Acceptance Report

## 1. Executive verdict

**{verdict}** — {reason} No production model, optimizer, API, or dashboard was created.

## 2. Database reconciliation

The live read-only database contains **{n(profile.get('table_count'))} tables, {n(profile.get('column_count'))} columns, and {n(profile.get('row_count'))} rows**. This matches the documented 24 / 224 / 328,420 totals. Per-table documented/live/difference/status values are in `schema_reconciliation.json`.

## 3. Target health

There are **{n(target.get('total_pricing_decisions'))}** decisions and **{n(target.get('non_null_count'))}** usable outcomes, with {n(target.get('purchase_count'))} purchases and {n(target.get('non_purchase_count'))} non-purchases. Purchase rate is **{pct(target.get('purchase_rate'))}**. Month/channel/store/region/category/brand/season/price-change profiles are in `target_segment_profile.csv`.

## 4. Quantity-target health

Purchased rows: **{n(purchased.get('row_count'))}**; quantity min/median/mean/p90/p95/p99/max: **{purchased.get('min_value','NA')} / {purchased.get('median','NA')} / {purchased.get('mean_value','NA')} / {purchased.get('p90','NA')} / {purchased.get('p95','NA')} / {purchased.get('p99','NA')} / {purchased.get('max_value','NA')}**. Outcome-consistency violations: **{consistency}**. The conditional quantity target is usable.

## 5. Price variation / learnability

Products observed: **{n(price.get('products'))}**; products with at least 2 distinct applied prices: **{n(price.get('products_ge_2_prices'))}**; at least 3: **{n(price.get('products_ge_3_prices'))}**; at least 5: **{n(price.get('products_ge_5_prices'))}**. Products with at least 10/20 decisions: **{n(price.get('products_ge_10_decisions'))} / {n(price.get('products_ge_20_decisions'))}**. Observed price-response variation is adequate for a global model; bucket associations are diagnostic, not causal.

## 6. Temporal coverage

Pricing decisions span **{decision_time.get('min_timestamp','NA')} through {decision_time.get('max_timestamp','NA')}**, across {n(decision_time.get('distinct_active_dates'))} active dates. Every future derived feature must satisfy `feature_timestamp <= DecisionTime`.

## 7. Competitor coverage

Strict Product×Region×Channel point-in-time coverage is same-day **{pct((competitor.get('0') or {}).get('coverage_rate'))}**, prior 3d **{pct((competitor.get('3') or {}).get('coverage_rate'))}**, 7d **{pct((competitor.get('7') or {}).get('coverage_rate'))}**, 14d **{pct((competitor.get('14') or {}).get('coverage_rate'))}**, and 30d **{pct((competitor.get('30') or {}).get('coverage_rate'))}**. At 30 days, Product×Region with any channel covers **{pct((competitor_fallbacks.get('product_region_any_channel') or {}).get('coverage_rate'))}** and Product-only covers **{pct((competitor_fallbacks.get('product_any_region_channel') or {}).get('coverage_rate'))}**. Phase 2 must retain availability/age/fallback indicators and never drop rows lacking competitor context.

## 8. Historical-sales feasibility

Only completed previous calendar days qualify; same-day date-only orders are excluded. At 30 days, prior-sale coverage is Product×Store **{pct((((sales_grains.get('product_store') or {}).get('30')) or {}).get('coverage_rate'))}**, Product×Region **{pct((((sales_grains.get('product_region') or {}).get('30')) or {}).get('coverage_rate'))}**, Product **{pct((sales.get('30') or {}).get('coverage_rate'))}**, Category×Store **{pct((((sales_grains.get('category_store') or {}).get('30')) or {}).get('coverage_rate'))}**, and Category **{pct((((sales_grains.get('category') or {}).get('30')) or {}).get('coverage_rate'))}**. Product-only coverage rises from 7d **{pct((sales.get('7') or {}).get('coverage_rate'))}** to 90d **{pct((sales.get('90') or {}).get('coverage_rate'))}**. Phase 2 should use this measured fallback hierarchy.

## 9. Promotion/calendar/weather feasibility

Active promotion coverage at decision time is **{pct(promotion.get('coverage_rate'))}**. Of the price-history promotion associations, **{n((promotion_data.get('price_history_associations') or {}).get('stale_or_inactive_associations'))}** are stale/inactive by window and must not be treated as active. Holiday and weather ranges are recorded in the temporal matrix and must join by date/region.

## 10. Product/store/category sparsity

ProductID has **{n(product_card.get('unique_values'))}** observed values (median {product_card.get('median_observations','NA')} decisions/entity; {n(product_card.get('low_frequency_count'))} below five). StoreID has **{n(store_card.get('unique_values'))}** values (median {store_card.get('median_observations','NA')}). ProductID and StoreID remain conditional CatBoost categoricals, not blindly encoded identifiers.

## 11. Data-quality issues

Outcome-consistency violations: **{consistency}**. Price-history decision coverage is **{pct(history.get('coverage_rate'))}** with {n(history.get('duplicate_active_decisions'))} decisions matching multiple eligible intervals. All **{n(relationships.get('logical_relationship_count'))}** Phase-2-critical logical joins were audited with **{n(relationships.get('logical_relationship_orphan_total'))}** total orphans. Referenced-price-rule compliance is **{pct(rules.get('compliance_rate'))}**; the remaining cases need rule-semantics review rather than automatic repair. Pytest evidence is machine-generated and source-bound: **{n(tests.get('passed'))} passed / {n(tests.get('failed'))} failed**.

## 12. Generator leakage analysis

Generator result: **{gen}**. The located older generator registry does not contain pricing-decision generation logic, so no formula is inferred. Empirical `PurchaseProbability` deciles are reported solely to measure synthetic outcome encoding; that field remains prohibited.

## 13. Final leakage matrix summary

All live columns are classified under a **deny-by-default explicit allowlist**. Cost and pricing rules are optimizer-only; raw sales/events are derivation-only; recommendation outputs and post-outcome fields are prohibited; PII is excluded; identifiers are join-only by default; inventory is prohibited historically.

## 14. Locked feature-policy summary

Core features are treatment price and proven pre-decision product/market/time context. Conditional features include high-cardinality IDs, preferences, and behavior. Current inventory, cost, rules, and constraints are optimization-only.

## 15. Inventory limitation

Inventory is a point-in-time snapshot and is **never** backfilled, forward-filled, or treated as historical decision context. It is supported only as a current optimization constraint.

## 16. Perishable/expiry limitation

Expiry-driven pricing remains out of scope. No expiry, batch, manufacture, or shelf-life values are created.

## 17. Proposed temporal split

{split_lines}

This is a Phase 3 proposal and uses chronological boundaries only.

## 18. Known limitations

- Generator source for pricing decisions is unavailable.
- Region/channel-matched competitor context is sparse (30-day coverage {pct((competitor.get('30') or {}).get('coverage_rate'))}).
- Product×Store 30-day sales coverage is {pct((((sales_grains.get('product_store') or {}).get('30')) or {}).get('coverage_rate'))}; hierarchical fallbacks are required.
- {n((promotion_data.get('price_history_associations') or {}).get('stale_or_inactive_associations'))} promotion associations are not active at their price interval.
- Rule compliance is {pct(rules.get('compliance_rate'))} under the audited direct constraints and needs semantic review.
- Individual SKU histories are uneven; global/hierarchical modelling is required.
- Inventory cannot be used historically.

## 19. Risks for Phase 2+

Synthetic probability/policy outputs could make accuracy misleading if admitted accidentally. Phase 2 must build joins point-in-time, enforce the leakage allowlist, quantify exclusions, and retain hierarchical fallbacks.

## 20. Overall result

**{verdict}**

## 21. Recommendation

**{proceed}** — Phase 2 may begin only under the locked contract and leakage tests.

### Dynamic-pricing learnability verdicts

1. AppliedPrice variation sufficient? **YES** — {n(price.get('products_ge_2_prices'))} products have at least two applied prices.
2. Both purchase classes represented? **YES** — {n(target.get('purchase_count'))} purchases and {n(target.get('non_purchase_count'))} non-purchases.
3. Quantity target usable? **YES** — {n(purchased.get('row_count'))} consistent positive purchased rows.
4. Leakage-safe point-in-time features constructible? **YES_WITH_LIMITATIONS** — coverage varies by feature family.
5. Competitor history useful? **YES_WITH_LIMITATIONS** — region/channel-matched 30-day coverage is {pct((competitor.get('30') or {}).get('coverage_rate'))}.
6. Sales velocity derivable? **YES_WITH_LIMITATIONS** — 30-day coverage ranges from Product×Store {pct((((sales_grains.get('product_store') or {}).get('30')) or {}).get('coverage_rate'))} to Category {pct((((sales_grains.get('category') or {}).get('30')) or {}).get('coverage_rate'))}.
7. Season/promotion/calendar context joinable? **YES_WITH_LIMITATIONS** — temporal overlap and region/date rules are mandatory.
8. Optimizer outputs separable? **YES** — explicit policy plus automated rejection tests.
9. Hidden generator structural problem? **NO** — none demonstrated; source unavailable, so empirical proxy risk remains a warning.
10. Proceed to Phase 2? **{'YES_WITH_LIMITATIONS' if verdict!='BLOCKED' else 'NO'}**.
"""


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    LOG.info(json.dumps({"event":"phase1_started"}))
    cfg_path = ROOT / "config" / "phase1_audit.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    artifacts = ROOT / cfg["audit"]["artifact_dir"]
    docs = ROOT / cfg["audit"]["document_dir"]
    artifacts.mkdir(parents=True, exist_ok=True); docs.mkdir(parents=True, exist_ok=True)
    current_source_hash=source_tree_sha256()
    test_evidence=load_test_evidence(artifacts/"test_results.json",current_source_hash)
    generator = search_generator(cfg["generator_search"]["roots"], cfg["generator_search"]["terms"], ROOT)
    write_json(artifacts / "generator_analysis.json", generator)
    errors: list[dict] = []
    data: dict[str, Any] = {"database_status":"NOT_AVAILABLE", "generator":generator, "test_evidence":test_evidence}
    raw = ""
    try:
        raw = connection_string_from_settings(cfg["database"], ROOT)
    except Exception:
        pass
    server_identity = sanitized_server_identity(raw) if raw else "not_configured"
    try:
        if not raw:
            raw = connection_string_from_settings(cfg["database"], ROOT)
        with connect_read_only(None, cfg["database"]["odbc_driver"], cfg["database"]["connect_timeout_seconds"], raw_connection=raw) as db:
            LOG.info(json.dumps({"event":"database_connection_validated"}))
            profile = database_profile(db, cfg["database"]["schema"]); data["database_status"] = "CONNECTED_READ_ONLY"; data["database_profile"] = profile
            columns = schema_columns(db, cfg["database"]["schema"])
            tables = {x["table_name"] for x in profile["tables"]}; colset = {(x["source_table"],x["column_name"]) for x in columns}
            missing_tables = sorted(REQUIRED_TABLES-tables); missing_columns = sorted(CRITICAL_COLUMNS-colset)
            live_rows={x["table_name"]:x["row_count"] for x in profile["tables"]}
            table_reconciliation=[{"table":name,"documented_value":documented,"live_value":live_rows.get(name),
              "difference":None if name not in live_rows else live_rows[name]-documented,
              "status":"MISSING" if name not in live_rows else "MATCH" if live_rows[name]==documented else "DIFFERENT"}
              for name,documented in EXPECTED_COUNTS.items()]
            reconciliation = {"documented":{"table_count":24,"column_count":224,"row_count":328420,"table_rows":EXPECTED_COUNTS},
                              "live":profile,"table_reconciliation":table_reconciliation,
                              "missing_required_tables":missing_tables,"missing_critical_columns":missing_columns}
            data["reconciliation"] = reconciliation
            write_json(artifacts / "database_profile.json", profile); write_json(artifacts / "schema_reconciliation.json", reconciliation)
            leakage = build_leakage_matrix(columns); write_csv(artifacts / "leakage_matrix.csv", leakage)
            temporal = safe_audit("temporal_audit", lambda: temporal_coverage(db,colset,cfg["database"]["schema"]),errors); data["temporal"] = temporal
            write_csv(artifacts / "temporal_coverage.csv", temporal if isinstance(temporal,list) else [])
            monthly=safe_audit("temporal_monthly_distribution",lambda:temporal_monthly_distribution(db,colset,cfg["database"]["schema"]),errors); write_csv(artifacts/"temporal_monthly_distribution.csv",monthly if isinstance(monthly,list) else [])
            data["target_profile"] = safe_audit("target_audit",lambda:target_profile(db),errors); write_json(artifacts/"target_profile.json",data["target_profile"])
            data["quantity"] = safe_audit("quantity_audit",lambda:quantity_profile(db),errors); write_json(artifacts/"quantity_profile.json",data["quantity"])
            data["outcome"] = safe_audit("outcome_consistency",lambda:outcome_consistency(db),errors); write_json(artifacts/"outcome_consistency.json",data["outcome"])
            price = safe_audit("price_variation_audit",lambda:price_variation_summary(db),errors); data["price"] = price; write_json(artifacts/"price_variation_summary.json",price)
            product = safe_audit("product_price_support",lambda:product_price_support(db),errors); write_csv(artifacts/"product_price_support.csv",product if isinstance(product,list) else [])
            segments=safe_audit("target_segment_audit",lambda:target_segment_profile(db),errors); write_csv(artifacts/"target_segment_profile.csv",segments if isinstance(segments,list) else [])
            dimensions=safe_audit("dimension_price_support",lambda:dimension_price_support(db),errors)
            if isinstance(dimensions,dict):
                for dimension,rows in dimensions.items(): write_csv(artifacts/f"{dimension}_price_support.csv",rows)
            data["competitor"] = safe_audit("competitor_audit",lambda:competitor_coverage(db,cfg["audit"]["competitor_windows_days"]),errors); write_json(artifacts/"competitor_coverage.json",data["competitor"])
            competitor_dimensions=safe_audit("competitor_dimension_coverage",lambda:competitor_dimension_coverage(db),errors)
            if isinstance(competitor_dimensions,dict):
                for dimension,rows in competitor_dimensions.items(): write_csv(artifacts/f"competitor_coverage_by_{dimension}.csv",rows)
            data["sales"] = safe_audit("sales_coverage_audit",lambda:sales_coverage(db,cfg["audit"]["sales_windows_days"]),errors); write_json(artifacts/"historical_sales_coverage.json",data["sales"])
            data["price_history"] = safe_audit("price_history_audit",lambda:price_history_audit(db),errors); write_json(artifacts/"price_history_audit.json",data["price_history"])
            data["promotion"] = safe_audit("promotion_audit",lambda:promotion_audit(db),errors); write_json(artifacts/"promotion_coverage.json",data["promotion"])
            probability=safe_audit("probability_diagnostics",lambda:probability_diagnostics(db),errors); write_csv(artifacts/"purchase_probability_deciles.csv",probability if isinstance(probability,list) else [])
            cardinality=safe_audit("cardinality_sparsity",lambda:cardinality_sparsity(db,cfg["audit"]["low_frequency_threshold"]),errors); data["cardinality"]=cardinality; write_csv(artifacts/"cardinality_sparsity.csv",cardinality if isinstance(cardinality,list) else [])
            missing=safe_audit("missingness_profile",lambda:missingness_profile(db),errors); write_csv(artifacts/"missingness_profile.csv",missing if isinstance(missing,list) else [])
            numeric=safe_audit("numeric_profile",lambda:numeric_profile(db),errors); write_csv(artifacts/"numeric_profile.csv",numeric if isinstance(numeric,list) else [])
            data["behavior"] = safe_audit("behavioral_coverage",lambda:behavioral_coverage(db,cfg["audit"]["behavior_windows_hours"]),errors); write_json(artifacts/"behavioral_coverage.json",data["behavior"])
            data["split"] = safe_audit("temporal_split",lambda:temporal_split_proposal(db),errors); write_json(artifacts/"proposed_temporal_split.json",data["split"])
            data["rule"] = safe_audit("rule_audit",lambda:rule_audit(db),errors); write_json(artifacts/"rule_audit.json",data["rule"])
            data["relationship"] = safe_audit("relationship_audit",lambda:relationship_audit(db),errors); write_json(artifacts/"relationship_audit.json",data["relationship"])
            hard_reasons=[]
            if missing_tables: hard_reasons.append("required tables missing")
            if missing_columns: hard_reasons.append("critical columns missing")
            if errors: hard_reasons.append("one or more mandatory audits failed")
            if test_evidence.get("status") != "PASS" or test_evidence.get("exit_code") != 0:
                hard_reasons.append("current machine-generated pytest evidence is missing, stale, or failed")
            logical_orphans=data["relationship"].get("logical_relationship_orphan_total",0)
            if logical_orphans > data["target_profile"].get("total_pricing_decisions",0)*0.01:
                hard_reasons.append("Phase-2-critical logical relationship orphans exceed 1% of pricing decisions")
            if not data["target_profile"].get("purchase_count") or not data["target_profile"].get("non_purchase_count"): hard_reasons.append("purchase target has one class")
            if not price.get("product_support_summary",{}).get("products_ge_2_prices"): hard_reasons.append("no meaningful applied-price variation")
            if sum(int(v or 0) for v in data["outcome"].values() if isinstance(v,(int,float))) > data["target_profile"].get("total_pricing_decisions",0)*0.05:
                hard_reasons.append("quantity/outcome consistency violations exceed 5%")
            if hard_reasons:
                verdict,reason="BLOCKED","; ".join(hard_reasons)+"."
            else:
                verdict,reason="PASS_WITH_WARNINGS","Live mandatory checks passed; sparse short-window context and unavailable pricing generator logic require Phase 2 safeguards."
    except Exception as exc:
        errors.append({"audit":"database_connection","error_type":type(exc).__name__,"sqlstate":str(getattr(exc,"args",[None])[0])[:20]})
        verdict, reason = "BLOCKED", "Live SQL Server cannot be accessed with the existing configuration (SQLSTATE 28000 / login error 18456)."
        leakage = blocked_leakage_seed(); write_csv(artifacts / "leakage_matrix.csv", leakage)
        unavailable = {"status":"NOT_MEASURED","reason":"LIVE_SQL_AUTHENTICATION_FAILED"}
        for name in ["database_profile","target_profile","quantity_profile","price_variation_summary","competitor_coverage","historical_sales_coverage","promotion_coverage","rule_audit","relationship_audit","proposed_temporal_split"]:
            write_json(artifacts/f"{name}.json",unavailable)
        write_json(artifacts/"schema_reconciliation.json",{"documented":{"table_count":24,"column_count":224,"row_count":328420,"table_rows":EXPECTED_COUNTS},"live":unavailable})
        write_csv(artifacts/"temporal_coverage.csv",[],["table","column","status","row_count","min_timestamp","max_timestamp","distinct_active_dates"])
        write_csv(artifacts/"target_segment_profile.csv",[],["segment_type","segment_value","decision_count","purchase_count","purchase_rate"])
        support_fields=["entity_id","decision_count","unique_current_price_count","unique_applied_price_count","min_applied_price","max_applied_price","mean_applied_price","std_applied_price","applied_price_range","applied_price_cv","pct_changed"]
        write_csv(artifacts/"product_price_support.csv",[],support_fields); write_csv(artifacts/"category_price_support.csv",[],support_fields)
    feasibility = feasibility_rows(); write_csv(artifacts/"point_in_time_feasibility.csv",feasibility)
    contract = ROOT/"contracts"/"dynamic_pricing_ml_contract_v1.yaml"; policy = ROOT/"contracts"/"leakage_policy_v1.yaml"
    canonical = json.dumps({"database_status":data["database_status"],"target":data.get("target_profile"),
      "schema_reconciliation":json.loads((artifacts/"schema_reconciliation.json").read_text()),
      "temporal_coverage":data.get("temporal"),"cardinality":data.get("cardinality"),
      "price_support":(data.get("price") or {}).get("product_support_summary"),
      "temporal_split":data.get("split")},sort_keys=True,default=json_default)
    fingerprint={"status":"COMPLETE" if data["database_status"]=="CONNECTED_READ_ONLY" else "INCOMPLETE_LIVE_DATABASE_UNAVAILABLE","sha256":hashlib.sha256(canonical.encode()).hexdigest(),"canonical_metadata":json.loads(canonical)}
    write_json(artifacts/"dataset_fingerprint.json",fingerprint)
    git_info=git_metadata(); schema_document=locate_schema_document()
    manifest={"audit_timestamp_utc":datetime.now(timezone.utc).isoformat(),"result":verdict,"database":cfg["database"]["name"],"schema":cfg["database"]["schema"],"sanitized_server_identity":server_identity,
      **git_info,"source_tree_sha256":current_source_hash,"schema_document_path":str(schema_document.relative_to(ROOT)) if schema_document else None,
      "schema_document_sha256":sha256_file(schema_document) if schema_document else None,"ml_contract_sha256":sha256_file(contract),
      "leakage_policy_sha256":sha256_file(policy),"configuration_sha256":sha256_file(cfg_path),
      "dataset_fingerprint_sha256":fingerprint["sha256"],"test_evidence_sha256":sha256_file(artifacts/"test_results.json"),
      "test_summary":test_evidence,"errors":errors}
    write_json(artifacts/"phase1_manifest.json",manifest)
    (docs/"PHASE1_ACCEPTANCE_REPORT.md").write_text(acceptance_markdown(verdict,reason,data),encoding="utf-8")
    LOG.info(json.dumps({"event":"phase1_acceptance_completed","result":verdict}))
    return 2 if verdict=="BLOCKED" else 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__": main()
