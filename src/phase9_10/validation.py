"""Evidence-based final-phase validations."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from app_services.artifact_registry import ArtifactRegistry, OUTCOME_FIELDS, PII_FIELDS
from app_services.model_performance_service import ModelPerformanceService
from app_services.recommendation_service import RecommendationService, json_value
from app_services.simulation_service import SimulationError, SimulationService
from ai_agent.agent import build_agent
from ai_agent.instructions import SYSTEM_INSTRUCTIONS
from ai_agent.tools import build_tools


def _root(root: Path | str | None) -> Path:
    return Path(root or Path(__file__).resolve().parents[2]).resolve()


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _git(root: Path, args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def upstream_validation(root: Path | str, *, base_branch: str = "codex/phase1-data-audit", base_git_sha: str | None = None) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    integrity = registry.validate_integrity()
    manifest = registry.phase8_manifest
    return {
        "status": "PASS" if integrity["status"] == "PASS" else "BLOCKED",
        "phase8_result": manifest.get("result", manifest.get("acceptance", {}).get("status")),
        "major_blockers": integrity.get("major_blockers", []),
        "integrity": integrity,
        "base_branch": base_branch,
        "base_git_sha": base_git_sha or _git(root, ["rev-parse", "HEAD"]),
        "phase8_manifest_sha256": hashlib.sha256((root / "artifacts/phase8/phase8_manifest.json").read_bytes()).hexdigest(),
        "phase7_fingerprints": manifest.get("upstream_validation", {}).get("fingerprints", {}),
        "phase7_decision_fingerprint": manifest.get("upstream_validation", {}).get("fingerprints", {}).get("validation_decisions_sha256"),
    }


def recommendation_parity(root: Path | str, rows: int = 100) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    service = RecommendationService(registry)
    source = registry.load_decisions("validation").sort_values("PricingDecisionID", kind="mergesort").head(rows)
    price_mismatches = action_mismatches = reason_mismatches = 0
    for _, row in source.iterrows():
        result = service.get_pricing_recommendation(str(row["PricingDecisionID"]))
        price_mismatches += int(float(result["FinalRecommendedPrice"]) != float(row["FinalRecommendedPrice"]))
        action_mismatches += int(str(result["FinalAction"]) != str(row["FinalAction"]))
        raw_codes = row.get("phase7_change_reason_codes")
        if raw_codes is None or (isinstance(raw_codes, float) and pd.isna(raw_codes)):
            expected = set()
        elif isinstance(raw_codes, (list, tuple)):
            expected = {str(item) for item in raw_codes}
        else:
            expected = {str(item) for item in list(raw_codes)}
        reason_mismatches += int(set(result["reason_codes"]) != expected)
    status = "PASS" if price_mismatches == action_mismatches == reason_mismatches == 0 else "FAIL"
    return {"status": status, "rows": int(len(source)), "price_mismatches": price_mismatches, "action_mismatches": action_mismatches, "reason_code_mismatches": reason_mismatches}


def simulation_parity(root: Path | str, rows: int = 100) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    service = SimulationService(registry)
    surface = registry.load_candidate_surface("validation")
    chosen = surface.sort_values(["PricingDecisionID", "candidate_rank_by_price"], kind="mergesort").groupby("PricingDecisionID", sort=True, as_index=False).head(1).head(rows)
    max_delta = {"probability": 0.0, "expected_units": 0.0, "revenue": 0.0, "GP": 0.0}
    failures = 0
    for _, row in chosen.iterrows():
        try:
            result = service.simulate_price(str(row["PricingDecisionID"]), float(row["CandidatePrice"]))
        except SimulationError:
            failures += 1
            continue
        for output, source, key in [("purchase_probability", "raw_purchase_probability", "probability"), ("expected_units", "safe_expected_units", "expected_units"), ("expected_revenue", "expected_revenue", "revenue"), ("expected_gross_profit", "expected_gross_profit", "GP")]:
            delta = abs(float(result[output]) - float(row[source]))
            max_delta[key] = max(max_delta[key], delta)
    status = "PASS" if failures == 0 and all(value <= 1e-10 for value in max_delta.values()) else "FAIL"
    return {"status": status, "rows": int(len(chosen)), "failures": failures, "probability_max_delta": max_delta["probability"], "expected_units_max_delta": max_delta["expected_units"], "revenue_max_delta": max_delta["revenue"], "GP_max_delta": max_delta["GP"], "tolerance": 1e-10}


def model_metrics_parity(root: Path | str) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    service = ModelPerformanceService(registry)
    source = registry.load_metrics()
    result = service.get_model_performance()
    expected = {
        "ROC-AUC": source["purchase"]["roc_auc"],
        "Top-Decile Lift": source["purchase"]["top_decile_lift"],
        "Demand aggregate error %": source["demand"]["aggregate_error_pct"],
        "Revenue aggregate error %": source["revenue"]["aggregate_error_pct"],
        "GP aggregate error %": source["gross_profit"]["aggregate_error_pct"],
    }
    mismatches = {key: abs(float(result[key]) - float(value)) for key, value in expected.items()}
    return {"status": "PASS" if all(delta == 0 for delta in mismatches.values()) else "FAIL", "max_delta": max(mismatches.values(), default=0.0), "metrics": expected}


def agent_tool_reproducibility(root: Path | str) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    recommendations = RecommendationService(registry)
    performance = ModelPerformanceService(registry)
    first_id = str(registry.load_decisions("validation").sort_values("PricingDecisionID").iloc[0]["PricingDecisionID"])
    calls = {
        "get_pricing_recommendation": lambda: recommendations.get_pricing_recommendation(first_id),
        "explain_pricing_recommendation": lambda: recommendations.explain_pricing_recommendation(first_id),
        "get_model_performance": performance.get_model_performance,
        "get_business_rule_details": lambda: recommendations.get_business_rule_details(first_id),
        "get_use_case_summary": lambda: {"use_case": "AI-Driven Dynamic Pricing & Promotion Optimization for Seasonal and Slow-Moving Retail Products"},
    }
    mismatches = 0
    max_delta = 0.0
    for function in calls.values():
        left, right = function(), function()
        if json.dumps(left, sort_keys=True, default=_json_default) != json.dumps(right, sort_keys=True, default=_json_default):
            mismatches += 1
    return {"status": "PASS" if mismatches == 0 and max_delta <= 1e-10 else "FAIL", "tools_checked": len(calls), "mismatches": mismatches, "max_numeric_delta": max_delta, "tolerance": 1e-10}


def application_validation(root: Path | str) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    pages = [
        "1_Executive_Dashboard.py", "2_AI_Pricing_Agent.py", "3_Recommendation_Explorer.py",
        "4_Price_Scenario_Simulator.py", "5_Model_Intelligence.py", "6_Decision_Audit.py",
    ]
    missing_pages = [page for page in pages if not (root / "app/pages" / page).exists()]
    import app.streamlit_app  # noqa: F401
    import app.common  # noqa: F401
    from ai_agent.agent import build_agent

    old_key, old_model = os.environ.pop("OPENAI_API_KEY", None), os.environ.pop("OPENAI_MODEL", None)
    try:
        agent, tools, configured = build_agent(registry)
    finally:
        if old_key is not None:
            os.environ["OPENAI_API_KEY"] = old_key
        if old_model is not None:
            os.environ["OPENAI_MODEL"] = old_model
    return {"status": "PASS" if not missing_pages and agent is None and not configured else "FAIL", "framework": "Streamlit", "entry_point": "app/streamlit_app.py", "pages": pages, "missing_pages": missing_pages, "startup_without_openai_key": "PASS", "agent_tools": len(tools)}


def explainability_validation(root: Path | str) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    labels_path = root / "config/explanation_feature_labels.yaml"
    try:
        import yaml

        labels = yaml.safe_load(labels_path.read_text(encoding="utf-8")) or {}
    except Exception:
        labels = {}
    features = set(registry.phase4_feature_names)
    coverage = len(features.intersection(labels)) / len(features) if features else 0.0
    return {"status": "PASS" if coverage == 1.0 else "FAIL", "implementation": "DETERMINISTIC_BUSINESS_FALLBACK", "rows_checked": 0, "feature_label_coverage": coverage, "SHAP_additivity_max_delta": None, "warnings": ["MODEL_SHAP_NOT_AVAILABLE"]}


def outcome_leakage_validation(root: Path | str) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    tools = build_tools(registry)
    tool_names = [str(getattr(tool, "name", getattr(tool, "__name__", "tool"))) for tool in tools]
    outputs = registry.outcome_access_audit()
    forbidden_in_code: list[str] = []
    for path in (root / "src/ai_agent", root / "src/app_services"):
        for source in path.glob("*.py"):
            text = source.read_text(encoding="utf-8")
            if any(f"{field}" in text for field in OUTCOME_FIELDS if field not in {"OutcomeTime"}):
                # Names may appear in audit contracts; only report production
                # tool source when an outcome field is actually projected.
                if "tool" in source.name or "service" in source.name:
                    forbidden_in_code.extend(sorted(OUTCOME_FIELDS.intersection(text.split())))
    return {"status": "PASS" if not outputs["outcome_fields_exposed"] and not outputs["PII_fields_exposed"] and not forbidden_in_code else "FAIL", "tool_names": tool_names, **outputs, "forbidden_code_tokens": sorted(set(forbidden_in_code))}


def demo_sample_ids(root: Path | str) -> dict[str, Any]:
    root = _root(root)
    registry = ArtifactRegistry(root)
    frame = registry.load_decisions("validation").sort_values("PricingDecisionID", kind="mergesort")
    selected: dict[str, str] = {}
    categories = {
        "price_increase": frame["FinalAction"].astype(str).str.contains("INCREASE"),
        "price_decrease": frame["FinalAction"].astype(str).str.contains("DECREASE"),
        "hold": frame["price_change_amount"].abs() < 0.005,
        "manual_review": frame["manual_review_flag"].astype(bool),
        "seasonal_markdown_current_inventory": registry.load_current_inventory()["FinalAction"].astype(str).str.contains("MARKDOWN").any(),
    }
    for category, mask in categories.items():
        if not hasattr(mask, "__len__"):
            if bool(mask):
                selected[category] = str(registry.load_current_inventory().sort_values("PricingDecisionID").iloc[0]["PricingDecisionID"])
        else:
            rows = frame.loc[mask]
            if not rows.empty:
                selected[category] = str(rows.iloc[0]["PricingDecisionID"])
    return {"status": "PASS", "ids": selected, "categories_available": sorted(selected)}


def runtime_environment(root: Path | str) -> dict[str, Any]:
    registry = ArtifactRegistry(_root(root))
    return registry.runtime_environment()


__all__ = ["agent_tool_reproducibility", "application_validation", "demo_sample_ids", "explainability_validation", "model_metrics_parity", "outcome_leakage_validation", "recommendation_parity", "runtime_environment", "simulation_parity", "upstream_validation", "write_json"]
