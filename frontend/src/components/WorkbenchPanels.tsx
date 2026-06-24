import ReactMarkdown from "react-markdown";

type Props = {
  sqlFiles: string[];
  sqlFile: string;
  setSqlFile: (f: string) => void;
  sourceSql: string;
  setSourceSql: (s: string) => void;
  targetSql: string;
  status: string;
  onLoad: () => void;
  onTranspile: () => void;
};

export function SqlWorkbench({
  sqlFiles,
  sqlFile,
  setSqlFile,
  sourceSql,
  setSourceSql,
  targetSql,
  status,
  onLoad,
  onTranspile,
}: Props) {
  return (
    <div className="sql-workbench">
      <div className="sql-toolbar">
        <select value={sqlFile} onChange={(e) => setSqlFile(e.target.value)}>
          {sqlFiles.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
        <button type="button" className="btn-ghost" onClick={onLoad}>Load file</button>
        <button type="button" className="btn-glow" onClick={onTranspile}>Transpile →</button>
        <span className="sql-status">{status}</span>
      </div>
      <div className="sql-panes">
        <div className="sql-pane">
          <div className="pane-label teradata">Teradata source</div>
          <textarea value={sourceSql} onChange={(e) => setSourceSql(e.target.value)} spellCheck={false} />
        </div>
        <div className="sql-arrow">⇄</div>
        <div className="sql-pane">
          <div className="pane-label bigquery">BigQuery target</div>
          <textarea readOnly value={targetSql} spellCheck={false} />
        </div>
      </div>
    </div>
  );
}

type ReportProps = {
  artifacts: { label: string; path: string; exists: boolean }[];
  previewPath: string;
  preview: string;
  onSelect: (path: string) => void;
};

export function ReportsViewer({ artifacts, previewPath, preview, onSelect }: ReportProps) {
  return (
    <div className="reports-viewer">
      <select value={previewPath} onChange={(e) => onSelect(e.target.value)}>
        <option value="">Select artifact…</option>
        {artifacts.filter((a) => a.exists).map((a) => (
          <option key={a.path} value={a.path}>{a.label}</option>
        ))}
      </select>
      {preview && (
        <div className="report-md">
          <ReactMarkdown>{preview}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

type RunProps = {
  runDetail: Record<string, unknown> | null;
};

export function RunInspector({ runDetail }: RunProps) {
  if (!runDetail) return <div className="feed-empty">Select a run from the rail</div>;
  return (
    <div className="run-inspector">
      <div className="sql-panes">
        <div className="sql-pane">
          <div className="pane-label teradata">Teradata</div>
          <textarea readOnly value={String(runDetail.source_sql || "")} spellCheck={false} />
        </div>
        <div className="sql-pane">
          <div className="pane-label bigquery">BigQuery</div>
          <textarea readOnly value={String(runDetail.target_sql || "")} spellCheck={false} />
        </div>
      </div>
    </div>
  );
}
