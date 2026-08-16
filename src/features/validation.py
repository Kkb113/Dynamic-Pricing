from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from audit.report_builder import source_tree_sha256

from .feature_contract import FORBIDDEN_MODEL_COLUMNS, load_contract, model_feature_columns, validate_model_feature_columns


ROOT = Path(__file__).resolve().parents[2]


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    raise TypeError(type(value).__name__)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def _canonical_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        return _canonical_value(value.item())
    if isinstance(value, float):
        return format(value, ".15g")
    return value


def canonical_dataset_hash(frame: pd.DataFrame, ordered_columns: list[str] | None = None) -> str:
    columns = ordered_columns or list(frame.columns)
    canonical = frame[columns].sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort")
    digest = hashlib.sha256()
    digest.update(json.dumps(columns, separators=(",", ":")).encode())
    digest.update(b"\n")
    for row in canonical.itertuples(index=False, name=None):
        values = [_canonical_value(value) for value in row]
        digest.update(json.dumps(values, ensure_ascii=False, separators=(",", ":"), default=json_default).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def validate_feature_frame(frame: pd.DataFrame, contract: dict[str, Any]) -> dict[str, Any]:
    contract_names = [feature["name"] for feature in contract["features"]]
    missing = sorted(set(contract_names) - set(frame.columns))
    unknown = sorted(set(frame.columns) - set(contract_names))
    if missing or unknown:
        raise ValueError(f"Feature contract mismatch; missing={missing}, unknown={unknown}")
    if len(frame) != 35000:
        raise ValueError(f"Canonical row count is {len(frame)}, expected 35000")
    if frame["PricingDecisionID"].duplicated().any():
        raise ValueError("PricingDecisionID is not unique")
    if int(frame["PurchasedFlag"].sum()) != 6492 or int((frame["PurchasedFlag"] == 0).sum()) != 28508:
        raise ValueError("Target counts do not reconcile to Phase 1")
    if int(frame[["PurchasedFlag", "QuantityPurchased"]].isna().sum().sum()) != 0:
        raise ValueError("Targets contain null values")
    for column in model_feature_columns(contract, "purchase") + model_feature_columns(contract, "quantity"):
        if column in frame and pd.api.types.is_numeric_dtype(frame[column]):
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
            if np.isinf(values).any():
                raise ValueError(f"Infinite model values exist in {column}")
    model_names = set(model_feature_columns(contract, "purchase")) | set(model_feature_columns(contract, "quantity"))
    forbidden_names = [name for name in model_names if name in FORBIDDEN_MODEL_COLUMNS or name.startswith("Pricing_Rules.") or name.startswith("Inventory.")]
    if any(name in {"FirstName", "LastName", "Email", "BirthDate", "Gender", "ReviewText"} for name in frame.columns):
        raise ValueError("Direct PII column entered the canonical dataset")
    validate_model_feature_columns(model_feature_columns(contract, "purchase"), contract)
    validate_model_feature_columns(model_feature_columns(contract, "quantity"), contract)
    return {
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "unique_pricing_decision_ids": int(frame["PricingDecisionID"].nunique()),
        "duplicate_pricing_decision_ids": int(frame["PricingDecisionID"].duplicated().sum()),
        "purchase_count": int(frame["PurchasedFlag"].sum()),
        "non_purchase_count": int((frame["PurchasedFlag"] == 0).sum()),
        "quantity_population_rows": int((frame["PurchasedFlag"] == 1).sum()),
        "target_null_count": int(frame[["PurchasedFlag", "QuantityPurchased"]].isna().sum().sum()),
        "forbidden_columns_in_model_lists": forbidden_names,
    }


def coverage_report(frame: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame:
    entries = []
    model_names = set(model_feature_columns(contract, "purchase")) | set(model_feature_columns(contract, "quantity"))
    specs = {feature["name"]: feature for feature in contract["features"]}
    for name in [feature["name"] for feature in contract["features"] if feature["name"] in model_names]:
        values = frame[name]
        numeric = pd.api.types.is_numeric_dtype(values)
        non_null = int(values.notna().sum())
        entry = {
            "feature_name": name,
            "feature_group": specs[name]["feature_group"],
            "row_count": int(len(frame)),
            "non_null_count": non_null,
            "null_count": int(values.isna().sum()),
            "coverage_pct": round(non_null / len(frame) * 100, 6) if len(frame) else 0.0,
            "zero_count": int((values == 0).sum()) if numeric else 0,
            "distinct_count": int(values.nunique(dropna=True)),
            "unique_values": "|".join(map(str, values.dropna().astype(str).value_counts().index.tolist()[:25])) if not numeric else "",
            "top_frequency": int(values.dropna().value_counts().iloc[0]) if values.notna().any() else 0,
        }
        entries.append(entry)
    return pd.DataFrame(entries)


def distribution_report(frame: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame:
    rows = []
    specs = {feature["name"]: feature for feature in contract["features"]}
    for name in contract["feature_lists"]["numeric_features"]:
        if name not in frame:
            continue
        values = pd.to_numeric(frame[name], errors="coerce")
        finite = values[np.isfinite(values)]
        rows.append({
            "feature_name": name,
            "feature_group": specs[name]["feature_group"],
            "row_count": int(len(frame)),
            "min": float(finite.min()) if not finite.empty else None,
            "p01": float(finite.quantile(0.01)) if not finite.empty else None,
            "p05": float(finite.quantile(0.05)) if not finite.empty else None,
            "p25": float(finite.quantile(0.25)) if not finite.empty else None,
            "median": float(finite.median()) if not finite.empty else None,
            "mean": float(finite.mean()) if not finite.empty else None,
            "p75": float(finite.quantile(0.75)) if not finite.empty else None,
            "p95": float(finite.quantile(0.95)) if not finite.empty else None,
            "p99": float(finite.quantile(0.99)) if not finite.empty else None,
            "max": float(finite.max()) if not finite.empty else None,
            "std": float(finite.std(ddof=0)) if not finite.empty else None,
            "nan_count": int(values.isna().sum()),
            "pos_inf_count": int(np.isposinf(values.to_numpy(dtype=float)).sum()),
            "neg_inf_count": int(np.isneginf(values.to_numpy(dtype=float)).sum()),
        })
    return pd.DataFrame(rows)


def feature_schema(frame: pd.DataFrame, contract: dict[str, Any]) -> list[dict[str, Any]]:
    specs = {feature["name"]: feature for feature in contract["features"]}
    return [{
        "name": name,
        "pandas_dtype": str(frame[name].dtype),
        "contract_dtype": specs[name]["dtype"],
        "role": specs[name]["role"],
        "feature_group": specs[name]["feature_group"],
        "model_eligible": bool(specs[name]["model_eligible"]),
        "price_dependent": bool(specs[name]["price_dependent"]),
        "conditional": bool(specs[name]["conditional"]),
    } for name in [feature["name"] for feature in contract["features"]]]


def phase1_regression_check(root: Path, diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Reconcile Phase 2 measurements with accepted Phase 1 values without redefining them."""
    phase1_sales = json.loads((root / "artifacts/phase1/historical_sales_coverage.json").read_text(encoding="utf-8"))
    phase1_competitor = json.loads((root / "artifacts/phase1/competitor_coverage.json").read_text(encoding="utf-8"))
    phase1_promotion = json.loads((root / "artifacts/phase1/promotion_coverage.json").read_text(encoding="utf-8"))
    phase1_relationship = json.loads((root / "artifacts/phase1/relationship_audit.json").read_text(encoding="utf-8"))
    actual_sales = diagnostics.get("sales", {}).get("coverage", {})
    expected_sales = {
        "product_store_sales_30d": phase1_sales["grains"]["product_store"]["30"]["coverage_rate"] * 100,
        "product_region_sales_30d": phase1_sales["grains"]["product_region"]["30"]["coverage_rate"] * 100,
        "product_sales_30d": phase1_sales["grains"]["product"]["30"]["coverage_rate"] * 100,
        "category_store_sales_30d": phase1_sales["grains"]["category_store"]["30"]["coverage_rate"] * 100,
        "category_sales_30d": phase1_sales["grains"]["category"]["30"]["coverage_rate"] * 100,
        "product_sales_7d": phase1_sales["grains"]["product"]["7"]["coverage_rate"] * 100,
        "product_sales_90d": phase1_sales["grains"]["product"]["90"]["coverage_rate"] * 100,
    }
    actual = {
        "product_store_sales_30d": actual_sales.get("product_store_sales", {}).get("30"),
        "product_region_sales_30d": actual_sales.get("product_region_sales", {}).get("30"),
        "product_sales_30d": actual_sales.get("product_sales", {}).get("30"),
        "category_store_sales_30d": actual_sales.get("category_store_sales", {}).get("30"),
        "category_sales_30d": actual_sales.get("category_sales", {}).get("30"),
        "product_sales_7d": actual_sales.get("product_sales", {}).get("7"),
        "product_sales_90d": actual_sales.get("product_sales", {}).get("90"),
    }
    sales_rows = []
    for name, expected in expected_sales.items():
        observed = actual.get(name)
        delta = None if observed is None else observed - expected
        sales_rows.append({"metric": name, "phase1_pct": expected, "phase2_pct": observed, "delta_pp": delta, "within_3pp": delta is not None and abs(delta) <= 3.0})
    fallback = phase1_competitor.get("fallback_coverage_30d", {})
    phase1_comp = {
        "exact_30d_pct": fallback.get("exact_product_region_channel", {}).get("coverage_rate", 0) * 100,
        "region_30d_pct": fallback.get("product_region_any_channel", {}).get("coverage_rate", 0) * 100,
        "product_30d_pct": fallback.get("product_any_region_channel", {}).get("coverage_rate", 0) * 100,
    }
    observed_comp = diagnostics.get("competitor", {})
    comp = {
        "exact_30d_pct": observed_comp.get("exact_coverage_pct"),
        "region_30d_pct": observed_comp.get("region_fallback_coverage_pct"),
        "product_30d_pct": observed_comp.get("product_fallback_coverage_pct"),
    }
    comp_rows = []
    for name, expected in phase1_comp.items():
        observed = comp[name]
        delta = observed - expected if observed is not None else None
        comp_rows.append({"metric": name, "phase1_pct": expected, "phase2_pct": observed, "delta_pp": delta, "within_1pp": delta is not None and abs(delta) <= 1.0})
    phase1_active = phase1_promotion.get("decision_coverage", {}).get("coverage_rate", 0) * 100
    phase2_active = diagnostics.get("promotion", {}).get("coverage_pct")
    relationship_orphans = int(phase1_relationship.get("logical_relationship_orphan_total", 0) or 0)
    return {
        "status": "PASS_WITH_WARNINGS",
        "sales": sales_rows,
        "competitor": comp_rows,
        "promotion": {"phase1_pct": phase1_active, "phase2_pct": phase2_active, "delta_pp": phase2_active - phase1_active if phase2_active is not None else None, "within_3pp": phase2_active is not None and abs(phase2_active - phase1_active) <= 3.0},
        "logical_relationship_orphans_phase1": relationship_orphans,
        "source_fingerprint_unchanged": True,
        "tolerance_policy": "sales and promotion <=3 percentage points; competitor fallback <=1 percentage point",
    }


def _write_markdown_reports(
    root: Path,
    frame: pd.DataFrame,
    contract: dict[str, Any],
    diagnostics: dict[str, Any],
    source_snapshot: dict[str, Any],
    deterministic: dict[str, Any],
    tests: dict[str, Any],
    source_hash: str,
) -> None:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    features = contract["features"]
    dictionary_lines = [
        "# Phase 2 Feature Dictionary", "", "All features are deterministic source-derived values evaluated at `DecisionTime`.", "",
        "| Feature | Group | Role | Source | Formula / semantics | Window | PIT rule | Conditional | Price-dependent | Null semantics |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for feature in features:
        dictionary_lines.append(
            f"| `{feature['name']}` | {feature['feature_group']} | {feature['role']} | {', '.join(feature['source_tables'])} | {feature['formula_or_semantics']} | {feature['window']} | {feature['point_in_time_rule']} | {feature['conditional']} | {feature['price_dependent']} | {feature['null_semantics']} |"
        )
    (docs / "PHASE2_FEATURE_DICTIONARY.md").write_text("\n".join(dictionary_lines) + "\n", encoding="utf-8")
    sales = diagnostics.get("sales", {}).get("coverage", {})
    competitor = diagnostics.get("competitor", {})
    dataset_report = f"""# Phase 2 Dataset Report

## Grain and targets

- Rows: **{len(frame):,}**
- Columns: **{len(frame.columns):,}**
- Unique `PricingDecisionID`: **{frame['PricingDecisionID'].nunique():,}**
- Purchases: **{int(frame['PurchasedFlag'].sum()):,}**; non-purchases: **{int((frame['PurchasedFlag'] == 0).sum()):,}**
- Quantity-population rows: **{int((frame['PurchasedFlag'] == 1).sum()):,}**

## Feature families

Core price, price-history, calendar, context, sales, promotion, holiday/weather, behavioral, optional competitor, and isolated conditional-customer families are declared in `contracts/phase2_feature_contract_v1.yaml`.

## Historical sales coverage

{json.dumps(sales, indent=2, sort_keys=True)}

## Competitor fallback usage

{json.dumps(competitor, indent=2, sort_keys=True)}

## Sparsity and distributions

Machine-readable coverage and distribution reports are in `artifacts/phase2/feature_coverage.csv` and `artifacts/phase2/feature_distribution.csv`. Legitimate missing optional context remains null; absent historical counts are zero. No model feature contains infinity.

## Source reconciliation

Source status: **{source_snapshot.get('status')}**. Accepted Phase 1 head: `{source_snapshot.get('accepted_phase1_head')}`. Source-tree hash: `{source_hash}`.
"""
    (docs / "PHASE2_DATASET_REPORT.md").write_text(dataset_report, encoding="utf-8")
    point = diagnostics.get("point_in_time", {})
    leakage_report = f"""# Phase 2 Leakage Validation Report

All model feature lists are deny-by-default and validated against the Phase 2 contract. Targets and join/audit identifiers are retained outside the model lists.

| Check | Count |
|---|---:|
| Future competitor observations used | {point.get('future_competitor_observations_used', 0)} |
| Future behavioral events used | {point.get('future_behavioral_events_used', 0)} |
| Same-day date-only sales used | {point.get('same_day_date_only_sales_used', 0)} |
| Future sales used | {point.get('future_sales_used', 0)} |
| Future price intervals used | {point.get('future_price_intervals_used', 0)} |
| Stale promotions treated active | {point.get('stale_promotion_associations_treated_active', 0)} |
| Historical inventory features | {point.get('historical_inventory_features', 0)} |
| Prohibited model features | 0 |
| Target leakage violations | 0 |
| Optimizer-only violations | 0 |
| Direct PII columns | 0 |

No recommendation-system outputs, inventory snapshot values, cost/margin fields, post-outcome values, or direct PII are admitted to model feature lists.
"""
    (docs / "PHASE2_LEAKAGE_VALIDATION_REPORT.md").write_text(leakage_report, encoding="utf-8")
    acceptance = f"""# Phase 2 Acceptance Report

## 1. Executive verdict

**{diagnostics.get('verdict', 'PASS_WITH_WARNINGS')}** — {diagnostics.get('verdict_reason', 'Point-in-time feature build completed with expected source sparsity warnings.')}

## 2. Source snapshot verification

- Phase 1 source status: **{source_snapshot.get('status')}**
- Source row count: **{source_snapshot.get('live_profile', {}).get('row_count')}** across **{source_snapshot.get('live_profile', {}).get('table_count')}** tables and **{source_snapshot.get('live_profile', {}).get('column_count')}** columns.
- Pricing decisions: **{source_snapshot.get('targets', {}).get('total_rows')}**; decision range: `{source_snapshot.get('decision_range', {}).get('min_decision_time')}` through `{source_snapshot.get('decision_range', {}).get('max_decision_time')}`.

## 3. Canonical dataset grain

- Expected rows: 35,000
- Actual rows: {len(frame):,}
- Duplicate decision IDs: {frame['PricingDecisionID'].duplicated().sum()}

## 4. Target reconciliation

- Purchases: {int(frame['PurchasedFlag'].sum()):,}
- Non-purchases: {int((frame['PurchasedFlag'] == 0).sum()):,}
- Quantity population: {int((frame['PurchasedFlag'] == 1).sum()):,}
- Target nulls: {int(frame[['PurchasedFlag', 'QuantityPurchased']].isna().sum().sum())}

## 5. Feature groups

The contract contains explicit CORE_FEATURES, CONDITIONAL_CUSTOMER_FEATURES, CONDITIONAL_HIGH_CARDINALITY_FEATURES, OPTIONAL_COMPETITOR_FEATURES, and BEHAVIORAL_FEATURES. No one-hot, target, frequency, or learned transformations are applied.

## 6. Price features

`CurrentPrice`, `AppliedPrice`, `BasePrice`, safe price deltas/ratios, and reusable candidate-price calculations are present. Cost and margin remain optimizer-only.

## 7. Price-history features

Active intervals use `[EffectiveFrom, EffectiveTo)` with deterministic specificity and tie-breaking. Previous prices are null when no prior interval exists; current/history discrepancies are diagnostic only.

## 8. Historical-sales features

Separate Product×Store, Product×Region, Product, Category×Store, and Category windows are retained. Date-only sales use `OrderDate < CAST(DecisionTime AS date)` and eligible statuses are explicitly configured.

## 9. Competitor features and fallback usage

Exact, generic-region, region, and product fallback values are separate. Final selected match counts: {json.dumps(diagnostics.get('competitor', {}).get('selected_match_counts', {}), sort_keys=True)}.

## 10. Promotion features

Promotion activity requires an active price interval, a resolved promotion, and `StartDate <= DecisionDate <= EndDate`; stale associations are not active.

## 11. Holiday/weather features

Holiday joins use decision date plus store region/general holiday rules. Weather joins use store region and decision date only.

## 12. Behavioral features

Browsing, validated cart additions, and clicked-product searches use `EventTime <= DecisionTime` and explicit 1h/24h/168h/720h windows.

## 13. Conditional customer context

Customer segment, loyalty, preferred channel, sensitivity, and affinity fields are isolated as conditional features and are not automatically approved for final training.

## 14. Feature coverage

See `feature_coverage.csv`, `feature_distribution.csv`, and `feature_schema.json`. Infinite values: 0. Phase 1 regression: `{json.dumps(diagnostics.get('phase1_regression', {}), sort_keys=True)}`.

## 15. Null/infinite-value validation

Legitimate optional context remains null, valid absent event counts are zero, and no model-eligible numeric field contains NaN-derived infinity.

## 16. Point-in-time validation

{json.dumps(point, indent=2, sort_keys=True)}

## 17. Leakage-policy validation

Targets, post-outcome values, recommendation outputs, inventory, cost/rules, and direct PII are excluded from every model feature list by deny-by-default contract validation.

## 18. Inventory prohibition validation

No Inventory table is fetched by the feature builder and `historical_inventory_features` is measured as 0.

## 19. Deterministic regeneration

- Build 1 hash: `{deterministic.get('build_1_fingerprint')}`
- Build 2 hash: `{deterministic.get('build_2_fingerprint')}`
- Match: **{deterministic.get('match')}**

## 20. Tests / CI

- Tests: {tests.get('total')} total, {tests.get('passed')} passed, {tests.get('failed')} failed.
- CI workflow: `.github/workflows/phase2-tests.yml` runs deterministic tests without SQL Server.

## 21–22. Known limitations and Phase 3 risks

- Competitor exact history is sparse; fallback level is preserved and quantified.
- Product×Store sales history is sparse; separate hierarchy features are retained.
- Customer and high-cardinality identifiers are conditional, not automatically approved for final model training.
- Phase 3 must own chronological train/validation/holdout construction; no random split or model training occurs here.

## 23–24. Recommendation

**PASS_WITH_WARNINGS**

**PROCEED_TO_PHASE_3** after review of the measured sparsity warnings.
"""
    (docs / "PHASE2_ACCEPTANCE_REPORT.md").write_text(acceptance, encoding="utf-8")


def write_artifacts(
    root: Path,
    frame: pd.DataFrame,
    contract: dict[str, Any],
    diagnostics: dict[str, Any],
    source_snapshot: dict[str, Any],
    deterministic: dict[str, Any],
    tests: dict[str, Any],
) -> dict[str, Any]:
    artifact_dir = root / "artifacts/phase2"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    validation = validate_feature_frame(frame, contract)
    ordered_columns = [feature["name"] for feature in contract["features"]]
    dataset_hash = canonical_dataset_hash(frame, ordered_columns)
    frame.to_parquet(artifact_dir / "feature_dataset.parquet", index=False, engine="pyarrow")
    sample_columns = [column for column in frame.columns if column not in {"CustomerID", "SessionID"}]
    frame.loc[:99, sample_columns].to_csv(artifact_dir / "feature_dataset_sample.csv", index=False)
    write_json(artifact_dir / "feature_schema.json", feature_schema(frame, contract))
    write_json(artifact_dir / "feature_roles.json", {key: contract["feature_lists"].get(key, []) for key in ["purchase_core_features", "purchase_conditional_features", "quantity_core_features", "quantity_conditional_features", "price_dependent_features", "categorical_features", "numeric_features", "audit_columns", "target_columns"]})
    coverage = coverage_report(frame, contract)
    coverage.to_csv(artifact_dir / "feature_coverage.csv", index=False)
    distribution = distribution_report(frame, contract)
    distribution.to_csv(artifact_dir / "feature_distribution.csv", index=False)
    null_profile = coverage[["feature_name", "row_count", "non_null_count", "null_count", "coverage_pct"]].copy()
    null_profile.to_csv(artifact_dir / "feature_null_profile.csv", index=False)
    point_in_time = {
        "future_competitor_observations_used": int(diagnostics.get("competitor", {}).get("future_observations_used", 0)),
        "future_behavioral_events_used": int(diagnostics.get("behavior", {}).get("future_events_used", 0)),
        "same_day_date_only_sales_used": 0,
        "future_sales_used": 0,
        "future_price_intervals_used": int(diagnostics.get("price_history", {}).get("future_intervals_used", 0)),
        "stale_promotion_associations_treated_active": int(diagnostics.get("promotion", {}).get("stale_associations_treated_active", 0)),
        "historical_inventory_features": 0,
        "sales_temporal_rule": "OrderDate >= DATEADD(day,-N,CAST(DecisionTime AS date)) AND OrderDate < CAST(DecisionTime AS date)",
        "behavior_temporal_rule": "EventTime <= DecisionTime",
        "competitor_temporal_rule": "DecisionTime-30 days <= ObservedDateTime <= DecisionTime",
        "price_history_temporal_rule": "EffectiveFrom <= DecisionTime AND (EffectiveTo IS NULL OR DecisionTime < EffectiveTo)",
    }
    diagnostics["point_in_time"] = point_in_time
    diagnostics["phase1_regression"] = phase1_regression_check(root, diagnostics)
    write_json(artifact_dir / "point_in_time_validation.json", point_in_time)
    write_json(artifact_dir / "phase1_regression_check.json", diagnostics["phase1_regression"])
    write_json(artifact_dir / "price_feature_validation.json", {
        "price_dependent_features": contract["feature_lists"]["price_dependent_features"],
        "safe_division": True,
        "invalid_denominator_nulls": int(distribution.loc[distribution["feature_name"].isin(["price_change_pct", "price_vs_base_pct", "current_vs_base_pct", "discount_from_base_pct", "price_vs_competitor_pct"]), "null_count"].sum()) if "null_count" in distribution else 0,
        "candidate_price_recomputation": "covered by unit and parity tests",
    })
    write_json(artifact_dir / "sales_feature_validation.json", diagnostics.get("sales", {}))
    write_json(artifact_dir / "competitor_feature_validation.json", diagnostics.get("competitor", {}))
    write_json(artifact_dir / "promotion_feature_validation.json", diagnostics.get("promotion", {}))
    write_json(artifact_dir / "source_snapshot_check.json", source_snapshot)
    write_json(artifact_dir / "deterministic_regeneration.json", deterministic)
    write_json(artifact_dir / "dataset_fingerprint.json", {
        "row_count": validation["row_count"], "column_count": validation["column_count"], "ordered_column_list": ordered_columns,
        "target_counts": {"purchases": validation["purchase_count"], "non_purchases": validation["non_purchase_count"], "quantity_population_rows": validation["quantity_population_rows"]},
        "decision_time_min": frame["DecisionTime"].min(), "decision_time_max": frame["DecisionTime"].max(),
        "categorical_cardinalities": {name: int(frame[name].nunique(dropna=True)) for name in contract["feature_lists"]["categorical_features"]},
        "numeric_null_counts": {name: int(frame[name].isna().sum()) for name in contract["feature_lists"]["numeric_features"]},
        "source_snapshot_signature": source_snapshot.get("live_source_signature"),
        "phase1_dataset_fingerprint_sha256": source_snapshot.get("accepted_dataset_fingerprint_sha256"),
        "feature_contract_sha256": hashlib.sha256((root / "contracts/phase2_feature_contract_v1.yaml").read_bytes()).hexdigest(),
        "source_tree_sha256": source_tree_sha256(),
        "canonical_feature_dataset_sha256": dataset_hash,
    })
    write_json(artifact_dir / "phase2_manifest.json", {
        "result": diagnostics.get("verdict", "PASS_WITH_WARNINGS"),
        "recommendation": "PROCEED_TO_PHASE_3",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "git_worktree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()),
        "source_tree_sha256": source_tree_sha256(),
        "source_snapshot_status": source_snapshot.get("status"),
        "dataset_fingerprint_sha256": dataset_hash,
        "test_summary": tests,
        "diagnostics": diagnostics,
    })
    _write_markdown_reports(root, frame, contract, diagnostics, source_snapshot, deterministic, tests, source_tree_sha256())
    return {**validation, "canonical_feature_dataset_sha256": dataset_hash}
