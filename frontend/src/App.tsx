import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { ChatDock } from "./components/ChatDock";
import { DataFlowCanvas } from "./components/DataFlowCanvas";
import { LiveFeed } from "./components/LiveFeed";
import { MetricsRail } from "./components/MetricsRail";
import { MigrationRouteBar } from "./components/MigrationRouteBar";
import { SlidePanel } from "./components/SlidePanel";
import { ReportsViewer, RunInspector, SqlWorkbench } from "./components/WorkbenchPanels";
import { usePipeline } from "./hooks/usePipeline";
import type { ChatMessage, EnvStatus, MigrationProfile, MigrationRun, PipelineOptions } from "./types";
import { dbLabel, defaultOptions } from "./types";

type Panel = "chat" | "sql" | "reports" | "run" | null;

export default function App() {
  const [options, setOptions] = useState<PipelineOptions>(defaultOptions());
  const [profile, setProfile] = useState<MigrationProfile | null>(null);
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [env, setEnv] = useState<EnvStatus[]>([]);
  const [runs, setRuns] = useState<MigrationRun[]>([]);
  const [panel, setPanel] = useState<Panel>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [clock, setClock] = useState(new Date());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [selectedRun, setSelectedRun] = useState<number | null>(null);
  const [runDetail, setRunDetail] = useState<Record<string, unknown> | null>(null);
  const [sqlFiles, setSqlFiles] = useState<string[]>([]);
  const [sqlFile, setSqlFile] = useState("");
  const [sourceSql, setSourceSql] = useState("");
  const [targetSql, setTargetSql] = useState("");
  const [transpileStatus, setTranspileStatus] = useState("");
  const [transpileBusy, setTranspileBusy] = useState(false);
  const [artifacts, setArtifacts] = useState<{ label: string; path: string; exists: boolean }[]>([]);
  const [previewPath, setPreviewPath] = useState("");
  const [preview, setPreview] = useState("");
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  const checkApi = useCallback(async () => {
    try {
      await api.health();
      setApiOnline(true);
      return true;
    } catch {
      setApiOnline(false);
      return false;
    }
  }, []);

  const sourceLabel = dbLabel(options.source_database, profile?.sources);
  const targetLabel = dbLabel(options.target_database, profile?.targets);

  const refresh = useCallback(async () => {
    const ok = await checkApi();
    if (!ok) return;
    const d = await api.dashboard();
    setMetrics(d.metrics);
    setEnv(d.env);
    setRuns(d.runs as MigrationRun[]);
  }, [checkApi]);

  const pipeline = usePipeline(options, refresh);

  useEffect(() => {
    checkApi().then((ok) => {
      if (ok) refresh().catch(console.error);
      pipeline.initSteps();
    });
    api.migrationProfile().then(setProfile).catch(console.error);
    pipeline.initFeed(sourceLabel, targetLabel);
    api.sqlFiles().then((f) => { setSqlFiles(f); if (f[0]) setSqlFile(f[0]); }).catch(console.error);
    api.reports().then(setArtifacts).catch(console.error);
  }, []);

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const poll = setInterval(() => {
      checkApi().then((ok) => {
        if (ok && !pipeline.running) refresh().catch(() => {});
      });
    }, 8000);
    return () => clearInterval(poll);
  }, [pipeline.running, refresh, checkApi]);

  useEffect(() => {
    if (selectedRun) api.migration(selectedRun).then(setRunDetail).catch(console.error);
  }, [selectedRun]);

  const toggleOpt = (key: keyof PipelineOptions) => {
    if (key === "preset" || key === "source_database" || key === "target_database") return;
    setOptions((o) => ({ ...o, [key]: !o[key] }));
  };

  const setRoute = (key: "source_database" | "target_database", value: string) => {
    setOptions((o) => ({ ...o, [key]: value }));
  };

  const sendChat = async (text: string) => {
    if (!text.trim() || chatBusy) return;
    setChatBusy(true);
    setPanel("chat");
    const userMsg: ChatMessage = { role: "user", content: text.trim() };
    const hist = [...messages, userMsg];
    setMessages(hist);
    try {
      const res = await api.chat(text, messages, options);
      setMessages([...hist, { role: "assistant", content: res.reply || "(no response)" }]);
      if (res.events?.some((e: unknown) => (e as { type?: string }).type?.startsWith("pipeline"))) {
        await refresh();
        await pipeline.loadSteps([], "");
      }
    } catch (e) {
      setMessages([...hist, { role: "assistant", content: `Error: ${e}` }]);
    } finally {
      setChatBusy(false);
    }
  };

  const openRun = (id: number) => {
    setSelectedRun(id);
    setPanel("run");
  };

  const loadSql = async () => {
    if (!sqlFile) return;
    const f = await api.sqlFile(sqlFile);
    setSourceSql(f.content);
  };

  const transpile = async () => {
    if (transpileBusy) return;
    setTranspileBusy(true);
    setTranspileStatus("Transpiling with LLM… (typically 15–60s)");
    try {
      const r = await api.transpile({
        ...(sqlFile ? { filename: sqlFile } : { sql: sourceSql }),
        source_database: options.source_database,
        target_database: options.target_database,
      });
      setTargetSql(r.sql);
      setTranspileStatus(r.status);
    } catch (e) {
      setTranspileStatus(String(e));
    } finally {
      setTranspileBusy(false);
    }
  };

  const loadReport = async (path: string) => {
    setPreviewPath(path);
    if (!path) { setPreview(""); return; }
    const p = await api.reportPreview(path);
    setPreview(p.content);
  };

  return (
    <div className="shell">
      <div className="aurora" aria-hidden />

      <header className="topbar">
        <div className="topbar-glow" aria-hidden />
        <div className="brand-block">
          <div className="brand-mark">
            <span>MA</span>
          </div>
          <div>
            <h1>Migration Accelerator</h1>
            <p className="brand-route">Enterprise Migration, Simplified</p>
          </div>
        </div>

        <div className="topbar-actions">
          <div className="topbar-right">
            <div className="topbar-utilities">
              <span className={`api-pill ${apiOnline === false ? "offline" : apiOnline ? "online" : "checking"}`}>
                <i className="api-pill-dot" />
                {apiOnline === false ? "Offline" : apiOnline ? "Online" : "Checking"}
              </span>
              <time className="clock">{clock.toLocaleTimeString()}</time>
            </div>
            <div className="topbar-docks">
              <button
                type="button"
                className={`dock-btn dock-btn--icon ${settingsOpen ? "active" : ""}`}
                onClick={() => setSettingsOpen((v) => !v)}
                title="Settings"
                aria-label="Settings"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
                    stroke="currentColor"
                    strokeWidth="1.75"
                  />
                  <path
                    d="M19.4 15a7.9 7.9 0 0 0 .1-1 7.9 7.9 0 0 0-.1-1l2-1.5-2-3.5-2.4 1a8 8 0 0 0-1.7-1L15 3h-6l-.3 2.5a8 8 0 0 0-1.7 1l-2.4-1-2 3.5 2 1.5a7.9 7.9 0 0 0-.1 1 7.9 7.9 0 0 0 .1 1l-2 1.5 2 3.5 2.4-1a8 8 0 0 0 1.7 1L9 21h6l.3-2.5a8 8 0 0 0 1.7-1l2.4 1 2-3.5-2-1.5Z"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <button type="button" className="dock-btn dock-btn--ai" onClick={() => setPanel("chat")}>
                AI
              </button>
              <button type="button" className="dock-btn" onClick={() => setPanel("sql")}>
                SQL
              </button>
              <button type="button" className="dock-btn" onClick={() => setPanel("reports")}>
                Reports
              </button>
            </div>
          </div>
        </div>
      </header>

      {apiOnline === false && (
        <div className="api-banner">
          Backend not reachable. Start it with: <code>uv run python -m api</code> (port 8000), then refresh.
        </div>
      )}

      {settingsOpen && (
        <div className="settings-bar">
          {([
            ["use_llm", "LLM agents"],
            ["integration_tests", "Integration tests"],
            ["skip_synthetic", "Skip synthetic data"],
            ["skip_provision", "Skip provision"],
            ["skip_migrate", "Skip migrate"],
            ["skip_recon", "Skip recon"],
            ["skip_tests", "Skip tests"],
            ["skip_docs", "Skip docs"],
          ] as const).map(([key, label]) => (
            <label key={key} className="setting-toggle">
              <input type="checkbox" checked={options[key]} onChange={() => toggleOpt(key)} />
              {label}
            </label>
          ))}
        </div>
      )}

      <MigrationRouteBar
        source={options.source_database}
        target={options.target_database}
        profile={profile}
        disabled={pipeline.running}
        pipelineDisabled={pipeline.running || apiOnline === false}
        onSourceChange={(v) => setRoute("source_database", v)}
        onTargetChange={(v) => setRoute("target_database", v)}
        onRunPipeline={pipeline.runPipeline}
      />

      <main className="stage">
        <div className="stage-primary">
          <DataFlowCanvas
            steps={pipeline.steps}
            activeNode={pipeline.activeNode}
            running={pipeline.running}
            phase={pipeline.phase}
            sourceDatabase={options.source_database}
            targetDatabase={options.target_database}
            sourceLabel={sourceLabel}
            targetLabel={targetLabel}
          />
          <div className="stage-bottom">
            <LiveFeed events={pipeline.feed} summary={pipeline.summary} />
          </div>
        </div>
        <MetricsRail metrics={metrics} env={env} runs={runs} onSelectRun={openRun} />
      </main>

      <SlidePanel open={panel === "chat"} title="AI Copilot" subtitle="Questions & pipeline commands" onClose={() => setPanel(null)}>
        <ChatDock messages={messages} busy={chatBusy} options={options} onSend={sendChat} />
      </SlidePanel>

      <SlidePanel open={panel === "sql"} title="SQL Studio" subtitle={`Transpile ${sourceLabel} → ${targetLabel}`} onClose={() => setPanel(null)} wide>
        <SqlWorkbench
          sqlFiles={sqlFiles}
          sqlFile={sqlFile}
          setSqlFile={setSqlFile}
          sourceSql={sourceSql}
          setSourceSql={setSourceSql}
          targetSql={targetSql}
          status={transpileStatus}
          sourceLabel={sourceLabel}
          targetLabel={targetLabel}
          busy={transpileBusy}
          onLoad={loadSql}
          onTranspile={transpile}
        />
      </SlidePanel>

      <SlidePanel open={panel === "reports"} title="Artifacts" subtitle="Generated reports & docs" onClose={() => setPanel(null)} wide>
        <ReportsViewer artifacts={artifacts} previewPath={previewPath} preview={preview} onSelect={loadReport} />
      </SlidePanel>

      <SlidePanel
        open={panel === "run"}
        title={selectedRun ? `Run #${selectedRun}` : "Run inspector"}
        subtitle="Source vs target SQL"
        onClose={() => setPanel(null)}
        wide
      >
        <RunInspector runDetail={runDetail} />
      </SlidePanel>
    </div>
  );
}
