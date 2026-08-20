"""Environment-only configuration for the local FastAPI process."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when local-only runtime configuration is unsafe or invalid."""


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ALLOWED_ORIGINS = frozenset({"http://localhost:5173", "http://127.0.0.1:5173"})


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
    values = tuple(item.strip() for item in raw.split(",") if item.strip()) if raw else tuple(_ALLOWED_ORIGINS)
    if not values or any(value not in _ALLOWED_ORIGINS for value in values):
        raise ConfigurationError("REACT_ORIGIN must contain only the two supported loopback origins")
    return tuple(dict.fromkeys(values))


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

    @property
    def agent_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_model)

    @classmethod
    def from_env(cls) -> "Settings":
        host = os.environ.get("FASTAPI_HOST", "127.0.0.1").strip() or "127.0.0.1"
        if host not in _LOOPBACK_HOSTS:
            raise ConfigurationError("FASTAPI_HOST must be a loopback address")
        root_raw = os.environ.get("DYNAMIC_PRICING_ROOT", "").strip()
        root = Path(root_raw).resolve() if root_raw else Path(__file__).resolve().parents[2]
        key = os.environ.get("OPENAI_API_KEY", "").strip() or None
        model = os.environ.get("OPENAI_MODEL", "").strip() or None
        return cls(
            host=host,
            port=_int_env("FASTAPI_PORT", 8000, minimum=1, maximum=65535),
            react_origins=_origins(),
            body_limit_bytes=64 * 1024,
            openai_timeout_seconds=_float_env("OPENAI_TIMEOUT_SECONDS", 20.0, minimum=0.1, maximum=120.0),
            agent_max_turns=_int_env("OPENAI_MAX_TURNS", 4, minimum=1, maximum=8),
            request_timeout_seconds=_float_env("FASTAPI_REQUEST_TIMEOUT_SECONDS", 30.0, minimum=1.0, maximum=180.0),
            root=root,
            openai_api_key=key,
            openai_model=model,
        )


__all__ = ["ConfigurationError", "Settings"]
