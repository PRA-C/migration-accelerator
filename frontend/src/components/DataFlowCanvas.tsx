import type { AgentStep } from "../types";

const SHORT: Record<string, string> = {
  environment_provisioner: "Provision",
  migration_intake: "Intake",
  migration_transpiler: "Transpile",
  recon_preparer: "Extract",
  recon_comparator: "Compare",
  recon_analyst: "Recon AI",
  regression_runner: "Tests",
  qa_analyst: "QA AI",
  documentation_generator: "Docs",
  doc_writer: "Summary",
};

type Props = {
  steps: AgentStep[];
  activeNode: string;
  running: boolean;
  phase: string;
};

export function DataFlowCanvas({ steps, activeNode, running, phase }: Props) {
  const doneCount = steps.filter((s) => s.state === "done").length;
  const hasActive = steps.some((s) => s.state === "active") || (!!activeNode && running);
  const total = steps.length || 7;
  const progress = Math.round(
    ((doneCount + (running && hasActive ? 0.5 : 0)) / total) * 100
  );

  return (
    <section className="flow-canvas">
      <div className="flow-bg" aria-hidden />
      <div className="flow-grid" aria-hidden />

      <header className="flow-header">
        <div>
          <span className="flow-kicker">Live data plane</span>
          <h2>Migration stream</h2>
        </div>
        <div className="flow-status">
          <span className={`pulse-dot ${running ? "live" : ""}`} />
          <span>{running ? (activeNode ? activeNode.replace(/_/g, " ") : phase) : "Standby"}</span>
          <span className="flow-pct">{progress}%</span>
        </div>
      </header>

      <div className="flow-lane">
        <div className={`source-node ${running ? "active" : ""}`}>
          <div className="db-icon teradata">TD</div>
          <div className="node-label">Teradata</div>
          <div className="node-sub">Source warehouse</div>
        </div>

        <div className="connector source-connector">
          <div className={`stream-line ${running ? "flowing" : ""}`} />
          {running && (
            <>
              <span className="packet p1" />
              <span className="packet p2" />
              <span className="packet p3" />
            </>
          )}
        </div>

        <div className="agent-rail">
          <div className={`rail-track ${running ? "active" : ""}`} />
          <div className="agent-nodes">
            {steps.map((s) => (
              <div
                key={s.node_id}
                className={`agent-node ${s.state} ${s.uses_llm ? "llm" : ""}`}
                title={s.name}
              >
                <div className="agent-ring">
                  <span className="agent-idx">{s.index}</span>
                </div>
                <span className="agent-short">{SHORT[s.node_id] || s.name.slice(0, 8)}</span>
                {s.state === "active" && <span className="agent-beacon" />}
                {s.uses_llm && <span className="llm-tag">AI</span>}
              </div>
            ))}
          </div>
        </div>

        <div className="connector target-connector">
          <div className={`stream-line ${running ? "flowing" : ""}`} />
          {running && activeNode && (
            <>
              <span className="packet p4" />
              <span className="packet p5" />
            </>
          )}
        </div>

        <div className={`target-node ${doneCount === steps.length && steps.length > 0 ? "landed" : running ? "receiving" : ""}`}>
          <div className="db-icon bigquery">BQ</div>
          <div className="node-label">BigQuery</div>
          <div className="node-sub">Target lakehouse</div>
          {running && <div className="ingest-ring" />}
        </div>
      </div>

      <div className="flow-legend">
        <span><i className="leg llm" /> LLM agent</span>
        <span><i className="leg tool" /> Tool agent</span>
        <span><i className="leg active" /> Processing</span>
        <span><i className="leg done" /> Complete</span>
      </div>
    </section>
  );
}
