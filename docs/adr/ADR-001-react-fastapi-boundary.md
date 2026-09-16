# ADR-001: React presentation with FastAPI authority

- Status: Accepted
- Date: 2026-08-20
- Scope: Phase 1 application track

## Decision

Use React for the single natural-language chat screen and FastAPI as the local application boundary. React sends versioned request JSON and renders validated responses, charts, warnings, and the expandable JSON panel. FastAPI validates requests, owns local ML/service access, orchestrates the optional agent, constructs chart specs, and normalizes responses.

## Rationale

The split keeps Python model artifacts and service code out of the browser, gives one place to enforce support envelopes and business rules, and makes secret handling auditable. It also allows deterministic pricing results to remain available when OpenAI is not configured.

## Consequences

The frontend cannot provide an authoritative price or execute chart code. Phase 2 must implement the API against `contracts/application/`; Phase 3 must not bypass it. Local CORS is required and no authentication or hosting is added in this product track.

## Rejected alternatives

Embedding Python/ML code in React, calling OpenAI directly from the browser, and using the existing multi-page Streamlit UI do not satisfy the fixed product scope or trust boundary.
