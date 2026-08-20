import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactElement } from "react";
import type {
  ErrorDetail,
  HealthResponse,
  PricingChatRequest,
  PricingChatResponse,
  SseEvent,
  ToolName,
  WarningDetail,
} from "./types/contracts";
import { ChartPanel } from "./components/ChartPanel";
import { JsonViewer } from "./components/JsonViewer";
import { ApiRequestError, createPricingApiClient, type PricingApiClient } from "./lib/api";
import { SseProtocolError } from "./lib/sse";
import { STARTER_PROMPTS } from "./lib/prompts";

const MAX_MESSAGES = 20;

type DisplayMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: PricingChatResponse;
  warnings: WarningDetail[];
  errors: ErrorDetail[];
  tools: Array<{ tool_name: ToolName; status: string; record_count?: number }>;
  pending?: boolean;
};

type HealthState = "checking" | "ready" | "fallback" | "blocked" | "unavailable";

function makeId(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
    : Math.random().toString(36).slice(2, 18);
  return `${prefix}_${suffix}`;
}

function toErrorDetail(error: unknown): ErrorDetail {
  if (error instanceof ApiRequestError && error.envelope) return error.envelope.error;
  return {
    code: "INTERNAL_ERROR",
    message: error instanceof Error ? error.message : "The local pricing request could not be completed.",
    retryable: true,
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function responseWarnings(response: PricingChatResponse): string {
  if (response.metadata.agent_available) return "Agent explanation active; numeric claims remain tool-authoritative.";
  return "Deterministic local fallback active; numeric claims come from validated pricing tools.";
}

function emptyMessage(role: "user" | "assistant", content: string): DisplayMessage {
  return { id: makeId(role), role, content, warnings: [], errors: [], tools: [] };
}

export interface AppProps {
  apiClient?: PricingApiClient;
}

export default function App({ apiClient = createPricingApiClient() }: AppProps): ReactElement {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthState, setHealthState] = useState<HealthState>("checking");
  const [healthMessage, setHealthMessage] = useState("Checking the local pricing service…");
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState("Ready for a pricing question.");
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  const checkHealth = useCallback(async (): Promise<void> => {
    setHealthState("checking");
    setHealthMessage("Checking the local pricing service…");
    try {
      const result = await apiClient.getHealth();
      setHealth(result);
      if (result.status === "blocked" || result.artifacts_integrity === "blocked") {
        setHealthState("blocked");
        setHealthMessage("The local artifact set is integrity-blocked. Pricing requests are disabled.");
      } else if (result.agent_available) {
        setHealthState("ready");
        setHealthMessage("Local service ready · agent explanation available.");
      } else {
        setHealthState("fallback");
        setHealthMessage("Local service ready · deterministic fallback active.");
      }
    } catch (error) {
      setHealth(null);
      setHealthState("unavailable");
      setHealthMessage(error instanceof Error ? error.message : "The local pricing service is unavailable.");
    }
  }, [apiClient]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void checkHealth(); }, 0);
    return () => window.clearTimeout(timer);
  }, [checkHealth]);

  const updateAssistant = useCallback((id: string, update: (message: DisplayMessage) => DisplayMessage): void => {
    setMessages((current) => current.map((message) => message.id === id ? update(message) : message));
  }, []);

  const sendMessage = useCallback(async (prompt: string): Promise<void> => {
    const message = prompt.trim();
    if (!message || busy || healthState === "blocked") return;
    const requestId = makeId("req");
    const userMessage = emptyMessage("user", message);
    const assistantId = makeId("assistant");
    const assistantMessage: DisplayMessage = { ...emptyMessage("assistant", ""), id: assistantId, pending: true };
    const priorConversation = messages.slice(-MAX_MESSAGES).map(({ role, content }) => ({ role, content }));
    const request: PricingChatRequest = {
      schema_version: "pricing.chat.request.v1",
      request_id: requestId,
      message,
      conversation: priorConversation,
      options: { stream: true, include_raw_json: true, max_charts: 4 },
    };
    setMessages((current) => [...current, userMessage, assistantMessage].slice(-MAX_MESSAGES));
    setDraft("");
    setBusy(true);
    setLastPrompt(message);
    setStatusText("Reading the governed pricing tools…");
    const controller = new AbortController();
    controllerRef.current = controller;
    let completedResponse: PricingChatResponse | null = null;
    const streamState: { error: ErrorDetail | null } = { error: null };

    const onEvent = (event: SseEvent): void => {
      if (event.event === "chat.started") {
        setStatusText("Pricing request accepted…");
        return;
      }
      if (event.event === "chat.tool") {
        setStatusText(`${event.payload.status === "started" ? "Calling" : "Finished"} ${event.payload.tool_name}…`);
        updateAssistant(assistantId, (current) => ({ ...current, tools: [...current.tools, event.payload] }));
        return;
      }
      if (event.event === "chat.delta") {
        updateAssistant(assistantId, (current) => ({ ...current, content: `${current.content}${event.payload.text}`, pending: true }));
        return;
      }
      if (event.event === "chat.error") {
        streamState.error = event.payload.error;
        updateAssistant(assistantId, (current) => ({ ...current, errors: [event.payload.error], pending: false, content: event.payload.error.message }));
        setStatusText("The pricing service returned a governed error.");
        return;
      }
      completedResponse = event.payload.response;
      updateAssistant(assistantId, (current) => ({
        ...current,
        content: event.payload.response.answer,
        response: event.payload.response,
        warnings: event.payload.response.warnings,
        errors: event.payload.response.errors,
        pending: false,
      }));
      setStatusText(responseWarnings(event.payload.response));
    };

    try {
      await apiClient.streamChat(request, { onEvent }, controller.signal);
      if (!completedResponse && !streamState.error) throw new SseProtocolError("The stream ended without a pricing response.");
    } catch (error) {
      if (isAbortError(error)) {
        updateAssistant(assistantId, (current) => ({ ...current, content: "Request cancelled.", pending: false }));
        setStatusText("Request cancelled. You can try another question.");
      } else if (streamState.error) {
        setStatusText(streamState.error.retryable ? "The request can be retried." : "The request was rejected by policy.");
      } else {
        setStatusText("Streaming was unavailable; trying the JSON response endpoint…");
        try {
          const response = await apiClient.postChat({ ...request, options: { ...request.options, stream: false } }, controller.signal);
          completedResponse = response;
          updateAssistant(assistantId, (current) => ({ ...current, content: response.answer, response, warnings: response.warnings, errors: response.errors, pending: false }));
          setStatusText(responseWarnings(response));
        } catch (fallbackError) {
          const detail = toErrorDetail(fallbackError);
          updateAssistant(assistantId, (current) => ({ ...current, content: detail.message, errors: [detail], pending: false }));
          setStatusText("The local pricing service could not complete the request.");
        }
      }
    } finally {
      controllerRef.current = null;
      setBusy(false);
      composerRef.current?.focus();
    }
  }, [apiClient, busy, healthState, messages, updateAssistant]);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void sendMessage(draft);
  }

  function cancel(): void {
    controllerRef.current?.abort();
  }

  const serviceLabel = useMemo(() => {
    if (healthState === "ready") return "AGENT READY";
    if (healthState === "fallback") return "DETERMINISTIC MODE";
    if (healthState === "blocked") return "INTEGRITY BLOCKED";
    if (healthState === "unavailable") return "SERVICE OFFLINE";
    return "CONNECTING";
  }, [healthState]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Pricefield home"><span className="brand-mark" aria-hidden="true">↗</span><span>Pricefield</span></a>
        <div className="topbar-status" aria-live="polite"><span className={`status-dot ${healthState}`} />{serviceLabel}<span className="local-only">LOCAL ONLY</span></div>
      </header>
      <main className="main-grid">
        <section className="conversation-panel" aria-labelledby="page-title">
          <div className="intro-block">
            <p className="eyebrow">Dynamic pricing assistant</p>
            <h1 id="page-title">Ask the price<br /><em>with evidence.</em></h1>
            <p className="intro-copy">A focused interface for governed pricing decisions. Ask in plain language; the local tools supply every numeric claim.</p>
          </div>
          <div className={`health-notice ${healthState}`} role={healthState === "unavailable" || healthState === "blocked" ? "alert" : "status"}>
            <span className="notice-icon" aria-hidden="true">{healthState === "ready" ? "●" : healthState === "fallback" ? "◇" : healthState === "blocked" ? "!" : "·"}</span>
            <span>{healthMessage}</span>
            {(healthState === "unavailable" || healthState === "blocked") && <button type="button" className="text-button" onClick={() => void checkHealth()}>Retry connection</button>}
          </div>
          <div className="message-list" aria-live="polite" aria-label="Pricing conversation">
            {messages.length === 0 && (
              <div className="empty-state">
                <span className="empty-glyph" aria-hidden="true">⌁</span>
                <h2>What should we price next?</h2>
                <p>Start with a decision, a comparison, or an explanation of the governing rule.</p>
                <div className="starter-prompts">
                  {STARTER_PROMPTS.map((prompt) => <button type="button" key={prompt} onClick={() => void sendMessage(prompt)} disabled={busy || healthState === "blocked"}>{prompt}</button>)}
                </div>
              </div>
            )}
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-label">{message.role === "user" ? "You" : "Pricing assistant"}</div>
                <div className="message-body">
                  {message.pending && <span className="processing-line"><span className="processing-pulse" />Working through validated tools…</span>}
                  {message.content && <p>{message.content}</p>}
                  {message.tools.length > 0 && <div className="tool-statuses" aria-label="Tool status">{message.tools.map((tool, index) => <span key={`${tool.tool_name}-${index}`}><i />{tool.tool_name.replaceAll("_", " ")} {tool.status}</span>)}</div>}
                  {message.warnings.length > 0 && <div className="inline-notices">{message.warnings.map((warning) => <p className={`inline-warning ${warning.severity}`} key={`${warning.code}-${warning.message}`}><strong>{warning.code.replaceAll("_", " ")}</strong> {warning.message}</p>)}</div>}
                  {message.errors.length > 0 && <div className="inline-notices">{message.errors.map((error) => <p className="inline-error" key={`${error.code}-${error.message}`}><strong>{error.code.replaceAll("_", " ")}</strong> {error.message}</p>)}</div>}
                  {message.response && <div className="response-details">
                    {message.response.charts.map((chart) => <ChartPanel chart={chart} key={chart.chart_id} />)}
                    <JsonViewer value={message.response} />
                  </div>}
                </div>
              </article>
            ))}
          </div>
          <form className="composer" onSubmit={submit}>
            <label htmlFor="pricing-question">Your pricing question</label>
            <div className="composer-row">
              <textarea id="pricing-question" ref={composerRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(draft); } }} placeholder="Ask about capabilities, model performance, inventory, or a governed decision" maxLength={4000} disabled={busy || healthState === "blocked"} rows={2} />
              {busy ? <button type="button" className="send-button cancel" onClick={cancel}>Cancel</button> : <button type="submit" className="send-button" disabled={!draft.trim() || healthState === "blocked"}>Send <span aria-hidden="true">↗</span></button>}
            </div>
            <div className="composer-meta"><span>Enter to send · Shift + Enter for a new line</span><span>{draft.length}/4000</span></div>
          </form>
          {lastPrompt && !busy && messages.some((message) => message.errors.length > 0) && <button type="button" className="retry-button" onClick={() => void sendMessage(lastPrompt)}>Try the last question again</button>}
        </section>
        <aside className="context-panel" aria-label="Pricing service details">
          <div className="context-header"><p className="eyebrow">System boundary</p><h2>Evidence, kept close.</h2></div>
          <div className="boundary-list">
            <div><span className="boundary-index">01</span><div><strong>Local tools</strong><p>Frozen ML and pricing rules supply the numbers.</p></div></div>
            <div><span className="boundary-index">02</span><div><strong>Plain-language answer</strong><p>Agent text explains; it cannot invent a price.</p></div></div>
            <div><span className="boundary-index">03</span><div><strong>Charts + JSON</strong><p>Every visual maps back to a validated response.</p></div></div>
          </div>
          <div className="context-footer"><span className="footer-rule" /><p>Responses stay in this session only.<br />No transcript is persisted.</p><span className="contract-stamp">CONTRACT<br />V1</span></div>
          {health && <dl className="health-details"><div><dt>Runtime</dt><dd>{health.runtime}</dd></div><div><dt>Artifacts</dt><dd>{health.artifacts_integrity}</dd></div><div><dt>Agent</dt><dd>{health.agent_available ? "available" : "fallback"}</dd></div></dl>}
        </aside>
      </main>
      <footer className="status-footer"><span className="sr-only" aria-live="polite">{statusText}</span><span aria-hidden="true">{statusText}</span><span>pricing.chat.response.v1</span></footer>
    </div>
  );
}
