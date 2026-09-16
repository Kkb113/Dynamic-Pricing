"""Secret-safe local release preflight for the Phase 4 operator workflow.

The preflight is deliberately descriptive rather than diagnostic: it reports
only booleans, allowlisted identifiers, dependency versions, and stable action
codes.  It never reads or serializes an OpenAI key value, an ``.env`` file, or
provider error text.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import ConfigurationError, Settings
from .services import ServiceContainer

_SAFE_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def safe_model_id(value: str | None) -> str:
    """Return a model identifier only when it is safe to display."""

    candidate = (value or "").strip()
    if candidate and _SAFE_MODEL.fullmatch(candidate) and not any(
        marker in candidate.casefold() for marker in ("key", "secret", "token", "password")
    ):
        return candidate
    return "redacted_model_id" if candidate else "not_configured"


def _version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except Exception:
        return "not_installed"


def _loopback_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and parsed.hostname in _LOOPBACK_HOSTS
    except Exception:
        return False


def build_preflight(
    settings: Settings | None = None,
    *,
    repo_root: Path | None = None,
    frontend_root: Path | None = None,
) -> dict[str, Any]:
    """Build a redacted, JSON-serializable local readiness report."""

    app_settings = settings or Settings.from_env()
    root = (repo_root or app_settings.root).resolve()
    frontend = (frontend_root or root / "frontend").resolve()
    failures: list[str] = []

    key_configured = bool(app_settings.openai_api_key)
    model_configured = bool(app_settings.openai_model)
    sdk_version = _version("openai-agents")
    sdk_installed = sdk_version != "not_installed"
    if not key_configured:
        failures.append("OPENAI_API_KEY_NOT_CONFIGURED")
    if not model_configured:
        failures.append("OPENAI_MODEL_NOT_CONFIGURED")
    if not sdk_installed:
        failures.append("OPENAI_AGENTS_SDK_NOT_INSTALLED")
    if app_settings.host not in _LOOPBACK_HOSTS:
        failures.append("BACKEND_HOST_NOT_LOOPBACK")

    artifact_status = "unknown"
    try:
        services = ServiceContainer.create(root)
        artifact_status = "pass" if bool(getattr(services, "ready", False)) else "blocked"
    except Exception:
        artifact_status = "blocked"
    if artifact_status != "pass":
        failures.append("ARTIFACT_INTEGRITY_BLOCKED")

    frontend_lock = (frontend / "package-lock.json").is_file()
    frontend_build = (frontend / "dist" / "index.html").is_file()
    if not frontend_lock:
        failures.append("FRONTEND_LOCKFILE_MISSING")
    if not frontend_build:
        failures.append("FRONTEND_BUILD_MISSING")

    live_ready = key_configured and model_configured and sdk_installed and artifact_status == "pass"
    if not live_ready:
        mode = "blocked" if artifact_status != "pass" else "deterministic_fallback"
        live_gate = "BLOCKED"
    else:
        mode = "live_ready"
        live_gate = "PASS"

    return {
        "phase": "phase4",
        "status": "PASS" if artifact_status == "pass" and app_settings.host in _LOOPBACK_HOSTS else "BLOCKED",
        "mode": mode,
        "live_gate": live_gate,
        "blockers": failures,
        "configuration": {
            "openai_api_key_configured": key_configured,
            "openai_model_configured": model_configured,
            "model_id": safe_model_id(app_settings.openai_model),
            "backend_host": app_settings.host,
            "backend_port": app_settings.port,
            "frontend_origin_allowlist": list(app_settings.react_origins),
            "openai_max_turns": app_settings.agent_max_turns,
            "openai_timeout_seconds": app_settings.openai_timeout_seconds,
        },
        "dependencies": {
            "python": platform.python_version(),
            "openai_agents": sdk_version,
            "fastapi": _version("fastapi"),
            "pydantic": _version("pydantic"),
            "uvicorn": _version("uvicorn"),
            "httpx": _version("httpx"),
        },
        "artifacts": {"integrity": artifact_status},
        "frontend": {
            "root": "frontend",
            "lockfile_present": frontend_lock,
            "production_build_present": frontend_build,
        },
        "local_only": {
            "backend_loopback": app_settings.host in _LOOPBACK_HOSTS,
            "allowed_api_base_examples": ["http://127.0.0.1:8000", "http://localhost:8000"],
            "persistence": False,
            "hosting": False,
            "authentication": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a secret-safe local Phase 4 preflight report")
    parser.add_argument("--json", action="store_true", help="accepted for script symmetry; JSON is always emitted")
    args = parser.parse_args(argv)
    del args
    try:
        report = build_preflight()
    except ConfigurationError:
        # Keep config failures stable and value-free.  The caller can inspect
        # the key/model booleans only after fixing the local environment.
        report = {
            "phase": "phase4",
            "status": "BLOCKED",
            "mode": "blocked",
            "live_gate": "BLOCKED",
            "blockers": ["LOCAL_CONFIGURATION_INVALID"],
            "configuration": {"openai_api_key_configured": False, "openai_model_configured": False, "model_id": "not_configured"},
        }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report.get("status") == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["build_preflight", "main", "safe_model_id"]
