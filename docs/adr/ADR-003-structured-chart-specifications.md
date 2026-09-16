# ADR-003: Structured backend-authored chart specifications

- Status: Accepted
- Date: 2026-08-20
- Scope: Phase 1 application track

## Decision

Charts are `pricing.chart.v1` objects built by FastAPI from validated deterministic tool records. The contract allows only `line` and `bar` charts, bounded points, enumerated x/series fields, named source tools, and an explicit observed/model-implied data status. React maps those specs to its chart library and never executes model-supplied code.

## Rationale

Structured specs keep chart rendering deterministic, prevent arbitrary JavaScript/HTML, and preserve the distinction between observed data and model-implied scenarios. They also let the JSON viewer expose the exact chart data used by the UI.

## Consequences

New chart types or fields require a schema version change and client support. A malformed or unsupported spec is discarded and reported as a contract error; the application does not infer a chart by scraping numbers from prose.

## Rejected alternatives

Free-form Plotly/JavaScript snippets, model-generated HTML/SVG, and frontend-side chart construction from narrative text are prohibited.
