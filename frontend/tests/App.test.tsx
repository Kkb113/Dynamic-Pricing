import responseFixture from "../../tests/application_contract/fixtures/response_recommendation.json";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import type { ErrorDetail, HealthResponse, PricingChatResponse } from "../src/types/contracts";
import type { PricingApiClient } from "../src/lib/api";
import { SseProtocolError } from "../src/lib/sse";

const readyFallback: HealthResponse = { status: "ready", runtime: "local", contract_version: "1", agent_available: false, artifacts_integrity: "pass" };
const response = responseFixture as PricingChatResponse;

afterEach(() => vi.unstubAllGlobals());

function fakeClient(overrides: Partial<PricingApiClient> = {}): PricingApiClient {
  return {
    getHealth: vi.fn().mockResolvedValue(readyFallback),
    postChat: vi.fn().mockResolvedValue(response),
    streamChat: vi.fn().mockImplementation(async (_request, callbacks) => {
      callbacks.onEvent({ schema_version: "pricing.chat.sse.v1", event: "chat.started", request_id: "req_server_01", sequence: 0, payload: { status: "started" } });
      callbacks.onEvent({ schema_version: "pricing.chat.sse.v1", event: "chat.delta", request_id: "req_server_01", sequence: 1, payload: { text: "Validated explanation is ready." } });
      callbacks.onEvent({ schema_version: "pricing.chat.sse.v1", event: "chat.completed", request_id: "req_server_01", sequence: 2, payload: { response } });
    }),
    ...overrides,
  };
}

describe("pricing chat interface", () => {
  it("creates the default API client once and does not loop the health check", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(readyFallback), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByText("WORKSPACE READY")).toBeInTheDocument();
    await new Promise((resolve) => window.setTimeout(resolve, 25));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("opens as a focused local pricing chat with context-free starters", async () => {
    render(<App apiClient={fakeClient()} />);
    expect(screen.getByRole("heading", { name: /ask the price/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /pricing question/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /what pricing questions/i })).toBeInTheDocument();
    expect(await screen.findByText("WORKSPACE READY")).toBeInTheDocument();
    expect(screen.queryByText(/dashboard/i)).not.toBeInTheDocument();
  });

  it("renders a polished business recommendation and keeps JSON available on demand", async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    const copySpy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<App apiClient={client} />);
    await user.click(screen.getByRole("button", { name: /what pricing questions/i }));
    expect(await screen.findByText(/model-informed recommendation constrained/i)).toBeInTheDocument();
    expect(screen.getAllByText("109.99 source units").length).toBeGreaterThan(0);
    expect(screen.getByText("Final recommendation")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: response.charts[0].title })).not.toBeInTheDocument();
    expect(screen.queryByText(/Phase7FinalRecommendedPrice/)).not.toBeInTheDocument();
    expect(screen.getByText(response.answer)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /view json output/i }));
    expect(screen.getByText(/"question": "What pricing questions can I ask\?"/)).toBeInTheDocument();
    expect(screen.getByText(/"sources":/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /copy answer json/i }));
    expect(copySpy).toHaveBeenCalledWith(expect.stringContaining("What pricing questions can I ask?"));
    expect(client.streamChat).toHaveBeenCalledTimes(1);
  });

  it("falls back to the JSON endpoint when POST SSE fails", async () => {
    const client = fakeClient({ streamChat: vi.fn().mockRejectedValue(new SseProtocolError("broken stream")) });
    const user = userEvent.setup();
    render(<App apiClient={client} />);
    await user.type(screen.getByRole("textbox", { name: /pricing question/i }), "What pricing questions can I ask?");
    await user.click(screen.getByRole("button", { name: /^send/i }));
    expect(await screen.findByText(/model-informed recommendation constrained/i)).toBeInTheDocument();
    expect(client.postChat).toHaveBeenCalledTimes(1);
  });

  it("surfaces unavailable and integrity-blocked states without implying an OpenAI requirement", async () => {
    const offline = fakeClient({ getHealth: vi.fn().mockRejectedValue(new Error("The local pricing API is unavailable.")) });
    render(<App apiClient={offline} />);
    expect(await screen.findByText("SERVICE OFFLINE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry connection/i })).toBeInTheDocument();

    const blockedHealth: HealthResponse = { ...readyFallback, status: "blocked", artifacts_integrity: "blocked" };
    const blocked = fakeClient({ getHealth: vi.fn().mockResolvedValue(blockedHealth) });
    render(<App apiClient={blocked} />);
    expect(await screen.findByText("INTEGRITY BLOCKED")).toBeInTheDocument();
    expect(screen.getByText(/integrity-blocked/i)).toBeInTheDocument();
  });

  it("renders a safe terminal error and allows cancellation", async () => {
    const terminalError: ErrorDetail = { code: "MISSING_PRICING_CONTEXT", message: "Provide a pricing decision id for this question.", retryable: false };
    const client = fakeClient({ streamChat: vi.fn().mockImplementation(async (_request, callbacks) => callbacks.onEvent({ schema_version: "pricing.chat.sse.v1", event: "chat.error", request_id: "req_server_01", sequence: 0, payload: { error: terminalError } })) });
    const user = userEvent.setup();
    render(<App apiClient={client} />);
    await user.type(screen.getByRole("textbox", { name: /pricing question/i }), "Why did the price move?");
    await user.click(screen.getByRole("button", { name: /^send/i }));
    expect(await screen.findByText(/more information needed/i)).toBeInTheDocument();
    expect(screen.getByText(/please include a pricing decision/i)).toBeInTheDocument();
    expect(screen.queryByText(terminalError.message)).not.toBeInTheDocument();
    expect(screen.queryByText(/missing pricing context/i)).not.toBeInTheDocument();
  });
});
