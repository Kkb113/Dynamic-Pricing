# Application contracts

These files define the Phase 1 React/FastAPI boundary. They are versioned independently from the historical ML contracts.

| File | Purpose |
| --- | --- |
| `application_contract_v1.yaml` | Endpoint, runtime, authority, and phase-boundary index |
| `pricing_chat_request_v1.schema.json` | Synchronous and streaming request body |
| `pricing_chat_response_v1.schema.json` | Validated response envelope and typed authoritative records |
| `pricing_chat_error_v1.schema.json` | HTTP error envelope and reusable error/warning details |
| `chart_spec_v1.schema.json` | Safe backend-authored chart specification |
| `pricing_chat_sse_event_v1.schema.json` | Streaming event payload union |

## Normalization rule

Existing Phase 9–10 Python services return legacy names such as `PricingDecisionID`, `CurrentPrice`, `FinalRecommendedPrice`, and `ExpectedGrossProfit`. Phase 2 must normalize those values to the lower-snake-case fields in `pricing_chat_response_v1.schema.json`. The model and React must never be asked to infer this mapping.

## Validation rule

Every response, chart, and SSE payload is validated before leaving FastAPI. `additionalProperties: false`, enums, bounded lengths, and source-tool fields are intentional. A new field or chart type requires a new schema version and an ADR/update to the acceptance manifest.
