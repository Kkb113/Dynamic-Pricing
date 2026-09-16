"""Environment-only configuration for local and Databricks App runtimes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

try:  # python-dotenv is a declared runtime dependency.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - keeps minimal imports safe
    load_dotenv = None  # type: ignore[assignment]


class ConfigurationError(ValueError):
    """Raised when local-only runtime configuration is unsafe or invalid."""


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ALLOWED_ORIGINS = frozenset({"http://localhost:5173", "http://127.0.0.1:5173"})
_RUNTIME_MODES = frozenset({"local", "databricks"})


def _is_safe_loopback_origin(value: str) -> bool:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "http"
        and parsed.hostname in _LOOPBACK_HOSTS
        and port is not None
        and 1 <= port <= 65535
        and not parsed.username
        and not parsed.password
        and parsed.path in ("", "/")
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} is outside the supported local range")
    return value


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} is outside the supported local range")
    return value


def _origins() -> tuple[str, ...]:
    raw = os.environ.get("REACT_ORIGIN", "").strip()
    values = tuple(item.strip().rstrip("/") for item in raw.split(",") if item.strip()) if raw else tuple(_ALLOWED_ORIGINS)
    if not values or any(not _is_safe_loopback_origin(value) for value in values):
        raise ConfigurationError("REACT_ORIGIN must contain only loopback HTTP origins with explicit ports")
    return tuple(dict.fromkeys(values))


def _runtime_mode() -> str:
    value = os.environ.get("PRICING_RUNTIME_MODE", "local").strip().casefold() or "local"
    if value not in _RUNTIME_MODES:
        raise ConfigurationError("PRICING_RUNTIME_MODE must be local or databricks")
    return value


@dataclass(frozen=True)
class Settings:
    """Validated, secret-safe application settings.

    ``openai_api_key`` is intentionally excluded from repr/comparison and is
    consumed only by :class:`OpenAIAgentAdapter` inside this process.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    react_origins: tuple[str, ...] = tuple(_ALLOWED_ORIGINS)
    body_limit_bytes: int = 64 * 1024
    openai_timeout_seconds: float = 20.0
    agent_max_turns: int = 4
    request_timeout_seconds: float = 30.0
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    openai_api_key: str | None = field(default=None, repr=False, compare=False)
    openai_model: str | None = None
    runtime_mode: str = "local"
    auth_mode: str = "local_only"
    release_version: str = "unsealed"

    @property
    def agent_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_model)

    @classmethod
    def from_env(cls) -> "Settings":
        # Load only the explicit local file and never override values already
        # supplied by the shell/service manager.  The key remains process-only
        # and is never included in a repr, response, log, or artifact.
        default_root = Path(__file__).resolve().parents[2]
        root_raw = os.environ.get("DYNAMIC_PRICING_ROOT", "").strip()
        root = Path(root_raw).resolve() if root_raw else default_root
        if load_dotenv is not None:
            # Resolve one root first, then load exactly that root's file. This
            # prevents a repository .env from bleeding into an explicitly
            # configured evidence/worktree root.
            load_dotenv(root / ".env", override=False)
        runtime_mode = _runtime_mode()
        default_host = "0.0.0.0" if runtime_mode == "databricks" else "127.0.0.1"
        host = os.environ.get("FASTAPI_HOST", default_host).strip() or default_host
        if runtime_mode == "local" and host not in _LOOPBACK_HOSTS:
            raise ConfigurationError("FASTAPI_HOST must be a loopback address in local mode")
        if runtime_mode == "databricks" and host != "0.0.0.0":
            raise ConfigurationError("FASTAPI_HOST must be 0.0.0.0 in Databricks mode")
        port_name = "DATABRICKS_APP_PORT" if runtime_mode == "databricks" and os.environ.get("DATABRICKS_APP_PORT") else "FASTAPI_PORT"
        key = os.environ.get("OPENAI_API_KEY", "").strip() or None
        model = os.environ.get("OPENAI_MODEL", "").strip() or None
        return cls(
            host=host,
            port=_int_env(port_name, 8000, minimum=1, maximum=65535),
            react_origins=() if runtime_mode == "databricks" else _origins(),
            body_limit_bytes=64 * 1024,
            openai_timeout_seconds=_float_env("OPENAI_TIMEOUT_SECONDS", 20.0, minimum=0.1, maximum=120.0),
            agent_max_turns=_int_env("OPENAI_MAX_TURNS", 4, minimum=1, maximum=8),
            request_timeout_seconds=_float_env("FASTAPI_REQUEST_TIMEOUT_SECONDS", 30.0, minimum=1.0, maximum=180.0),
            root=root,
            openai_api_key=key,
            openai_model=model,
            runtime_mode=runtime_mode,
            auth_mode="databricks_app_identity" if runtime_mode == "databricks" else "local_only",
            release_version=os.environ.get("PRICING_RELEASE_VERSION", "unsealed").strip() or "unsealed",
        )


__all__ = ["ConfigurationError", "Settings"]
