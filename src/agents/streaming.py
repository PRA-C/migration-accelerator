"""Stream LangGraph pipeline execution for real-time UI updates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .graph import GRAPH_NODE_ORDER, build_pipeline_graph
from .registry import AGENT_BY_NODE, AGENT_PIPELINE
from .runner import PIPELINE_REPORT_PATH, _default_state, _write_pipeline_report
from .state import AgentMessage, PipelineState

NODE_LABELS: dict[str, str] = {
    spec.node_id: spec.name for spec in AGENT_PIPELINE
}


@dataclass
class StreamEvent:
    """One real-time update for the UI."""

    phase: str
    active_node: str
    status_markdown: str
    chat_chunk: str
    done: bool = False
    node_status: str = "complete"  # "starting" | "complete"
    final_state: PipelineState | None = None
    report_path: str = ""


def _merge_state(state: PipelineState, patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if key in ("agent_log", "errors") and key in state:
            state[key] = list(state.get(key, [])) + list(value)  # type: ignore[arg-type]
        else:
            state[key] = value  # type: ignore[literal-required]


def _format_agent_line(entry: AgentMessage) -> str:
    status = entry.get("status", "?").upper()
    agent = entry.get("agent", "?")
    role = entry.get("role", "tool")
    msg = entry.get("message", "")
    ms = entry.get("duration_ms", 0.0)
    icon = "🤖" if role == "llm" else "⚙️"
    timing = f" ({ms:.0f} ms)" if ms else ""
    return f"{icon} **[{status}]** `{agent}` — {msg}{timing}"


def format_live_status(
    state: PipelineState,
    *,
    active_node: str = "",
    running: bool = False,
) -> str:
    """Build markdown for the live activity panel."""
    now = datetime.now().strftime("%H:%M:%S")
    phase = state.get("phase", "start")
    lines = [
        f"### Live activity `{now}`",
        "",
        f"**Phase:** `{phase}`  ",
    ]
    if active_node and running:
        label = NODE_LABELS.get(active_node, active_node)
        spec = AGENT_BY_NODE.get(active_node)
        role = spec.role if spec else "tool"
        lines.append(f"**Running:** `{label}` ({role}) ⏳")
        lines.append("")

    lines.extend(["#### Agent log", ""])
    log = state.get("agent_log", [])
    if not log:
        lines.append("_Waiting to start…_")
    else:
        for entry in log:
            lines.append(_format_agent_line(entry))
            lines.append("")

    errors = state.get("errors", [])
    if errors:
        lines.extend(["#### Errors", ""])
        for err in errors:
            lines.append(f"- ❌ {err}")
        lines.append("")

    summary_bits: list[str] = []
    for label, key in (
        ("migrations ok", "migration_succeeded"),
        ("migrations failed", "migration_failed"),
        ("recon passed", "compare_passed"),
        ("recon failed", "compare_failed"),
        ("tests passed", "tests_passed"),
        ("tests failed", "tests_failed"),
    ):
        val = state.get(key)  # type: ignore[literal-required]
        if val is not None:
            summary_bits.append(f"{label}={val}")
    if summary_bits:
        lines.extend(["---", f"**Summary:** {' · '.join(summary_bits)}"])

    return "\n".join(lines)


def format_final_chat_summary(state: PipelineState, report_path: Path) -> str:
    """Assistant message when pipeline completes."""
    lines = ["### Pipeline complete", ""]
    for entry in state.get("agent_log", []):
        lines.append(_format_agent_line(entry))

    lines.extend(["", "---", "**Artifacts**"])
    if state.get("recon_report_path"):
        lines.append(f"- Reconciliation: `{state['recon_report_path']}`")
    if state.get("regression_report_path"):
        lines.append(f"- Regression: `{state['regression_report_path']}`")
    if state.get("docs_path"):
        lines.append(f"- Documentation: `{state['docs_path']}/`")
    lines.append(f"- Pipeline report: `{report_path}`")

    errors = state.get("errors", [])
    if errors:
        lines.extend(["", f"⚠️ **{len(errors)} error(s)** — see activity log."])
    else:
        lines.append("")
        lines.append("✅ All agents finished.")
    return "\n".join(lines)


def _yield_node_start(
    state: PipelineState,
    node_name: str,
    chat_parts: list[str],
) -> StreamEvent:
    label = NODE_LABELS.get(node_name, node_name)
    chat_parts.append(f"\n---\n⏳ **{label}** running…\n")
    return StreamEvent(
        phase="running",
        active_node=node_name,
        node_status="starting",
        status_markdown=format_live_status(state, active_node=node_name, running=True),
        chat_chunk="".join(chat_parts),
    )


def stream_pipeline(**config: Any) -> Iterator[StreamEvent]:
    """Yield real-time events as each LangGraph node runs and completes."""
    graph = build_pipeline_graph()
    state = _default_state(**config)
    chat_parts: list[str] = ["🚀 **Starting migration agent pipeline…**\n"]

    yield StreamEvent(
        phase="start",
        active_node="",
        node_status="starting",
        status_markdown=format_live_status(state, running=True),
        chat_chunk="".join(chat_parts),
    )

    if GRAPH_NODE_ORDER:
        yield _yield_node_start(state, GRAPH_NODE_ORDER[0], chat_parts)

    for event in graph.stream(state, stream_mode="updates"):
        for node_name, patch in event.items():
            _merge_state(state, patch)
            label = NODE_LABELS.get(node_name, node_name)
            chat_parts.append(f"\n---\n▶️ **{label}** finished.\n")
            for entry in patch.get("agent_log", []):
                chat_parts.append(_format_agent_line(entry) + "\n")

            yield StreamEvent(
                phase=state.get("phase", ""),
                active_node=node_name,
                node_status="complete",
                status_markdown=format_live_status(state, active_node=node_name),
                chat_chunk="".join(chat_parts),
            )

            try:
                idx = GRAPH_NODE_ORDER.index(node_name)
            except ValueError:
                idx = -1
            if idx >= 0 and idx + 1 < len(GRAPH_NODE_ORDER):
                yield _yield_node_start(state, GRAPH_NODE_ORDER[idx + 1], chat_parts)

    report_path = _write_pipeline_report(state)
    chat_parts.append("\n" + format_final_chat_summary(state, report_path))

    yield StreamEvent(
        phase=state.get("phase", "done"),
        active_node="",
        status_markdown=format_live_status(state),
        chat_chunk="".join(chat_parts),
        done=True,
        final_state=state,
        report_path=str(report_path),
    )


def _looks_like_question(text: str) -> bool:
    """Route questions to Claude instead of pipeline command handlers."""
    lower = text.strip().lower()
    if lower.endswith("?"):
        return True
    starters = (
        "what ", "why ", "how ", "when ", "where ", "who ",
        "can you ", "could you ", "would you ", "please explain",
        "explain ", "tell me ", "describe ", "is there ", "are there ",
        "does ", "do ", "should i ", "help me understand",
    )
    return any(lower.startswith(s) for s in starters)


def _is_exact_command(text: str, commands: set[str]) -> bool:
    return text.strip().lower().rstrip("!.") in commands


def parse_user_intent(message: str) -> tuple[str, dict[str, Any] | None]:
    """
    Map chat text to a pipeline action.

    Returns (action, config_overrides). action is one of:
    pipeline | status | help | chat | migrate_sql | migrate_file
    """
    text = message.strip()
    lower = text.lower()

    if not text:
        return "help", None

    if _is_exact_command(text, {"help", "?", "commands"}):
        return "help", None

    # Questions go to LLM even if they mention migrate/reconcile/etc.
    if _looks_like_question(text):
        return "chat", None

    if _is_exact_command(text, {"status"}) or lower in {
        "list runs", "show runs", "migration runs",
    }:
        return "status", None

    pipeline_config: dict[str, Any] = {
        "skip_provision": True,
        "skip_migrate": True,
        "skip_recon": True,
        "skip_tests": True,
        "skip_docs": True,
    }

    full_cmds = {
        "run full pipeline", "full pipeline", "run all", "run everything",
        "start migration", "full migration", "end to end", "e2e",
    }
    if lower in full_cmds or lower.startswith("run full pipeline"):
        return "pipeline", {k: False for k in pipeline_config}

    if lower in {"provision", "setup schema", "setup schemas", "init teradata"}:
        return "pipeline", {**pipeline_config, "skip_provision": False}

    migrate_cmds = {
        "migrate", "migrate all", "migrate all sql files", "transpile",
        "transpile all", "run migrate",
    }
    if lower in migrate_cmds or lower.startswith("migrate all"):
        return "pipeline", {**pipeline_config, "skip_provision": False, "skip_migrate": False}

    recon_cmds = {"reconcile", "reconcile all", "reconcile all runs", "recon", "compare"}
    if lower in recon_cmds or lower.startswith("reconcile"):
        return "pipeline", {**pipeline_config, "skip_recon": False}

    test_cmds = {"run tests", "run regression tests", "regression", "test suite", "tests"}
    if lower in test_cmds or lower.startswith("run regression"):
        overrides = {
            **pipeline_config,
            "skip_tests": False,
            "include_integration_tests": "integration" in lower,
            "include_slow_tests": "slow" in lower or "integration" in lower,
        }
        return "pipeline", overrides

    doc_cmds = {"generate docs", "generate documentation", "document", "documentation", "lineage", "docs"}
    if lower in doc_cmds or lower.startswith("generate doc"):
        return "pipeline", {**pipeline_config, "skip_docs": False}

    if re.search(r"\b(select|with|insert|create)\b", lower) and len(text) > 80:
        return "migrate_sql", {"sql": text}

    file_match = re.search(r"([\w_]+\.(?:sql|proc|txt))", text, re.IGNORECASE)
    if file_match and re.search(r"\b(migrate|transpile|convert)\b", lower):
        return "migrate_file", {"filename": file_match.group(1)}

    return "chat", None


def migration_status_markdown() -> str:
    """Summary of runs in metadata for status command."""
    from accelarator.metadata import init_metadata_db, list_migration_runs

    init_metadata_db()
    runs = list_migration_runs()
    if not runs:
        return "No migration runs in metadata yet. Try **run full pipeline** or **migrate**."

    lines = ["### Migration runs", "", "| Run | File | Status | Recon |", "|-----|------|--------|-------|"]
    for run in sorted(runs, key=lambda r: int(r["run_id"])):
        rid = run["run_id"]
        src = run.get("source_file") or "—"
        ok = "✅" if run.get("success") else "❌"
        recon = "✅" if run.get("recon_passed") else ("❌" if run.get("recon_passed") is False else "—")
        lines.append(f"| {rid} | `{src}` | {ok} | {recon} |")
    return "\n".join(lines)


HELP_MARKDOWN = """
### Migration Accelerator — commands

Type any of these in the chat:

| Command | Action |
|---------|--------|
| **run full pipeline** | Provision → migrate → reconcile → test → document |
| **provision** | Setup Teradata + BigQuery schemas only |
| **migrate** / **transpile** | Provision + transpile all SQL files |
| **reconcile** | Prepare + compare reconciliation CSVs |
| **run tests** | Regression test suite |
| **generate docs** | Migration documentation + lineage |
| **status** | List migration runs from metadata |
| **migrate `file.sql`** | Transpile one source file |

Use the **Pipeline options** panel to toggle LLM, integration tests, etc.

Ask anything else — the assistant uses Claude for migration Q&A.

**LLM chat:** ask a question ending with `?` or starting with *how/what/why*.
**Commands:** exact phrases like `migrate`, `reconcile`, `run full pipeline` run agents (not chat).
"""
