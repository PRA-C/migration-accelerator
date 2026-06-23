"""Backend helpers for the Gradio migration accelerator UI."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from accelarator.metadata import get_migration_run, init_metadata_db, list_migration_runs
from accelarator.migration_assistant.io_handlers import read_source_migration_files
from agents.registry import AGENT_PIPELINE


def env_status_html() -> str:
    """Connection / API key status badges."""
    checks = [
        ("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", "").strip()),
        ("TD_HOST", os.getenv("TD_HOST", os.getenv("TERADATA_HOST", "")).strip()),
        ("GCP_PROJECT_ID", os.getenv("GCP_PROJECT_ID", "").strip()),
    ]
    parts = []
    for name, val in checks:
        ok = bool(val)
        cls = "badge-ok" if ok else "badge-warn"
        label = "configured" if ok else "missing"
        parts.append(f'<span class="badge {cls}">{name}: {label}</span>')
    src = os.getenv("TD_DATABASE", os.getenv("TERADATA_DATABASE", "teradata"))
    tgt = os.getenv("GCP_TARGET_DATASET", "bigquery")
    parts.append(f'<span class="badge badge-info">Route: {src} → {tgt}</span>')
    return " ".join(parts)


def dashboard_metrics_html() -> str:
    init_metadata_db()
    runs = list_migration_runs()
    total = len(runs)
    migrated = sum(1 for r in runs if r.get("success"))
    recon_done = sum(1 for r in runs if r.get("recon_passed") is not None)
    recon_pass = sum(1 for r in runs if r.get("recon_passed") is True)
    recon_fail = sum(1 for r in runs if r.get("recon_passed") is False)

    def card(title: str, value: str | int, sub: str, accent: str) -> str:
        return f"""
        <div class="metric-card" style="--accent:{accent}">
          <div class="metric-label">{title}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-sub">{sub}</div>
        </div>"""

    cards = [
        card("Migration runs", total, "in metadata store", "#3b82f6"),
        card("Transpiled OK", migrated, f"of {total} files", "#22c55e"),
        card("Recon passed", recon_pass, f"{recon_fail} failed · {recon_done} compared", "#14b8a6"),
        card("LLM agents", len([a for a in AGENT_PIPELINE if a.uses_llm]), "in pipeline", "#a855f7"),
    ]
    return f'<div class="metric-grid">{"".join(cards)}</div>'


def agent_pipeline_html(active: str = "", completed: list[str] | None = None) -> str:
    """Visual stepper for the agent pipeline."""
    completed = completed or []
    steps = []
    for idx, spec in enumerate(AGENT_PIPELINE, start=1):
        node_id = spec.node_id
        if node_id in completed:
            state = "done"
        elif node_id == active:
            state = "active"
        else:
            state = "pending"
        role = "LLM" if spec.uses_llm else "TOOL"
        steps.append(
            f"""
            <div class="pipeline-step {state}">
              <div class="step-num">{idx}</div>
              <div class="step-body">
                <div class="step-name">{spec.name}</div>
                <div class="step-meta">{role} · {spec.description[:60]}…</div>
              </div>
            </div>"""
        )
    return f'<div class="pipeline-track">{"".join(steps)}</div>'


def runs_table_data() -> list[list]:
    init_metadata_db()
    rows: list[list] = []
    for run in sorted(list_migration_runs(), key=lambda r: int(r["run_id"]), reverse=True):
        rid = run["run_id"]
        src = run.get("source_file") or "—"
        ok = "✓" if run.get("success") else "✗"
        val = "✓" if run.get("validation_passed") else "✗"
        recon = "—"
        if run.get("recon_passed") is True:
            recon = "✓ pass"
        elif run.get("recon_passed") is False:
            recon = "✗ fail"
        created = str(run.get("created_at", ""))[:19]
        rows.append([rid, src, ok, val, recon, run.get("recon_ind") or "—", created])
    return rows


RUNS_HEADERS = ["Run", "Source file", "Migrate", "Validate", "Recon", "Status", "Created"]


def run_detail_markdown(run_id: int | str) -> tuple[str, str, str]:
    """Return (meta markdown, source sql, target sql)."""
    if not run_id:
        return "_Select a run to inspect._", "", ""
    run = get_migration_run(int(run_id))
    if not run:
        return f"Run `{run_id}` not found.", "", ""

    lines = [
        f"### Run {run['run_id']}: `{run.get('source_file') or '—'}`",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Request | `{run.get('request_id', '—')}` |",
        f"| Source → Target | `{run.get('source_type')}` → `{run.get('target_type')}` |",
        f"| Schemas | `{run.get('source_schema')}` → `{run.get('target_schema')}` |",
        f"| Transpile | {'✓' if run.get('success') else '✗'} `{run.get('status')}` |",
        f"| Validation | {'✓' if run.get('validation_passed') else '✗'} |",
        f"| Reconciliation | {run.get('recon_ind') or '—'} |",
    ]
    if run.get("error_message"):
        lines.append(f"| Error | {run['error_message'][:200]} |")
    if run.get("recon_result_path"):
        lines.append(f"| Report | `{run['recon_result_path']}` |")

    source = run.get("source_code") or "-- no source SQL stored --"
    target = run.get("generated_code") or "-- no generated SQL --"
    return "\n".join(lines), source, target


def list_source_sql_files() -> list[str]:
    return sorted(read_source_migration_files().keys())


def load_source_sql(filename: str) -> str:
    if not filename:
        return ""
    files = read_source_migration_files()
    return files.get(filename, "")


def artifacts_markdown() -> str:
    paths = [
        ("Pipeline report", Path("test_results/agent_pipeline_report.md")),
        ("Regression report", Path("test_results/regression_report.md")),
        ("Test catalog", Path("test_results/test_catalog.md")),
        ("Reconciliation report", Path("reconciliation/reconciliation_report.md")),
        ("Migration overview", Path("documentation/migration_overview.md")),
        ("Lineage", Path("documentation/lineage.md")),
        ("Lineage JSON", Path("documentation/lineage.json")),
    ]
    lines = ["### Generated artifacts", ""]
    for label, path in paths:
        if path.exists():
            mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- **{label}** — `{path}` _(updated {mtime})_")
        else:
            lines.append(f"- {label} — _not generated yet_")
    lines.extend(["", "### Documentation runs", ""])
    mig_dir = Path("documentation/migrations")
    if mig_dir.exists():
        for p in sorted(mig_dir.glob("*.md")):
            lines.append(f"- `{p}`")
    else:
        lines.append("_No per-run docs yet. Run **Generate docs**._")
    return "\n".join(lines)


def read_artifact_preview(relative_path: str, max_chars: int = 12000) -> str:
    if not relative_path or relative_path == "(select)":
        return ""
    path = Path(relative_path)
    if not path.exists():
        return f"File not found: {relative_path}"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n… _(truncated)_"
    return text


def list_artifact_paths() -> list[str]:
    options = ["(select)"]
    for p in [
        Path("test_results/agent_pipeline_report.md"),
        Path("test_results/regression_report.md"),
        Path("reconciliation/reconciliation_report.md"),
        Path("documentation/migration_overview.md"),
        Path("documentation/lineage.md"),
    ]:
        if p.exists():
            options.append(str(p).replace("\\", "/"))
    mig_dir = Path("documentation/migrations")
    if mig_dir.exists():
        options.extend(str(p).replace("\\", "/") for p in sorted(mig_dir.glob("*.md")))
    return options
