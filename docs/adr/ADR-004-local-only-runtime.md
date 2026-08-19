# ADR-004: Local-only runtime

- Status: Accepted
- Date: 2026-08-20
- Scope: Phase 1 application track

## Decision

Run the React development server and FastAPI service on loopback only. Do not add authentication, hosting, deployment, cloud storage, remote database writes, or operational price writeback. Conversation state exists only in React memory for the current tab; FastAPI keeps no application session.

## Rationale

This phase is a controlled local demonstration over frozen evidence. A local boundary reduces exposure, keeps ML/service access read-only, and makes it clear that recommendations are advisory rather than an operational pricing action.

## Consequences

The app is intentionally single-user and non-production. CORS is a small local allowlist, health/readiness is explicit, and future hosting would require a new security/operational design rather than an incremental configuration toggle.

## Rejected alternatives

Cloud deployment, multi-user authentication, persistent chat history, and database/writeback integration are outside the fixed product scope.
