"""Serialization and validation helpers for outbound application envelopes."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from application_contracts.validation import ContractValidationError, validate_document


T = TypeVar("T", bound=BaseModel)


def dump_model(model: BaseModel) -> dict[str, Any]:
    """Dump JSON primitives while retaining schema-required nullable fields.

    Pydantic models use ``None`` for both optional properties and the three
    required nullable authoritative slots.  The checked-in schemas permit the
    former only when omitted, so this small serializer removes optional nulls
    but keeps the required envelope slots and required metric keys.
    """

    raw = model.model_dump(mode="json", exclude_none=False)

    def clean(value: Any, path: tuple[str, ...] = ()) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                keep_null = (path == ("authoritative",) and key in {"model_performance", "business_rule", "capabilities"}) or path[-2:] == ("model_performance", "metrics")
                if item is None and not keep_null:
                    continue
                result[key] = clean(item, path + (str(key),))
            return result
        if isinstance(value, list):
            return [clean(item, path + ("[]",)) for item in value]
        return value

    return clean(raw)


def validate_model(model: T, schema_name: str) -> T:
    """Validate a Pydantic model against the checked-in Phase 1 JSON schema."""

    validate_document(dump_model(model), schema_name)
    return model


def validate_payload(payload: dict[str, Any], schema_name: str) -> dict[str, Any]:
    """Validate and return an outbound JSON document."""

    validate_document(payload, schema_name)
    return payload


def json_bytes(payload: dict[str, Any]) -> bytes:
    """Stable compact JSON for SSE and tests."""

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


__all__ = ["ContractValidationError", "dump_model", "json_bytes", "validate_model", "validate_payload"]
