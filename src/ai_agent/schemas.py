"""Small typed schemas used by the agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    status: str = "ok"


def compact_tool_output(value: Any) -> Any:
    """Keep tool responses JSON-safe without passing datasets to the model."""

    if isinstance(value, list):
        return value[:100]
    if isinstance(value, dict):
        return {key: compact_tool_output(item) for key, item in value.items()}
    return value


__all__ = ["ToolCallRecord", "compact_tool_output"]
