import responseFixture from "../../tests/application_contract/fixtures/response_recommendation.json";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../src/App";
import type { ErrorDetail, HealthResponse, PricingChatResponse } from "../src/types/contracts";
import type { PricingApiClient } from "../src/lib/api";
import { SseProtocolError } from "../src/lib/sse";

const readyFallback: HealthResponse = { status: "ready", runtime: "local", contract_version: "1", agent_available: false, artifacts_integrity: "pass" };
const response = responseFixture as PricingChatResponse;

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
  it("opens as a focused local pricing chat with context-free starters", async () => {
    render(<App apiClient={fakeClient()} />);
    expect(screen.getByRole("heading", { name: /ask the price/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /pricing question/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /what pricing questions/i })).toBeInTheDocument();
    expect(await screen.findByText("DETERMINISTIC MODE")).toBeInTheDocument();
    expect(screen.queryByText(/dashboard/i)).not.toBeInTheDocument();
  });

  it("submits a starter prompt, renders validated charts/warnings, and exposes raw JSON copy/expand", async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    const copySpy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<App apiClient={client} />);
    await user.click(screen.getByRole("button", { name: /what pricing questions/i }));
    expect(await screen.findByText(response.answer)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: response.charts[0].title })).toBeInTheDocument();
    expect(screen.getAllByText(/model-implied estimates/i).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /show response payload/i }));
    expect(screen.getByText(/"schema_version": "pricing.chat.response.v1"/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /copy raw json/i }));
    expect(copySpy).toHaveBeenCalledWith(expect.stringContaining("pricing.chat.response.v1"));
    expect(client.streamChat).toHaveBeenCalledTimes(1);
  });

  it("falls back to the JSON endpoint when POST SSE fails", async () => {
    const client = fakeClient({ streamChat: vi.fn().mockRejectedValue(new SseProtocolError("broken stream")) });
    const user = userEvent.setup();
    render(<App apiClient={client} />);
    await user.type(screen.getByRole("textbox", { name: /pricing question/i }), "What pricing questions can I ask?");
    await user.click(screen.getByRole("button", { name: /^send/i }));
    expect(await screen.findByText(response.answer)).toBeInTheDocument();
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
    expect((await screen.findAllByText(terminalError.message)).length).toBeGreaterThan(0);
    expect(screen.getByText(/missing pricing context/i)).toBeInTheDocument();
  });
});
