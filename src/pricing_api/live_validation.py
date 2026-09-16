"""Bounded, redacted live/fallback validation for the local pricing API.

This module intentionally records no narrative, business values, request IDs,
prompts, tool arguments/results, provider headers, or secret material.  The
output is an operator gate, not a transcript.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from .config import Settings
from .contracts import validate_payload
from .models import HealthResponse, PricingChatResponse
from .preflight import safe_model_id
from .tools import TOOL_NAMES

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_SECRET_MARKERS = ("openai_api_key", "authorization", "bearer ", "sk-", "hidden reasoning", "chain of thought")


def _safe_url(base_url: str) -> bool:
    try:
        parsed = urlparse(base_url)
        return parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS
    except Exception:
        return False


def _response_hash(payload: dict[str, Any]) -> str:
    """Hash only structural/redacted response facts, never business values."""

    authoritative = payload.get("authoritative") if isinstance(payload.get("authoritative"), dict) else {}
    projection = {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "answer_source": payload.get("answer_source"),
        "numeric_claims_source": authoritative.get("numeric_claims_source"),
        "recommendation_count": len(authoritative.get("recommendations", [])) if isinstance(authoritative.get("recommendations"), list) else 0,
        "scenario_count": len(authoritative.get("scenario_comparisons", [])) if isinstance(authoritative.get("scenario_comparisons"), list) else 0,
        "inventory_count": len(authoritative.get("inventory_insights", [])) if isinstance(authoritative.get("inventory_insights"), list) else 0,
        "chart_count": len(payload.get("charts", [])) if isinstance(payload.get("charts"), list) else 0,
        "tools_used": [item for item in payload.get("tools_used", []) if item in TOOL_NAMES],
        "warning_codes": [item.get("code") for item in payload.get("warnings", []) if isinstance(item, dict)],
        "error_codes": [item.get("code") for item in payload.get("errors", []) if isinstance(item, dict)],
    }
    encoded = json.dumps(projection, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _leak_checks(payload: dict[str, Any]) -> dict[str, bool]:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).casefold()
    return {
        "no_secret_or_provider_markers": not any(marker in encoded for marker in _SECRET_MARKERS),
        "no_raw_tool_payload": all(
            key not in encoded for key in ("candidateprice", "pricingdecisionid", "tool_arguments", "raw_item")
        ),
        "no_hidden_reasoning": "reasoning" not in encoded and "chain of thought" not in encoded,
    }


def _base_report(settings: Settings, *, base_url: str) -> dict[str, Any]:
    return {
        "phase": "phase4",
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url_loopback": _safe_url(base_url),
        "configured_model_id": safe_model_id(settings.openai_model),
        "openai_api_key_configured": bool(settings.openai_api_key),
        "openai_model_configured": bool(settings.openai_model),
        "api_calls": 0,
        "health_http_status": None,
        "chat_http_status": None,
        "health_agent_available": False,
        "answer_source": None,
        "agent_tool_names": [],
        "agent_tool_count": 0,
        "authoritative_numeric_source": False,
        "schema_validation": False,
        "leak_checks": {"no_secret_or_provider_markers": True, "no_raw_tool_payload": True, "no_hidden_reasoning": True},
        "fallback_functional": False,
        "latency_ms": None,
        "response_hash": None,
        "evidence_hash": None,
        "status": "BLOCKED",
        "live_gate": "BLOCKED",
        "block_reason": None,
    }


def run_live_validation(
    *,
    base_url: str = "http://127.0.0.1:8000",
    settings: Settings | None = None,
    output: Path | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run health + one capability call and emit a redacted gate report."""

    app_settings = settings or Settings.from_env()
    report = _base_report(app_settings, base_url=base_url.rstrip("/"))
    if not report["base_url_loopback"]:
        report["block_reason"] = "API_BASE_NOT_LOOPBACK"
        return _finalize(report, output)
    if not app_settings.openai_api_key or not app_settings.openai_model:
        report["block_reason"] = "OPENAI_KEY_OR_MODEL_NOT_CONFIGURED"
        return _finalize(report, output)

    factory = client_factory or httpx.Client
    started = perf_counter()
    try:
        with factory(base_url=base_url.rstrip("/"), timeout=app_settings.request_timeout_seconds, headers={"Accept": "application/json"}) as client:
            health_response = client.get("/api/v1/healthz")
            report["api_calls"] = 1
            report["health_http_status"] = int(getattr(health_response, "status_code", 0))
            health_payload = health_response.json()
            health = HealthResponse.model_validate(health_payload)
            report["schema_validation"] = True
            report["health_agent_available"] = health.agent_available
            if report["health_http_status"] != 200:
                report["block_reason"] = "HEALTH_HTTP_NOT_READY"
                return _finalize(report, output, started=started)
            if health.status != "ready" or health.artifacts_integrity != "pass":
                report["block_reason"] = "ARTIFACT_INTEGRITY_BLOCKED"
                return _finalize(report, output, started=started)
            if not health.agent_available:
                report["block_reason"] = "AGENT_NOT_AVAILABLE"
                return _finalize(report, output, started=started)
            chat_response = client.post(
                "/api/v1/pricing/chat",
                json={"schema_version": "pricing.chat.request.v1", "message": "What can you do?"},
            )
            report["api_calls"] = 2
            report["chat_http_status"] = int(getattr(chat_response, "status_code", 0))
            if report["chat_http_status"] != 200:
                report["schema_validation"] = False
                report["status"] = "FAIL"
                report["live_gate"] = "FAIL"
                report["block_reason"] = "CHAT_HTTP_FAILED"
                return _finalize(report, output, started=started)
            payload = chat_response.json()
            response = PricingChatResponse.model_validate(payload)
            validate_payload(payload, "pricing_chat_response_v1.schema.json")
            report["schema_validation"] = True
            report["answer_source"] = response.answer_source
            names_header = str(chat_response.headers.get("X-Pricing-Agent-Tools", ""))
            names = [item.strip() for item in names_header.split(",") if item.strip()]
            names_valid = bool(names) and all(item in TOOL_NAMES for item in names)
            report["agent_tool_names"] = list(dict.fromkeys(names))
            report["agent_tool_count"] = len(report["agent_tool_names"])
            report["authoritative_numeric_source"] = response.authoritative.numeric_claims_source == "deterministic_local_tools"
            report["leak_checks"] = _leak_checks(payload)
            report["fallback_functional"] = response.answer_source == "deterministic_fallback" or response.status in {"completed", "partial"}
            report["response_hash"] = _response_hash(payload)
            grounded_agent = (
                report["chat_http_status"] == 200
                and health.agent_available
                and response.answer_source == "agent"
                and chat_response.headers.get("X-Pricing-Agent-SDK-Success") == "true"
                and names_valid
            )
            if not all(report["leak_checks"].values()) or not report["authoritative_numeric_source"]:
                report["status"] = "FAIL"
                report["live_gate"] = "FAIL"
                report["block_reason"] = "GROUNDING_OR_LEAK_CHECK_FAILED"
            elif response.answer_source != "agent":
                report["status"] = "FALLBACK"
                report["live_gate"] = "BLOCKED"
                report["block_reason"] = "AGENT_FALLBACK_ACTIVE"
            elif not grounded_agent:
                report["status"] = "FAIL"
                report["live_gate"] = "FAIL"
                report["block_reason"] = "GROUNDING_OR_LEAK_CHECK_FAILED"
            elif response.answer_source == "agent":
                report["status"] = "PASS"
                report["live_gate"] = "PASS"
            else:
                report["status"] = "FALLBACK"
                report["live_gate"] = "BLOCKED"
                report["block_reason"] = "AGENT_FALLBACK_ACTIVE"
    except Exception:
        # Never serialize the provider/HTTP exception: it may contain a URL,
        # request body, response headers, or account-specific details.
        report["status"] = "FAIL"
        report["live_gate"] = "FAIL"
        report["block_reason"] = "LOCAL_VALIDATION_REQUEST_FAILED"
    return _finalize(report, output, started=started)


def _finalize(report: dict[str, Any], output: Path | None, *, started: float | None = None) -> dict[str, Any]:
    if started is not None:
        report["latency_ms"] = round((perf_counter() - started) * 1000, 2)
    safe_for_hash = dict(report)
    safe_for_hash["evidence_hash"] = None
    encoded = json.dumps(safe_for_hash, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    report["evidence_hash"] = hashlib.sha256(encoded).hexdigest()
    if output is not None:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one bounded redacted local pricing validation")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase4_application/live_validation.json"))
    args = parser.parse_args(argv)
    report = run_live_validation(base_url=args.base_url, output=args.output)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] in {"PASS", "FALLBACK", "BLOCKED"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["run_live_validation", "main"]
