import { useState, type ReactElement } from "react";

export function JsonViewer({ value }: { value: unknown }): ReactElement {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const formatted = JSON.stringify(value, null, 2);

  async function copyJson(): Promise<void> {
    try {
      await navigator.clipboard.writeText(formatted);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="json-viewer" aria-label="Answer JSON output">
      <div className="json-heading">
        <div>
          <h3>JSON output</h3>
          <p>Question, answer, and supporting information sources</p>
        </div>
        <button className="button subtle" type="button" onClick={() => void copyJson()} aria-label="Copy answer JSON">
          {copied ? "Copied" : "Copy JSON"}
        </button>
      </div>
      <button className="json-toggle" type="button" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        <span>{open ? "Hide JSON output" : "View JSON output"}</span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && <pre className="json-content" tabIndex={0}>{formatted}</pre>}
      <p className="sr-only" aria-live="polite">{copied ? "Answer JSON copied to clipboard." : ""}</p>
    </section>
  );
}
