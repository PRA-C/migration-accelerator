import type { EnvStatus, MigrationRun } from "../types";

type Props = {
  metrics: Record<string, number>;
  env: EnvStatus[];
  runs: MigrationRun[];
  onSelectRun: (id: number) => void;
};

export function MetricsRail({ metrics, env, runs, onSelectRun }: Props) {
  return (
    <aside className="metrics-rail">
      <section className="panel env-panel">
        <header className="panel-head compact">
          <span className="panel-kicker">Environment</span>
        </header>
        <div className="env-chips">
          {env.map((e) => (
            <div key={e.name} className={`env-chip ${e.configured ? "ok" : "warn"}`}>
              <span className="chip-dot" />
              <span className="chip-name">{e.name}</span>
              <span className="chip-val">{e.label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel stats-panel">
        <header className="panel-head compact">
          <span className="panel-kicker">Throughput</span>
        </header>
        <div className="stat-grid">
          {[
            { label: "Total runs", value: metrics.total_runs ?? 0, accent: "cyan" },
            { label: "Transpiled", value: metrics.migrated_ok ?? 0, accent: "violet" },
            { label: "Recon pass", value: metrics.recon_passed ?? 0, accent: "green" },
            { label: "LLM agents", value: metrics.llm_agents ?? 0, accent: "amber" },
          ].map((s) => (
            <div key={s.label} className={`stat-card ${s.accent}`}>
              <div className="stat-val">{s.value}</div>
              <div className="stat-label">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel runs-panel">
        <header className="panel-head compact">
          <span className="panel-kicker">Recent migrations</span>
        </header>
        <div className="runs-list">
          {runs.slice(0, 8).map((r) => (
            <button
              key={r.run_id}
              type="button"
              className="run-row"
              onClick={() => onSelectRun(r.run_id)}
            >
              <span className="run-id">#{r.run_id}</span>
              <span className="run-file">{r.source_file || "—"}</span>
              <span className={`run-badge ${r.success ? "ok" : "fail"}`}>
                {r.success ? "OK" : "FAIL"}
              </span>
              <span className={`run-badge ${r.recon_passed === true ? "ok" : r.recon_passed === false ? "fail" : "muted"}`}>
                {r.recon_passed === true ? "RECON" : r.recon_passed === false ? "DIFF" : "—"}
              </span>
            </button>
          ))}
          {runs.length === 0 && <div className="feed-empty">No runs yet</div>}
        </div>
      </section>
    </aside>
  );
}
