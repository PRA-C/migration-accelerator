import type { FeedEvent } from "../types";

function timeAgo(ts: number) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  return `${Math.floor(s / 60)}m ago`;
}

const ICON: Record<FeedEvent["kind"], string> = {
  info: "◆",
  agent: "▶",
  data: "⇄",
  success: "✓",
  error: "✕",
};

type Props = { events: FeedEvent[]; summary: string };

export function LiveFeed({ events, summary }: Props) {
  return (
    <section className="live-feed panel">
      <header className="panel-head">
        <div>
          <span className="panel-kicker">Event stream</span>
          <h3>Real-time telemetry</h3>
        </div>
        <span className="feed-count">{events.length} events</span>
      </header>

      {summary && (
        <div className="feed-summary">
          <pre>{summary.replace(/\*\*/g, "").replace(/`/g, "")}</pre>
        </div>
      )}

      <div className="feed-scroll">
        {events.length === 0 ? (
          <div className="feed-empty">Waiting for pipeline activity…</div>
        ) : (
          events.map((e) => (
            <article key={e.id} className={`feed-item ${e.kind}`}>
              <span className="feed-icon">{ICON[e.kind]}</span>
              <div className="feed-body">
                <div className="feed-title">{e.title}</div>
                {e.detail && <div className="feed-detail">{e.detail}</div>}
              </div>
              <time className="feed-time">{timeAgo(e.ts)}</time>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
