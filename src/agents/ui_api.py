"""JSON API helpers for React frontend."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from accelarator.metadata import get_migration_run, init_metadata_db, list_migration_runs
from accelarator.migration_assistant.io_handlers import read_source_migration_files

from .graph import GRAPH_NODE_ORDER
from .registry import AGENT_BY_NODE, AGENT_PIPELINE, graph_node_uses_llm


def env_status() -> list[dict]:
    checks = [
        ("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", "").strip()),
        ("TD_HOST", os.getenv("TD_HOST", os.getenv("TERADATA_HOST", "")).strip()),
        ("GCP_PROJECT_ID", os.getenv("GCP_PROJECT_ID", "").strip()),
    ]
    rows = [
        {"name": name, "configured": bool(val), "label": "configured" if val else "missing"}
        for name, val in checks
    ]
    rows.append({
        "name": "route",
        "configured": True,
        "label": f"{os.getenv('TD_DATABASE', 'teradata')} -> {os.getenv('GCP_TARGET_DATASET', 'bigquery')}",
    })
    return rows


def dashboard_metrics() -> dict:
    init_metadata_db()
    runs = list_migration_runs()
    total = len(runs)
    migrated = sum(1 for r in runs if r.get("success"))
    recon_pass = sum(1 for r in runs if r.get("recon_passed") is True)
    recon_fail = sum(1 for r in runs if r.get("recon_passed") is False)
    recon_done = sum(1 for r in runs if r.get("recon_passed") is not None)
    return {
        "total_runs": total,
        "migrated_ok": migrated,
        "recon_passed": recon_pass,
        "recon_failed": recon_fail,
        "recon_compared": recon_done,
        "llm_agents": sum(1 for a in AGENT_PIPELINE if a.uses_llm),
    }


def agent_catalog() -> list[dict]:
    return [
        {
            "index": i,
            "node_id": s.node_id,
            "name": s.name,
            "role": s.role,
            "uses_llm": s.uses_llm,
            "description": s.description,
            "wraps": s.wraps,
        }
        for i, s in enumerate(AGENT_PIPELINE, 1)
    ]


def pipeline_steps(completed: list[str] | None = None, active: str = "") -> list[dict]:
    completed = completed or []
    steps: list[dict] = []
    for i, node_id in enumerate(GRAPH_NODE_ORDER, 1):
        spec = AGENT_BY_NODE.get(node_id)
        steps.append({
            "index": i,
            "node_id": node_id,
            "name": spec.name if spec else node_id,
            "role": spec.role if spec else "tool",
            "uses_llm": graph_node_uses_llm(node_id),
            "state": (
                "done" if node_id in completed
                else "active" if node_id == active
                else "pending"
            ),
        })
    return steps


def list_runs() -> list[dict]:
    init_metadata_db()
    out = []
    for run in sorted(list_migration_runs(), key=lambda r: int(r["run_id"]), reverse=True):
        out.append({
            "run_id": run["run_id"],
            "source_file": run.get("source_file"),
            "success": bool(run.get("success")),
            "validation_passed": bool(run.get("validation_passed")),
            "recon_passed": run.get("recon_passed"),
            "recon_ind": run.get("recon_ind"),
            "created_at": str(run.get("created_at", ""))[:19],
        })
    return out


def get_run_detail(run_id: int) -> dict | None:
    run = get_migration_run(run_id)
    if not run:
        return None
    return {
        "run_id": run["run_id"],
        "request_id": run.get("request_id"),
        "source_file": run.get("source_file"),
        "source_type": run.get("source_type"),
        "target_type": run.get("target_type"),
        "source_schema": run.get("source_schema"),
        "target_schema": run.get("target_schema"),
        "status": run.get("status"),
        "success": bool(run.get("success")),
        "validation_passed": bool(run.get("validation_passed")),
        "recon_ind": run.get("recon_ind"),
        "recon_passed": run.get("recon_passed"),
        "error_message": run.get("error_message"),
        "recon_result_path": run.get("recon_result_path"),
        "source_sql": run.get("source_code") or "",
        "target_sql": run.get("generated_code") or "",
        "created_at": str(run.get("created_at", "")),
    }


def list_sql_files() -> list[str]:
    return sorted(read_source_migration_files().keys())


def load_sql_file(name: str) -> str:
    return read_source_migration_files().get(name, "")


def list_artifacts() -> list[dict]:
    entries = [
        ("Pipeline report", Path("test_results/agent_pipeline_report.md")),
        ("Regression report", Path("test_results/regression_report.md")),
        ("Reconciliation report", Path("reconciliation/reconciliation_report.md")),
        ("Migration overview", Path("documentation/migration_overview.md")),
        ("Lineage", Path("documentation/lineage.md")),
    ]
    items = []
    for label, path in entries:
        items.append({
            "label": label,
            "path": str(path).replace("\\", "/"),
            "exists": path.exists(),
            "updated": (
                datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                if path.exists() else None
            ),
        })
    mig_dir = Path("documentation/migrations")
    if mig_dir.exists():
        for p in sorted(mig_dir.glob("*.md")):
            items.append({
                "label": p.name,
                "path": str(p).replace("\\", "/"),
                "exists": True,
                "updated": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return items


def read_artifact(path: str, max_chars: int = 12000) -> str:
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n… (truncated)"
    return text
