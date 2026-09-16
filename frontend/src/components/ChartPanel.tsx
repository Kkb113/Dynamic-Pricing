import type { ReactElement } from "react";
import type { ChartSpec } from "../types/contracts";

const palette = ["#2cc6b8", "#f3b45b", "#8fd3ff"];

function formatValue(value: number | string | null, unit: string): string {
  if (value === null) return "—";
  if (typeof value === "string") return value;
  if (unit === "currency") return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(value)} source units`;
  if (unit === "percentage") return `${(value <= 1 ? value * 100 : value).toFixed(1)}%`;
  if (unit === "count") return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function pointValue(chart: ChartSpec, pointIndex: number, field: string): number | null {
  const value = chart.points[pointIndex]?.values.find((item) => item.field === field)?.value;
  return value === undefined ? null : value;
}

function chartCoordinates(chart: ChartSpec, seriesIndex: number): string {
  const values = chart.points.map((_, index) => pointValue(chart, index, chart.series[seriesIndex].field)).filter((item): item is number => item !== null);
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values.map((value, index) => {
    const x = chart.points.length === 1 ? 50 : 8 + (index * 84) / (chart.points.length - 1);
    const y = 90 - ((value - min) / range) * 76;
    return `${x},${y}`;
  }).join(" ");
}

function AccessibleChartTable({ chart }: { chart: ChartSpec }): ReactElement {
  return (
    <table className="chart-table">
      <caption>{chart.title} data</caption>
      <thead>
        <tr>
          <th scope="col">{chart.x_axis.label}</th>
          {chart.series.map((series) => <th scope="col" key={series.field}>{series.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {chart.points.map((point, index) => (
          <tr key={`${String(point.x)}-${index}`}>
            <th scope="row">{formatValue(point.x, chart.x_axis.unit ?? "none")}</th>
            {chart.series.map((series) => <td key={series.field}>{formatValue(pointValue(chart, index, series.field), series.unit)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ChartPanel({ chart }: { chart: ChartSpec }): ReactElement {
  const labelledBy = `${chart.chart_id}-title`;
  return (
    <section className="chart-panel" aria-labelledby={labelledBy}>
      <div className="chart-heading">
        <div>
          <p className="eyebrow">Validated chart · {chart.type}</p>
          <h3 id={labelledBy}>{chart.title}</h3>
          <p>{chart.description}</p>
        </div>
        <span className={chart.model_implied ? "data-badge implied" : "data-badge"}>
          {chart.model_implied ? "Model-implied" : "Observed"}
        </span>
      </div>
      <div className="chart-visual-wrap">
        <svg className="chart-visual" role="img" aria-labelledby={labelledBy} viewBox="0 0 100 100" preserveAspectRatio="none">
          <line x1="8" y1="90" x2="92" y2="90" className="chart-axis" />
          <line x1="8" y1="14" x2="8" y2="90" className="chart-axis" />
          {chart.type === "line" ? chart.series.map((series, seriesIndex) => (
            <polyline key={series.field} points={chartCoordinates(chart, seriesIndex)} fill="none" stroke={series.color ?? palette[seriesIndex % palette.length]} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
          )) : chart.points.map((_, pointIndex) => chart.series.map((series, seriesIndex) => {
            const value = pointValue(chart, pointIndex, series.field);
            if (value === null) return null;
            const values = chart.points.map((_, index) => pointValue(chart, index, series.field)).filter((item): item is number => item !== null);
            const min = values.length > 0 ? Math.min(...values) : 0;
            const max = values.length > 0 ? Math.max(...values) : 1;
            const height = ((value - min) / (max - min || 1)) * 70 + 6;
            const groupWidth = 84 / Math.max(chart.points.length, 1);
            const width = Math.max(groupWidth / Math.max(chart.series.length, 1) - 1.5, 2);
            const x = 8 + pointIndex * groupWidth + seriesIndex * (width + 1);
            const y = 90 - height;
            return <rect key={`${pointIndex}-${series.field}`} x={x} y={y} width={width} height={height} rx="0.8" fill={series.color ?? palette[seriesIndex % palette.length]} />;
          }))}
        </svg>
      </div>
      <div className="chart-legend" aria-label="Chart series">
        {chart.series.map((series, index) => <span key={series.field}><i style={{ backgroundColor: series.color ?? palette[index % palette.length] }} />{series.label}</span>)}
      </div>
      <AccessibleChartTable chart={chart} />
      <p className="chart-source">Source: {chart.source.tool_name} · {chart.source.record_path}</p>
    </section>
  );
}
