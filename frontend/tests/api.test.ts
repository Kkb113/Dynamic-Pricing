import responseFixture from "../../tests/application_contract/fixtures/response_recommendation.json";
import { describe, expect, it, vi } from "vitest";
import { createPricingApiClient } from "../src/lib/api";
import { ApiConfigurationError } from "../src/lib/config";
import { SseProtocolError } from "../src/lib/sse";

const request = { schema_version: "pricing.chat.request.v1" as const, request_id: "req_client_01", message: "What pricing questions can I ask?" };

function streamBody(events: unknown[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const text = events.map((item) => `data: ${JSON.stringify(item)}\n\n`).join("");
  return new ReadableStream({ start(controller) { controller.enqueue(encoder.encode(text)); controller.close(); } });
}

describe("pricing API client", () => {
  it("validates every injected base URL at construction", () => {
    expect(() => createPricingApiClient("https://remote.example" )).toThrow(ApiConfigurationError);
    expect(() => createPricingApiClient("http://10.0.0.4:8000")).toThrow(ApiConfigurationError);
  });

  it("learns a Phase 2 generated stream id instead of requiring the optional client id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(streamBody([
      { schema_version: "pricing.chat.sse.v1", event: "chat.started", request_id: "req_server_01", sequence: 0, payload: { status: "started" } },
      { schema_version: "pricing.chat.sse.v1", event: "chat.delta", request_id: "req_server_01", sequence: 1, payload: { text: "Validated explanation is ready." } },
      { schema_version: "pricing.chat.sse.v1", event: "chat.error", request_id: "req_server_01", sequence: 2, payload: { error: { code: "AGENT_TIMEOUT", message: "The explanation timed out.", retryable: true } } },
    ]), { status: 200, headers: { "Content-Type": "text/event-stream" } }));
    const events: string[] = [];
    await createPricingApiClient().streamChat(request, { onEvent: (event) => events.push(event.event) });
    expect(events).toEqual(["chat.started", "chat.delta", "chat.error"]);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/api/v1/pricing/chat/stream", expect.objectContaining({ method: "POST" }));
  });

  it("validates JSON responses and maps invalid server output to a safe error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(responseFixture), { status: 200, headers: { "Content-Type": "application/json" } }));
    const response = await createPricingApiClient().postChat(request);
    expect(response.request_id).toBe("req_demo_001");

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ nope: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await expect(createPricingApiClient().postChat(request)).rejects.toThrow(/outside the application contract/);
  });

  it("returns a valid blocked health response even when FastAPI uses HTTP 503", async () => {
    const blocked = { status: "blocked", runtime: "local", contract_version: "1", agent_available: false, artifacts_integrity: "blocked" };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(blocked), { status: 503, headers: { "Content-Type": "application/json" } }));
    await expect(createPricingApiClient().getHealth()).resolves.toEqual(blocked);
  });

  it("keeps malformed stream output outside the UI", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(streamBody([
      { schema_version: "pricing.chat.sse.v1", event: "chat.started", request_id: "req_server_01", sequence: 0, payload: { status: "started" } },
      { schema_version: "pricing.chat.sse.v1", event: "chat.delta", request_id: "req_server_01", sequence: 2, payload: { text: "No." } },
    ]), { status: 200 }));
    await expect(createPricingApiClient().streamChat(request, { onEvent: () => undefined })).rejects.toBeInstanceOf(SseProtocolError);
  });
});
