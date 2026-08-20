import type {
  HealthResponse,
  PricingChatError,
  PricingChatRequest,
  PricingChatResponse,
  SseEvent,
} from "../types/contracts";
import { API_BASE_URL, resolveApiBaseUrl } from "./config";
import { consumeSseStream, SseProtocolError } from "./sse";
import {
  ContractValidationError,
  validateErrorEnvelope,
  validateHealth,
  validateRequest,
  validateResponse,
} from "./validation";

export interface StreamCallbacks {
  onEvent: (event: SseEvent) => void;
}

export interface PricingApiClient {
  getHealth(signal?: AbortSignal): Promise<HealthResponse>;
  postChat(request: PricingChatRequest, signal?: AbortSignal): Promise<PricingChatResponse>;
  streamChat(request: PricingChatRequest, callbacks: StreamCallbacks, signal?: AbortSignal): Promise<void>;
}

export class ApiRequestError extends Error {
  readonly envelope?: PricingChatError;
  readonly status?: number;
  readonly retryable: boolean;

  constructor(message: string, options: { envelope?: PricingChatError; status?: number; retryable?: boolean } = {}) {
    super(message);
    this.name = "ApiRequestError";
    this.envelope = options.envelope;
    this.status = options.status;
    this.retryable = options.retryable ?? true;
  }
}

function requestPayload(request: PricingChatRequest): string {
  validateRequest(request);
  return JSON.stringify(request);
}

async function parseError(response: Response): Promise<ApiRequestError> {
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    return new ApiRequestError(`The pricing API returned HTTP ${response.status}.`, { status: response.status, retryable: response.status >= 500 });
  }
  try {
    const envelope = validateErrorEnvelope(raw);
    return new ApiRequestError(envelope.error.message, { envelope, status: response.status, retryable: envelope.error.retryable });
  } catch (error) {
    const detail = error instanceof ContractValidationError ? "invalid error envelope" : "unreadable error envelope";
    return new ApiRequestError(`The pricing API returned HTTP ${response.status} with an ${detail}.`, { status: response.status, retryable: response.status >= 500 });
  }
}

function fetchOptions(request: PricingChatRequest, signal?: AbortSignal): RequestInit {
  return {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: requestPayload(request),
  };
}

export function createPricingApiClient(baseUrl = API_BASE_URL): PricingApiClient {
  const base = resolveApiBaseUrl(baseUrl);
  return {
    async getHealth(signal) {
      let response: Response;
      try {
        response = await fetch(`${base}/api/v1/healthz`, { method: "GET", signal, headers: { Accept: "application/json" } });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") throw error;
        throw new ApiRequestError("The local pricing API is unavailable.");
      }
      let raw: unknown;
      try {
        raw = await response.json();
      } catch {
        if (!response.ok) throw await parseError(response);
        throw new ApiRequestError("The local pricing API returned unreadable health data.", { retryable: false });
      }
      try {
        const health = validateHealth(raw);
        if (health.status === "blocked" || response.ok) return health;
        throw new ApiRequestError("The local pricing service reported a blocked runtime.", { status: response.status, retryable: false });
      } catch (error) {
        if (error instanceof ApiRequestError) throw error;
        if (error instanceof ContractValidationError) {
          if (!response.ok) throw await parseError(response);
          throw new ApiRequestError("The local pricing API returned an invalid health response.", { retryable: false });
        }
        throw new ApiRequestError("The local pricing API returned unreadable health data.", { retryable: false });
      }
    },

    async postChat(request, signal) {
      let response: Response;
      try {
        response = await fetch(`${base}/api/v1/pricing/chat`, fetchOptions(request, signal));
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") throw error;
        throw new ApiRequestError("The local pricing API is unavailable.");
      }
      if (!response.ok) throw await parseError(response);
      try {
        return validateResponse(await response.json());
      } catch (error) {
        if (error instanceof ContractValidationError) throw new ApiRequestError("The pricing API returned a response outside the application contract.", { retryable: false });
        throw new ApiRequestError("The pricing API returned unreadable response data.", { retryable: false });
      }
    },

    async streamChat(request, callbacks, signal) {
      let response: Response;
      try {
        response = await fetch(`${base}/api/v1/pricing/chat/stream`, {
          ...fetchOptions(request, signal),
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") throw error;
        throw new ApiRequestError("The local pricing API is unavailable.");
      }
      if (!response.ok) throw await parseError(response);
      if (!response.body) throw new SseProtocolError("The pricing API returned an empty stream.");
      await consumeSseStream(response.body, { signal, onEvent: callbacks.onEvent });
    },
  };
}
