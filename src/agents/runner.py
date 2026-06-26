"""Run the LangGraph agent pipeline and write execution report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .graph import build_pipeline_graph
from .registry import AGENT_PIPELINE
from .state import PipelineState

PIPELINE_REPORT_PATH = Path("test_results/agent_pipeline_report.md")


def _default_state(**overrides: Any) -> PipelineState:
    base: PipelineState = {
        "phase": "start",
        "use_llm": True,
        "skip_synthetic": False,
        "skip_provision": False,
        "skip_migrate": False,
        "skip_recon": False,
        "skip_tests": False,
        "skip_docs": False,
        "include_integration_tests": False,
        "include_slow_tests": False,
        "source_database": "teradata",
        "target_database": "bigquery",
        "errors": [],
        "agent_log": [],
    }
    base.update(overrides)
    return base


def _write_pipeline_report(final_state: PipelineState) -> Path:
    PIPELINE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Agent Pipeline Report",
        "",
        f"**Generated:** {generated}  ",
        f"**Final phase:** {final_state.get('phase', 'unknown')}  ",
        "",
        "## Agent catalog",
        "",
        "| # | Agent | Role | LLM | Node |",
        "|---|-------|------|-----|------|",
    ]
    for idx, spec in enumerate(AGENT_PIPELINE, start=1):
        llm = "yes" if spec.uses_llm else "no"
        lines.append(f"| {idx} | {spec.name} | {spec.role} | {llm} | `{spec.node_id}` |")

    lines.extend(["", "## Execution log", ""])
    for entry in final_state.get("agent_log", []):
        status = entry.get("status", "?")
        agent = entry.get("agent", "?")
        role = entry.get("role", "tool")
        msg = entry.get("message", "")
        ms = entry.get("duration_ms", 0)
        lines.append(f"### {agent} ({role}) — {status}")
        lines.append("")
        lines.append(f"{msg}  ")
        if ms:
            lines.append(f"Duration: {ms:.1f} ms  ")
        lines.append("")

    errors = final_state.get("errors", [])
    if errors:
        lines.extend(["## Errors", ""])
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    lines.extend(["## Summary", ""])
    summary_fields = [
        ("Synthetic tables generated", final_state.get("synthetic_tables_generated")),
        ("Migrations succeeded", final_state.get("migration_succeeded")),
        ("Migrations failed", final_state.get("migration_failed")),
        ("Recon prepared", final_state.get("recon_prepared")),
        ("Recon compare passed", final_state.get("compare_passed")),
        ("Recon compare failed", final_state.get("compare_failed")),
        ("Tests passed", final_state.get("tests_passed")),
        ("Tests failed", final_state.get("tests_failed")),
        ("Recon report", final_state.get("recon_report_path")),
        ("Regression report", final_state.get("regression_report_path")),
        ("Documentation", final_state.get("docs_path")),
    ]
    for label, value in summary_fields:
        if value is not None and value != "":
            lines.append(f"- **{label}:** {value}")
    lines.append("")

    PIPELINE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return PIPELINE_REPORT_PATH


def run_pipeline(**config: Any) -> tuple[PipelineState, Path]:
    """Execute all agents sequentially. Returns final state and report path."""
    graph = build_pipeline_graph()
    initial = _default_state(**config)
    final_state = graph.invoke(initial)
    report_path = _write_pipeline_report(final_state)
    return final_state, report_path
