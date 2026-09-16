# ADR-002: Server-only OpenAI credential

- Status: Accepted
- Date: 2026-08-20
- Scope: Phase 1 application track

## Decision

`OPENAI_API_KEY` is read only by FastAPI from the local process environment. React never receives an OpenAI SDK/client, endpoint, header, key, model configuration secret, or provider error. The key is excluded from prompts, responses, logs, fixtures, browser storage, reports, and Git.

## Rationale

Browser-delivered keys are recoverable by every user and extension. Centralizing the call lets FastAPI minimize data, apply timeouts, turn off unnecessary provider state, and fall back safely to deterministic local tools.

## Consequences

The app requires a local `.env` only when conversational OpenAI access is desired. Missing configuration is a supported offline state and is reported with a typed warning. Provider retention and account controls remain an operational concern; the local app itself does not persist conversations.

## Rejected alternatives

Putting the key in Vite/React environment variables, sending it from the browser, or storing it in local/session storage is prohibited.
