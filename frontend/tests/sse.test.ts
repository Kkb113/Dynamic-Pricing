import { describe, expect, it } from "vitest";
import type { SseEvent } from "../src/types/contracts";
import { consumeSseStream, SseProtocolError } from "../src/lib/sse";

function frame(value: unknown): string {
  return `event: ${typeof value === "object" && value !== null && "event" in value ? String((value as { event: string }).event) : "chat.started"}\ndata: ${JSON.stringify(value)}\n\n`;
}

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

function event(eventName: SseEvent["event"], sequence: number, requestId = "req_server_01"): SseEvent {
  if (eventName === "chat.started") return { schema_version: "pricing.chat.sse.v1", event: eventName, request_id: requestId, sequence, payload: { status: "started" } };
  if (eventName === "chat.delta") return { schema_version: "pricing.chat.sse.v1", event: eventName, request_id: requestId, sequence, payload: { text: "Validated explanation is ready." } };
  if (eventName === "chat.error") return { schema_version: "pricing.chat.sse.v1", event: eventName, request_id: requestId, sequence, payload: { error: { code: "AGENT_TIMEOUT", message: "The explanation timed out.", retryable: true } } };
  return { schema_version: "pricing.chat.sse.v1", event: eventName, request_id: requestId, sequence, payload: { status: "completed" } } as never;
}

describe("POST SSE contract consumer", () => {
  it("decodes arbitrary UTF-8 chunk boundaries, learns the server stream id, and completes once", async () => {
    const started = frame(event("chat.started", 0, "req_server_99"));
    const delta = frame(event("chat.delta", 1, "req_server_99"));
    const error = frame(event("chat.error", 2, "req_server_99"));
    const all = started + delta + error;
    const chunks = Array.from(all).map((_, index) => all.slice(index, index + 1));
    const received: SseEvent[] = [];
    await consumeSseStream(streamFrom(chunks), { onEvent: (item) => received.push(item) });
    expect(received.map((item) => item.event)).toEqual(["chat.started", "chat.delta", "chat.error"]);
    expect(received.every((item) => item.request_id === "req_server_99")).toBe(true);
  });

  it("rejects a stream that does not start at sequence zero", async () => {
    const received = consumeSseStream(streamFrom([frame(event("chat.delta", 1)), frame(event("chat.error", 2))]), { onEvent: () => undefined });
    await expect(received).rejects.toThrow(SseProtocolError);
  });

  it("rejects gaps, id changes, duplicate terminals, and missing terminals", async () => {
    await expect(consumeSseStream(streamFrom([frame(event("chat.started", 0)), frame(event("chat.error", 2))]), { onEvent: () => undefined })).rejects.toThrow(/monotonic/);
    await expect(consumeSseStream(streamFrom([frame(event("chat.started", 0)), frame(event("chat.error", 1)), frame(event("chat.error", 2))]), { onEvent: () => undefined })).rejects.toThrow(/after the terminal/);
    await expect(consumeSseStream(streamFrom([frame(event("chat.started", 0)), frame(event("chat.delta", 1, "req_other")), frame(event("chat.error", 2))]), { onEvent: () => undefined })).rejects.toThrow(/request id/);
    await expect(consumeSseStream(streamFrom([frame(event("chat.started", 0)), frame(event("chat.delta", 1))]), { onEvent: () => undefined })).rejects.toThrow(/without a terminal/);
  });

  it("rejects numeric deltas before they can be rendered", async () => {
    const numeric = { ...event("chat.delta", 1), payload: { text: "The price is 109.99." } };
    await expect(consumeSseStream(streamFrom([frame(event("chat.started", 0)), frame(numeric), frame(event("chat.error", 2))]), { onEvent: () => undefined })).rejects.toThrow(/numeric/);
  });

  it("cancels a pending reader promptly", async () => {
    const controller = new AbortController();
    const body = new ReadableStream<Uint8Array>({ pull() { return new Promise<void>(() => undefined); } });
    const pending = consumeSseStream(body, { signal: controller.signal, onEvent: () => undefined });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
