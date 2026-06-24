import { useState } from "react";
import type { ChatMessage, PipelineOptions } from "../types";

type Props = {
  messages: ChatMessage[];
  busy: boolean;
  options: PipelineOptions;
  onSend: (text: string) => void;
};

const QUICK = [
  "run full pipeline",
  "migrate",
  "reconcile",
  "status",
  "How does reconciliation work?",
];

export function ChatDock({ messages, busy, onSend }: Props) {
  const [input, setInput] = useState("");

  const submit = () => {
    if (!input.trim()) return;
    onSend(input);
    setInput("");
  };

  return (
    <div className="chat-dock">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <h4>Migration copilot</h4>
            <p>Ask about Teradata → BigQuery migration, or run pipeline commands.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble ${m.role}`}>
            <span className="bubble-role">{m.role === "user" ? "You" : "Copilot"}</span>
            <div className="bubble-text">{m.content}</div>
          </div>
        ))}
        {busy && <div className="chat-typing"><span /><span /><span /></div>}
      </div>
      <div className="chat-compose">
        <textarea
          value={input}
          placeholder="Ask a question or type a command…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button type="button" className="btn-glow" disabled={busy} onClick={submit}>
          Send
        </button>
      </div>
      <div className="quick-chips">
        {QUICK.map((q) => (
          <button key={q} type="button" className="chip-btn" onClick={() => onSend(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
