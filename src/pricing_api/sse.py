"""SSE framing for the versioned pricing chat stream."""

from __future__ import annotations

import json
from typing import Any

from .contracts import validate_payload


def event_payload(event: str, request_id: str, sequence: int, payload: dict[str, Any]) -> dict[str, Any]:
    document = {
        "schema_version": "pricing.chat.sse.v1",
        "event": event,
        "request_id": request_id,
        "sequence": sequence,
        "payload": payload,
    }
    return validate_payload(document, "pricing_chat_sse_event_v1.schema.json")


def format_sse(document: dict[str, Any]) -> str:
    """Return one standard SSE event with exactly one JSON data line."""

    return f"event: {document['event']}\ndata: {json.dumps(document, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}\n\n"


__all__ = ["event_payload", "format_sse"]
