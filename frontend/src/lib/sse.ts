import type { SseEvent } from "../types/contracts";
import { ContractValidationError, validateSseEvent } from "./validation";

export class SseProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SseProtocolError";
  }
}

export interface SseStreamOptions {
  expectedRequestId?: string;
  signal?: AbortSignal;
  onEvent: (event: SseEvent) => void;
}

function splitFrames(buffer: string): { frames: string[]; remainder: string } {
  const frames: string[] = [];
  let start = 0;
  while (start < buffer.length) {
    const lf = buffer.indexOf("\n\n", start);
    const crlf = buffer.indexOf("\r\n\r\n", start);
    let boundary = -1;
    let length = 2;
    if (lf !== -1 && (crlf === -1 || lf < crlf)) {
      boundary = lf;
    } else if (crlf !== -1) {
      boundary = crlf;
      length = 4;
    }
    if (boundary === -1) break;
    frames.push(buffer.slice(start, boundary));
    start = boundary + length;
  }
  return { frames, remainder: buffer.slice(start) };
}

function parseFrame(frame: string): unknown | null {
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null;
  const payload = dataLines.join("\n");
  try {
    return JSON.parse(payload) as unknown;
  } catch {
    throw new SseProtocolError("The server sent an invalid JSON SSE payload.");
  }
}

function validateOrder(event: SseEvent, expectedRequestId: string | undefined, previousSequence: number | null, terminalSeen: boolean): void {
  if (expectedRequestId !== undefined && event.request_id !== expectedRequestId) throw new SseProtocolError("The SSE request id changed during the stream.");
  if (previousSequence !== null && event.sequence !== previousSequence + 1) {
    throw new SseProtocolError("The SSE sequence is not strictly monotonic.");
  }
  if (terminalSeen) throw new SseProtocolError("The server sent an event after the terminal SSE event.");
}

export async function consumeSseStream(body: ReadableStream<Uint8Array>, options: SseStreamOptions): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let previousSequence: number | null = null;
  let terminalSeen = false;
  let ended = false;
  let streamRequestId = options.expectedRequestId;
  const abortHandler = (): void => { void reader.cancel(); };
  options.signal?.addEventListener("abort", abortHandler, { once: true });

  const processFrame = (frame: string): void => {
    const raw = parseFrame(frame);
    if (raw === null) return;
    let event: SseEvent;
    try {
      event = validateSseEvent(raw, streamRequestId);
    } catch (error) {
      if (error instanceof ContractValidationError) throw new SseProtocolError(error.message);
      throw error;
    }
    if (previousSequence === null) {
      if (event.event !== "chat.started" || event.sequence !== 0) {
        throw new SseProtocolError("The SSE stream must begin with chat.started at sequence zero.");
      }
      streamRequestId = event.request_id;
    }
    validateOrder(event, streamRequestId, previousSequence, terminalSeen);
    previousSequence = event.sequence;
    if (event.event === "chat.completed" || event.event === "chat.error") terminalSeen = true;
    options.onEvent(event);
  };

  try {
    while (true) {
      if (options.signal?.aborted) throw new DOMException("The request was cancelled.", "AbortError");
      const result = await reader.read();
      if (result.done) {
        if (options.signal?.aborted) throw new DOMException("The request was cancelled.", "AbortError");
        ended = true;
        buffer += decoder.decode();
        const split = splitFrames(`${buffer}\n\n`);
        for (const frame of split.frames) processFrame(frame);
        if (split.remainder.trim() !== "") throw new SseProtocolError("The server ended with an incomplete SSE event.");
        break;
      }
      buffer += decoder.decode(result.value, { stream: true });
      const split = splitFrames(buffer);
      buffer = split.remainder;
      for (const frame of split.frames) processFrame(frame);
    }
  } finally {
    options.signal?.removeEventListener("abort", abortHandler);
    if (!ended) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  if (!terminalSeen) throw new SseProtocolError("The server closed the stream without a terminal event.");
}
