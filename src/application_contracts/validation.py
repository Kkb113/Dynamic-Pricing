"""Dependency-light validation for the Phase 1 application JSON contracts.

The repository stores the contracts as JSON Schema so a FastAPI implementation
may use a standards-compliant validator.  This module keeps contract tests
portable in the frozen evidence environment, where optional web dependencies
are intentionally not installed yet.  It implements the subset used by these
schemas and adds cross-field chart invariants that JSON Schema alone cannot
express.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts" / "application"


class ContractValidationError(ValueError):
    """Raised when a contract document is invalid."""

    def __init__(self, message: str, path: str = "$", *, errors: list[str] | None = None):
        self.path = path
        self.errors = errors or [f"{path}: {message}"]
        super().__init__(self.errors[0])


def load_schema(schema_name: str) -> dict[str, Any]:
    """Load a checked-in application schema by filename."""

    path = CONTRACT_DIR / schema_name
    if path.parent != CONTRACT_DIR or path.suffix != ".json":
        raise ValueError(f"Unsupported schema path: {schema_name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Unknown application schema: {schema_name}") from exc


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _pointer(root: Any, fragment: str) -> Any:
    if fragment in ("", "#"):
        return root
    if fragment.startswith("#"):
        fragment = fragment[1:]
    if not fragment.startswith("/"):
        raise ValueError(f"Unsupported JSON pointer: #{fragment}")
    value = root
    for token in fragment[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            value = value[int(token)]
        else:
            value = value[token]
    return value


def _resolve_ref(ref: str, *, current_path: Path, root_schema: dict[str, Any]) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    if ref.startswith("#"):
        return _pointer(root_schema, ref), current_path, root_schema
    filename, _, fragment = ref.partition("#")
    external_path = (current_path.parent / filename).resolve()
    external_root = json.loads(external_path.read_text(encoding="utf-8"))
    return _pointer(external_root, f"#{fragment}" if fragment else "#"), external_path, external_root


def _validate(value: Any, schema: dict[str, Any], *, path: str, current_path: Path, root_schema: dict[str, Any]) -> list[str]:
    if "$ref" in schema:
        resolved, resolved_path, resolved_root = _resolve_ref(schema["$ref"], current_path=current_path, root_schema=root_schema)
        return _validate(value, resolved, path=path, current_path=resolved_path, root_schema=resolved_root)

    failures: list[str] = []
    if "const" in schema and value != schema["const"]:
        failures.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        failures.append(f"{path}: {value!r} is not one of {schema['enum']!r}")

    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        actual = _json_type(value)
        matches = actual in expected_types or (actual == "integer" and "number" in expected_types)
        if not matches:
            return failures + [f"{path}: expected {expected_types}, got {actual}"]

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            failures.append(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            failures.append(f"{path}: longer than maxLength")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            failures.append(f"{path}: does not match pattern")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            failures.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            failures.append(f"{path}: above maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            failures.append(f"{path}: must be greater than exclusiveMinimum")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            failures.append(f"{path}: must be less than exclusiveMaximum")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            failures.append(f"{path}: fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            failures.append(f"{path}: more than maxItems")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(set(encoded)) != len(encoded):
                failures.append(f"{path}: items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                failures.extend(_validate(item, item_schema, path=f"{path}[{index}]", current_path=current_path, root_schema=root_schema))

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                failures.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            failures.extend(f"{path}: additional property {key!r} is not allowed" for key in unknown)
        for key, child_schema in properties.items():
            if key in value:
                failures.extend(_validate(value[key], child_schema, path=f"{path}.{key}", current_path=current_path, root_schema=root_schema))

    if "allOf" in schema:
        for child in schema["allOf"]:
            failures.extend(_validate(value, child, path=path, current_path=current_path, root_schema=root_schema))
    if "oneOf" in schema:
        matches = 0
        branch_failures: list[str] = []
        for child in schema["oneOf"]:
            child_errors = _validate(value, child, path=path, current_path=current_path, root_schema=root_schema)
            if not child_errors:
                matches += 1
            else:
                branch_failures.extend(child_errors[:1])
        if matches != 1:
            failures.append(f"{path}: oneOf matched {matches} schemas")
            failures.extend(branch_failures[:3])
    return failures


def _semantic_chart_checks(chart: dict[str, Any], *, path: str) -> list[str]:
    failures: list[str] = []
    chart_type = chart.get("type")
    x_field = chart.get("x_axis", {}).get("field")
    if chart_type == "line" and x_field != "candidate_price":
        failures.append(f"{path}.x_axis.field: line charts must use candidate_price")
    if chart_type == "bar" and x_field not in {"scenario", "final_action"}:
        failures.append(f"{path}.x_axis.field: bar charts must use scenario or final_action")
    series = {item.get("field") for item in chart.get("series", [])}
    for index, point in enumerate(chart.get("points", [])):
        point_fields = [item.get("field") for item in point.get("values", [])]
        unknown = sorted(set(point_fields) - series)
        failures.extend(f"{path}.points[{index}]: field {field!r} is not declared in series" for field in unknown)
    source_status = chart.get("source", {}).get("data_status")
    if source_status == "model_implied" and chart.get("model_implied") is not True:
        failures.append(f"{path}.model_implied: model_implied data must be labelled true")
    return failures


def validate_document(document: Any, schema_name: str) -> None:
    """Validate a document and raise :class:`ContractValidationError` on failure."""

    schema = load_schema(schema_name)
    failures = _validate(document, schema, path="$", current_path=CONTRACT_DIR / schema_name, root_schema=schema)
    if schema_name == "chart_spec_v1.schema.json" and isinstance(document, dict):
        failures.extend(_semantic_chart_checks(document, path="$"))
    if schema_name == "pricing_chat_response_v1.schema.json" and isinstance(document, dict):
        for index, chart in enumerate(document.get("charts", [])):
            failures.extend(_semantic_chart_checks(chart, path=f"$.charts[{index}]"))
            if chart.get("source", {}).get("tool_name") not in document.get("tools_used", []):
                failures.append(f"$.charts[{index}].source.tool_name: source tool must be listed in tools_used")
    if failures:
        raise ContractValidationError(failures[0].split(": ", 1)[-1], errors=failures)


__all__ = ["CONTRACT_DIR", "ContractValidationError", "load_schema", "validate_document"]
