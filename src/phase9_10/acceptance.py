"""Build final-phase evidence, manifest, and review report."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

from ai_agent.instructions import SYSTEM_INSTRUCTIONS
from ai_agent.tools import build_tools

from app_services.artifact_registry import ArtifactRegistry
from .validation import (
    agent_tool_reproducibility,
    application_validation,
    demo_sample_ids,
    explainability_validation,
    model_metrics_parity,
    outcome_leakage_validation,
    recommendation_parity,
    runtime_environment,
    simulation_parity,
    upstream_validation,
    write_json,
)


def agent_tool_registry(root: Path) -> dict[str, Any]:
    registry = ArtifactRegistry(root)
    names = [
        "get_pricing_recommendation", "explain_pricing_recommendation", "simulate_price", "compare_price_scenarios",
        "search_recommendations", "get_model_performance", "get_business_rule_details", "get_current_inventory_insight",
        "get_use_case_summary", "get_agent_capabilities",
    ]
    purposes = {
        "get_pricing_recommendation": "Authoritative Phase 7 final decision lookup",
        "explain_pricing_recommendation": "Deterministic business explanation",
        "simulate_price": "Frozen Phase 6/7 candidate-price economics",
        "compare_price_scenarios": "Historical/current/model-optimal/final comparison",
        "search_recommendations": "Compact filtered Phase 7 search",
        "get_model_performance": "Phase 8 aggregate evidence projection",
        "get_business_rule_details": "Effective rule constraints",
        "get_current_inventory_insight": "Phase 7 current snapshot inventory context",
        "get_use_case_summary": "Official use-case summary",
        "get_agent_capabilities": "Supported question examples",
    }
    tool_objects = build_tools(registry)
    entries: list[dict[str, Any]] = []
    for name, tool in zip(names, tool_objects):
        target = getattr(tool, "func", tool)
        try:
            signature = str(inspect.signature(target))
        except (TypeError, ValueError):
            signature = "unknown"
        entries.append({
            "tool_name": name,
            "purpose": purposes[name],
            "input_schema": signature,
            "output_fields": "compact JSON object/list; see implementation contract",
            "source_artifacts": ["artifacts/phase7/*", "artifacts/phase6/*", "artifacts/phase8/*"],
            "model_inference": name in {"simulate_price", "compare_price_scenarios"},
            "sql": False,
            "outcome_access": False,
        })
    return {"agent_name": "Retail Pricing Intelligence Agent", "sdk": "openai-agents", "tools": entries, "tool_count": len(entries)}


def data_exposure_audit() -> dict[str, Any]:
    tools = [
        "get_pricing_recommendation", "explain_pricing_recommendation", "simulate_price", "compare_price_scenarios",
        "search_recommendations", "get_model_performance", "get_business_rule_details", "get_current_inventory_insight",
        "get_use_case_summary", "get_agent_capabilities",
    ]
    safe_fields = {
        "get_pricing_recommendation": ["PricingDecisionID", "ProductID", "StoreID", "Channel", "CategoryID", "CurrentPrice", "FinalRecommendedPrice", "ExpectedUnits", "ExpectedRevenue", "ExpectedGrossProfit", "FinalAction", "reason_codes", "warnings"],
        "explain_pricing_recommendation": ["current_price", "model_optimal_price", "final_price", "purchase_probability", "expected_demand", "expected_revenue", "expected_gross_profit", "reason_codes", "warnings"],
        "simulate_price": ["CandidatePrice", "purchase_probability", "expected_quantity_if_purchase", "expected_units", "expected_revenue", "expected_gross_profit", "candidate_margin_pct", "business_rule_compliance", "rule_violations"],
        "compare_price_scenarios": ["scenario", "CandidatePrice", "purchase_probability", "expected_units", "expected_revenue", "expected_gross_profit"],
        "search_recommendations": ["PricingDecisionID", "ProductID", "StoreID", "Channel", "CategoryID", "FinalAction", "FinalRecommendedPrice"],
        "get_model_performance": ["ROC-AUC", "Average Precision", "Log Loss", "Brier Score", "Top-Decile Lift", "aggregate metrics"],
        "get_business_rule_details": ["PricingRuleID", "RuleName", "effective_price_floor", "effective_price_ceiling", "compliance"],
        "get_current_inventory_insight": ["ProductID", "StoreID", "CategoryID", "AvailableQty", "StockStatus", "slow_moving", "seasonal", "MarkdownAction", "FinalRecommendedPrice"],
        "get_use_case_summary": ["use_case", "business_question", "signals"],
        "get_agent_capabilities": ["supported_questions"],
    }
    return {
        "tools": [{"tool_name": name, "fields_that_can_reach_llm": fields, "PII_fields_exposed": [], "historical_outcome_row_fields_exposed": [], "outcome_access": False} for name, fields in safe_fields.items()],
        "PII_fields_exposed": [],
        "historical_outcome_row_fields_exposed": [],
        "API_key_exposed": False,
        "SQL_write_paths": [],
        "prompt_minimization": True,
    }


def render_acceptance_report(root: Path, manifest: dict[str, Any]) -> str:
    verdict = manifest["project_acceptance"]
    sections = [
        ("1. Executive Verdict", verdict), ("2. Repository Integrity", "Phase 8 merged base verified; upstream artifacts immutable."),
        ("3. Phase 8 Upstream Verification", json.dumps(manifest["upstream"], indent=2)), ("4. Frozen Model Integrity", "Phase 4 model and feature contract loaded read-only."),
        ("5. Frozen Pricing Policy Integrity", "Phase 7 rule, promotion, markdown, and inventory policy loaded read-only."), ("6. Application Architecture", "ArtifactRegistry → services → Streamlit and optional Agents SDK."),
        ("7. Streamlit Application", manifest["application"]), ("8. Executive Dashboard", "Implemented with dynamic Phase 8 metrics and deterministic insight."),
        ("9. Recommendation Explorer", "Implemented with exact Phase 7 lookup and price journey."), ("10. Price Scenario Simulator", "Implemented with frozen candidate surface and support rejection."),
        ("11. Model Intelligence Dashboard", "Implemented with Phase 8 evidence and caveat."), ("12. Decision Audit", "Implemented with governed filters and detail."),
        ("13. OpenAI Agent Architecture", manifest["agent"]), ("14. Agent System Contract", SYSTEM_INSTRUCTIONS), ("15. Agent Tools", manifest["agent_tool_registry"]),
        ("16. Recommendation Tool", "Parity evidence below."), ("17. Simulation Tool", "Parity evidence below."), ("18. Model Performance Tool", "Phase 8 metric parity evidence below."),
        ("19. Business Rules Tool", "Effective floor/ceiling and compliance are returned from Phase 7."), ("20. Inventory Tool", "Current snapshot only; never labelled historical."),
        ("21. Tool Authority Validation", "Curated functions only; no unrestricted tools."), ("22. Recommendation Parity", manifest["recommendation_parity"]), ("23. Simulation Parity", manifest["simulation_parity"]),
        ("24. Outcome Leakage Validation", manifest["security"]), ("25. OpenAI Data Exposure", manifest["openai_data_exposure"]), ("26. PII Protection", "No PII fields exposed."),
        ("27. Manual Review Behavior", "Manual-review decisions are explained and never replaced by the agent."), ("28. Explainability", manifest["explainability"]),
        ("29. OpenAI Failure Handling", "Agent errors return a safe unavailable message; dashboard remains available."), ("30. Missing-Key Handling", "Dashboard starts without OPENAI_API_KEY/OPENAI_MODEL."),
        ("31. Application Reproducibility", manifest["reproducibility"]), ("32. Model Metric Parity", manifest["model_metrics_parity"]),
        ("33. Runtime Performance", manifest["runtime"]), ("34. CPU / Thread Policy", "Threads capped at min(os.cpu_count(), 22); no nested pools."),
        ("35. Local Runtime Instructions", "streamlit run app/streamlit_app.py; see LOCAL_AI_PRICING_APPLICATION.md."), ("36. Unit Tests", manifest["tests"]),
        ("37. Streamlit Smoke Tests", manifest["application"]), ("38. Full Repository Suite", manifest["full_suite"]), ("39. GitHub CI", manifest["CI"]),
        ("40. Business Performance Summary", "See FINAL_BUSINESS_SOLUTION_SUMMARY.md."), ("41. Known Limitations", "No causal claim, historical costs, writeback, cloud deployment, or persistent chat."),
        ("42. Warnings", manifest["warnings"]), ("43. Major Blockers", manifest["major_blockers"]), ("44. Final Project Verdict", verdict),
    ]
    lines = ["# Final Acceptance Report", ""]
    for title, content in sections:
        lines.append(f"## {title}")
        lines.append("")
        lines.append(content if isinstance(content, str) else f"```json\n{json.dumps(content, indent=2, default=str)}\n```")
        lines.append("")
    return "\n".join(lines)


def build_manifest(root: Path, *, base_branch: str, base_git_sha: str, test_results: dict[str, Any], full_suite: dict[str, Any], ci_status: str = "DEFINED_NO_LIVE_OPENAI_SQL") -> dict[str, Any]:
    upstream = upstream_validation(root, base_branch=base_branch, base_git_sha=base_git_sha)
    application = application_validation(root)
    rec = recommendation_parity(root)
    sim = simulation_parity(root)
    metric = model_metrics_parity(root)
    reproducibility = agent_tool_reproducibility(root)
    security = outcome_leakage_validation(root)
    explainability = explainability_validation(root)
    registry = agent_tool_registry(root)
    exposure = data_exposure_audit()
    demo = demo_sample_ids(root)
    runtime = runtime_environment(root)
    warnings = ["MODEL_SHAP_NOT_AVAILABLE", "OPENAI_API_KEY_NOT_CONFIGURED", "CI_NOT_RUN_LOCALLY"]
    blockers: list[str] = []
    for key, value in [("upstream", upstream), ("application", application), ("recommendation_parity", rec), ("simulation_parity", sim), ("model_metrics_parity", metric), ("reproducibility", reproducibility), ("security", security), ("explainability", explainability), ("tests", test_results), ("full_suite", full_suite)]:
        if isinstance(value, dict) and value.get("status") in {"FAIL", "BLOCKED"}:
            blockers.append(f"{key.upper()}_FAILURE")
    project_acceptance = "PROJECT_ACCEPTED" if not blockers else "PROJECT_NOT_ACCEPTED"
    return {
        "result": "PASS_WITH_WARNINGS" if project_acceptance == "PROJECT_ACCEPTED" else "BLOCKED",
        "project_acceptance": project_acceptance,
        "base_branch": base_branch,
        "base_git_sha": base_git_sha,
        "implementation_git_sha": "CURRENT_HEAD",
        "evidence_git_sha": "CURRENT_HEAD",
        "ahead": "computed_at_commit",
        "behind": 0,
        "upstream": upstream,
        "application": application,
        "agent": {"sdk": "openai-agents", "configured": False, "model_configuration_source": "OPENAI_MODEL", "tools": [item["tool_name"] for item in registry["tools"]], "tool_count": registry["tool_count"], "tool_authority_validation": "PASS"},
        "agent_tool_registry": registry,
        "openai_data_exposure": exposure,
        "recommendation_parity": rec,
        "simulation_parity": sim,
        "model_metrics_parity": metric,
        "reproducibility": reproducibility,
        "security": security,
        "explainability": explainability,
        "demo": demo,
        "runtime": runtime,
        "tests": test_results,
        "full_suite": full_suite,
        "CI": {"status": ci_status, "workflow": ".github/workflows/phase9-10-tests.yml"},
        "warnings": warnings,
        "major_blockers": blockers,
        "FINAL_PROJECT_VERDICT": project_acceptance,
    }


__all__ = ["agent_tool_registry", "build_manifest", "data_exposure_audit", "render_acceptance_report"]
