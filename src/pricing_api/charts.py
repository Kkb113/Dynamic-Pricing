"""Backend-authored chart specifications derived only from authoritative data."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from .contracts import validate_model
from .models import AuthoritativeData


class ChartModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChartAxis(ChartModel):
    field: str
    label: str
    value_type: str
    unit: str = "none"


class ChartSeries(ChartModel):
    field: str
    label: str
    unit: str
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ChartPointValue(ChartModel):
    field: str
    value: float | None


class ChartPoint(ChartModel):
    x: float | str
    values: list[ChartPointValue] = Field(min_length=1, max_length=3)


class ChartSource(ChartModel):
    tool_name: str
    record_path: str = Field(pattern=r"^[A-Za-z0-9._\[\]-]{1,160}$")
    data_status: str


class ChartSpec(ChartModel):
    schema_version: str = "pricing.chart.v1"
    chart_id: str = Field(pattern=r"^chart_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    type: str
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=400)
    x_axis: ChartAxis
    series: list[ChartSeries] = Field(min_length=1, max_length=3)
    points: list[ChartPoint] = Field(min_length=1, max_length=200)
    source: ChartSource
    model_implied: bool


_SERIES_META: dict[str, tuple[str, str, str]] = {
    "candidate_price": ("Candidate price", "currency", "#2563EB"),
    "purchase_probability": ("Purchase probability", "number", "#7C3AED"),
    "expected_quantity_if_purchase": ("Expected quantity if purchased", "count", "#059669"),
    "expected_units": ("Expected units", "count", "#0891B2"),
    "expected_revenue": ("Expected revenue", "currency", "#D97706"),
    "expected_gross_profit": ("Expected gross profit", "currency", "#DC2626"),
    "candidate_margin_pct": ("Candidate margin", "percentage", "#4F46E5"),
    "price_change_percentage": ("Price change", "percentage", "#9333EA"),
}


def _series(field: str) -> ChartSeries:
    label, unit, color = _SERIES_META[field]
    return ChartSeries(field=field, label=label, unit=unit, color=color)


def _status(records: Iterable[dict[str, Any]]) -> tuple[str, bool]:
    flags = [bool(record.get("model_implied")) for record in records]
    if all(flags):
        return "model_implied", True
    if any(flags):
        return "mixed", True
    return "observed", False


def _scenario_chart(authoritative: AuthoritativeData) -> ChartSpec | None:
    records = [item.model_dump(mode="json") for item in authoritative.scenario_comparisons if item.candidate_price is not None]
    if not records:
        return None
    candidate_fields = [field for field in ("expected_gross_profit", "expected_revenue", "expected_units") if any(item.get(field) is not None for item in records)]
    if not candidate_fields:
        return None
    candidate_fields = candidate_fields[:2]
    points = [
        ChartPoint(
            x=float(item["candidate_price"]),
            values=[ChartPointValue(field=field, value=item.get(field)) for field in candidate_fields],
        )
        for item in records[:200]
    ]
    data_status, implied = _status(records)
    source_tool = "compare_price_scenarios" if any(item.get("source_tool") == "compare_price_scenarios" for item in records) else "simulate_price"
    chart = ChartSpec(
        chart_id="chart_scenario_economics",
        type="line",
        title="Candidate price economics",
        description="Validated deterministic tool outputs for supported candidate-price scenarios.",
        x_axis=ChartAxis(field="candidate_price", label="Candidate price", value_type="number", unit="currency"),
        series=[_series(field) for field in candidate_fields],
        points=points,
        source=ChartSource(tool_name=source_tool, record_path="authoritative.scenario_comparisons", data_status=data_status),
        model_implied=implied,
    )
    return validate_model(chart, "chart_spec_v1.schema.json")


def _recommendation_chart(authoritative: AuthoritativeData, *, source_tool: str = "get_pricing_recommendation") -> ChartSpec | None:
    records = [item.model_dump(mode="json") for item in authoritative.recommendations if item.final_recommended_price is not None]
    if not records:
        return None
    points = [
        ChartPoint(
            x=item["final_action"],
            values=[ChartPointValue(field="candidate_price", value=float(item["final_recommended_price"]))],
        )
        for item in records[:100]
    ]
    chart = ChartSpec(
        chart_id="chart_final_recommendations",
        type="bar",
        title="Final governed recommendations",
        description="Final recommended prices grouped by the deterministic policy action.",
        x_axis=ChartAxis(field="final_action", label="Final action", value_type="string", unit="none"),
        series=[_series("candidate_price")],
        points=points,
        source=ChartSource(tool_name=source_tool, record_path="authoritative.recommendations", data_status="observed"),
        model_implied=False,
    )
    return validate_model(chart, "chart_spec_v1.schema.json")


def build_charts(authoritative: AuthoritativeData, *, max_charts: int = 4, tool_names: Iterable[str] = ()) -> list[ChartSpec]:
    """Build the allowlisted chart types without accepting model-supplied code."""

    if max_charts <= 0:
        return []
    source_tool = "search_recommendations" if "search_recommendations" in set(tool_names) else "get_pricing_recommendation"
    charts = [chart for chart in (_scenario_chart(authoritative), _recommendation_chart(authoritative, source_tool=source_tool)) if chart is not None]
    return charts[: min(max_charts, 4)]


__all__ = ["ChartAxis", "ChartPoint", "ChartPointValue", "ChartSeries", "ChartSource", "ChartSpec", "build_charts"]
