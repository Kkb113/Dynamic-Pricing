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
import { BusinessResponse } from "./components/BusinessResponse";
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
  question?: string;
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
  return response.status === "completed" ? "Response ready." : "Response completed with items to review.";
}

function friendlyError(error: ErrorDetail): { title: string; message: string } {
  if (error.code === "MISSING_PRICING_CONTEXT") return { title: "More information needed", message: "Please include a pricing decision, product, store, category, or sales channel so I can provide a useful recommendation." };
  if (error.code === "UNKNOWN_PRICING_DECISION") return { title: "Recommendation not found", message: "I could not find a matching recommendation. Please check the reference or try a broader product, store, category, or channel question." };
  if (error.code === "UNSUPPORTED_INTENT") return { title: "Please rephrase the question", message: "Ask about recommendations, pricing options, expected business impact, inventory, model performance, or pricing rules." };
  if (error.code === "POLICY_REJECTED") return { title: "Request unavailable", message: "I can help with pricing analysis and recommendations, but I cannot perform that operation." };
  return { title: "Unable to complete the request", message: error.retryable ? "The request could not be completed right now. Please try again." : "Please adjust the question and try again." };
}

function emptyMessage(role: "user" | "assistant", content: string): DisplayMessage {
  return { id: makeId(role), role, content, warnings: [], errors: [], tools: [] };
}

export interface AppProps {
  apiClient?: PricingApiClient;
}

export default function App({ apiClient }: AppProps): ReactElement {
  const client = useMemo(() => apiClient ?? createPricingApiClient(), [apiClient]);
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
      const result = await client.getHealth();
      setHealth(result);
      if (result.status === "blocked" || result.artifacts_integrity === "blocked") {
        setHealthState("blocked");
        setHealthMessage("The local artifact set is integrity-blocked. Pricing requests are disabled.");
      } else if (result.agent_available) {
        setHealthState("ready");
        setHealthMessage("Workspace ready.");
      } else {
        setHealthState("fallback");
        setHealthMessage("Workspace ready.");
      }
    } catch (error) {
      setHealth(null);
      setHealthState("unavailable");
      setHealthMessage(error instanceof Error ? error.message : "The local pricing service is unavailable.");
    }
  }, [client]);

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
    const assistantMessage: DisplayMessage = { ...emptyMessage("assistant", ""), id: assistantId, pending: true, question: message };
    const priorConversation = messages.slice(-MAX_MESSAGES).map(({ role, content }) => ({ role, content }));
    const request: PricingChatRequest = {
      schema_version: "pricing.chat.request.v1",
      request_id: requestId,
      message,
      conversation: priorConversation,
      options: { stream: true, include_raw_json: true, max_charts: 0 },
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
      await client.streamChat(request, { onEvent }, controller.signal);
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
          const response = await client.postChat({ ...request, options: { ...request.options, stream: false } }, controller.signal);
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
  }, [client, busy, healthState, messages, updateAssistant]);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void sendMessage(draft);
  }

  function cancel(): void {
    controllerRef.current?.abort();
  }

  const serviceLabel = useMemo(() => {
    if (healthState === "ready" || healthState === "fallback") return "WORKSPACE READY";
    if (healthState === "blocked") return "INTEGRITY BLOCKED";
    if (healthState === "unavailable") return "SERVICE OFFLINE";
    return "CONNECTING";
  }, [healthState]);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Application navigation">
        <a className="brand" href="/" aria-label="Pricefield home"><span className="brand-mark" aria-hidden="true">p/</span><span>Pricefield</span></a>
        <div className="nav-item"><span aria-hidden="true">✦</span><span>Pricing assistant</span></div>
        <div className="sidebar-note"><span>Local workspace</span><small>No data is persisted</small></div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div><strong>Dynamic pricing workspace</strong><span>Pricing recommendations powered by your model</span></div>
          <div className="topbar-status" aria-live="polite"><span className={`status-dot ${healthState}`} />{serviceLabel}</div>
        </header>
        <main className="main-grid">
          <section className="conversation-panel" aria-labelledby="page-title">
            <div className="page-heading">
              <div className="intro-block">
                <p className="eyebrow">Pricing assistant</p>
                <h1 id="page-title">Ask the price. Get a clear next step.</h1>
                <p className="intro-copy">Explore recommendations, scenarios, inventory, and model performance in plain language.</p>
              </div>
              {messages.length > 0 && <button type="button" className="reset-button" onClick={() => { setMessages([]); setLastPrompt(null); setStatusText("Ready for a pricing question."); }}>Reset conversation</button>}
            </div>
            <div className="chat-card">
          <div className={`health-notice ${healthState}`} role={healthState === "unavailable" || healthState === "blocked" ? "alert" : "status"}>
            <span className="notice-icon" aria-hidden="true">{healthState === "ready" ? "●" : healthState === "fallback" ? "◇" : healthState === "blocked" ? "!" : "·"}</span>
            <span>{healthMessage}</span>
            {(healthState === "unavailable" || healthState === "blocked") && <button type="button" className="text-button" onClick={() => void checkHealth()}>Retry connection</button>}
          </div>
          <div className="message-list" aria-live="polite" aria-label="Pricing conversation">
            {messages.length === 0 && (
              <div className="empty-state">
                <div className="empty-intro"><span className="empty-glyph" aria-hidden="true">✦</span><div><h2>What would you like to explore?</h2><p>Ask for a recommendation, compare pricing options, or review expected business impact.</p></div></div>
                <div className="starter-prompts">
                  {STARTER_PROMPTS.map((prompt) => <button type="button" key={prompt} onClick={() => void sendMessage(prompt)} disabled={busy || healthState === "blocked"}>{prompt}</button>)}
                </div>
              </div>
            )}
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-avatar" aria-label={message.role === "user" ? "You" : "Pricing assistant"}>{message.role === "user" ? "You" : "✦"}</div>
                <div className="message-body">
                  {message.pending && <span className="processing-line"><span className="processing-pulse" />Working through validated tools…</span>}
                  {!message.response && message.content && message.errors.length === 0 && <p>{message.content}</p>}
                  {message.warnings.some((warning) => warning.code === "MANUAL_REVIEW_REQUIRED" || warning.code === "RULE_VIOLATION_REVIEW" || warning.code === "CURRENT_CONTEXT_STALENESS_HIGH") && <div className="inline-notices">{message.warnings.filter((warning) => warning.code === "MANUAL_REVIEW_REQUIRED" || warning.code === "RULE_VIOLATION_REVIEW" || warning.code === "CURRENT_CONTEXT_STALENESS_HIGH").map((warning) => <p className={`inline-warning ${warning.severity}`} key={`${warning.code}-${warning.message}`}>{warning.message}</p>)}</div>}
                  {message.errors.length > 0 && <div className="inline-notices">{message.errors.map((error) => { const friendly = friendlyError(error); return <p className="inline-error" key={`${error.code}-${error.message}`}><strong>{friendly.title}</strong><span>{friendly.message}</span></p>; })}</div>}
                  {message.response && <BusinessResponse response={message.response} question={message.question ?? ""} />}
                </div>
              </article>
            ))}
          </div>
          <form className="composer" onSubmit={submit}>
            <label className="sr-only" htmlFor="pricing-question">Your pricing question</label>
            <div className="composer-row">
              <textarea id="pricing-question" ref={composerRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(draft); } }} placeholder="Ask about pricing recommendations, business impact, inventory, or model performance" maxLength={4000} disabled={busy || healthState === "blocked"} rows={2} />
              {busy ? <button type="button" className="send-button cancel" onClick={cancel}>Cancel</button> : <button type="submit" className="send-button" aria-label="Send pricing question" disabled={!draft.trim() || healthState === "blocked"}>Ask <span aria-hidden="true">→</span></button>}
            </div>
            <div className="composer-meta"><span>Enter to send · Shift + Enter for a new line</span><span>{draft.length}/4000</span></div>
          </form>
          {lastPrompt && !busy && messages.some((message) => message.errors.length > 0) && <button type="button" className="retry-button" onClick={() => void sendMessage(lastPrompt)}>Try the last question again</button>}
            </div>
          </section>
        </main>
        <footer className="status-footer"><span className="sr-only" aria-live="polite">{statusText}</span><span aria-hidden="true">{statusText}</span>{health && <span>Local workspace</span>}</footer>
      </div>
    </div>
  );
}
