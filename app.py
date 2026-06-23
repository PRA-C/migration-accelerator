"""
Migration Accelerator — professional Gradio control plane.

Launch:  uv run python app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import gradio as gr

from accelarator.metadata import init_metadata_db
from accelarator.migration_assistant.io_handlers import (
    CodeType,
    MigrationRequest,
    OutputFormat,
    SourceDatabase,
    TargetDatabase,
    read_source_migration_files,
)
from accelarator.migration_assistant.transpiler import transpile_request
from agents.registry import AGENT_PIPELINE
from agents.streaming import (
    HELP_MARKDOWN,
    format_live_status,
    migration_status_markdown,
    parse_user_intent,
    stream_pipeline,
)
from agents.ui_services import (
    RUNS_HEADERS,
    agent_pipeline_html,
    artifacts_markdown,
    dashboard_metrics_html,
    env_status_html,
    list_artifact_paths,
    list_source_sql_files,
    load_source_sql,
    read_artifact_preview,
    run_detail_markdown,
    runs_table_data,
)

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

CSS = """
/* ── Base ─────────────────────────────────────────────────────────────── */
.gradio-container {
  max-width: 1440px !important;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif !important;
}
#header-bar {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
  border-radius: 16px;
  padding: 1.5rem 2rem;
  margin-bottom: 1rem;
  border: 1px solid rgba(59,130,246,.25);
  box-shadow: 0 8px 32px rgba(0,0,0,.35);
}
#header-bar h1 { color: #f8fafc !important; margin: 0 !important; font-size: 1.75rem !important; }
#header-bar p  { color: #94a3b8 !important; margin: .35rem 0 0 !important; }

/* ── Badges ───────────────────────────────────────────────────────────── */
.badge {
  display: inline-block;
  padding: .25rem .65rem;
  border-radius: 999px;
  font-size: .72rem;
  font-weight: 600;
  margin: .15rem .25rem;
  letter-spacing: .02em;
}
.badge-ok   { background: rgba(34,197,94,.15);  color: #4ade80; border: 1px solid rgba(34,197,94,.35); }
.badge-warn { background: rgba(251,191,36,.12); color: #fbbf24; border: 1px solid rgba(251,191,36,.35); }
.badge-info { background: rgba(59,130,246,.12);  color: #60a5fa; border: 1px solid rgba(59,130,246,.35); }

/* ── Metric cards ─────────────────────────────────────────────────────── */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin: .5rem 0 1rem;
}
.metric-card {
  background: linear-gradient(145deg, #1e293b, #0f172a);
  border: 1px solid rgba(255,255,255,.08);
  border-left: 3px solid var(--accent, #3b82f6);
  border-radius: 12px;
  padding: 1rem 1.15rem;
}
.metric-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; color: #94a3b8; }
.metric-value { font-size: 2rem; font-weight: 700; color: #f1f5f9; line-height: 1.2; }
.metric-sub   { font-size: .78rem; color: #64748b; margin-top: .25rem; }

/* ── Pipeline stepper ─────────────────────────────────────────────────── */
.pipeline-track { display: flex; flex-direction: column; gap: .5rem; }
.pipeline-step {
  display: flex; align-items: flex-start; gap: .75rem;
  padding: .65rem .85rem; border-radius: 10px;
  border: 1px solid rgba(255,255,255,.06);
  background: #1e293b;
  transition: all .2s;
}
.pipeline-step.done    { border-color: rgba(34,197,94,.4);  background: rgba(34,197,94,.08); }
.pipeline-step.active  { border-color: rgba(59,130,246,.6); background: rgba(59,130,246,.12);
                         box-shadow: 0 0 0 2px rgba(59,130,246,.2); }
.pipeline-step.pending { opacity: .55; }
.step-num {
  width: 28px; height: 28px; border-radius: 50%;
  background: #334155; color: #e2e8f0;
  display: flex; align-items: center; justify-content: center;
  font-size: .75rem; font-weight: 700; flex-shrink: 0;
}
.pipeline-step.done   .step-num { background: #16a34a; }
.pipeline-step.active .step-num { background: #2563eb; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }
.step-name { font-weight: 600; color: #f1f5f9; font-size: .88rem; }
.step-meta { font-size: .72rem; color: #94a3b8; margin-top: .15rem; }

/* ── Panels ───────────────────────────────────────────────────────────── */
.panel-title {
  font-size: .7rem; text-transform: uppercase; letter-spacing: .1em;
  color: #64748b; font-weight: 700; margin-bottom: .5rem;
}
#activity-panel textarea, #activity-panel .prose {
  font-family: 'Cascadia Code', 'Fira Code', monospace !important;
  font-size: .8rem !important;
}
footer { display: none !important; }
"""

HEADER_HTML = """
<div id="header-bar">
  <h1>⚡ Migration Accelerator</h1>
  <p>Teradata → BigQuery · LangGraph agent pipeline · LLM transpilation · reconciliation · docs</p>
</div>
"""


# ---------------------------------------------------------------------------
# Business logic (shared by tabs)
# ---------------------------------------------------------------------------

def _pipeline_config(
    use_llm: bool,
    skip_provision: bool,
    skip_migrate: bool,
    skip_recon: bool,
    skip_tests: bool,
    skip_docs: bool,
    integration_tests: bool,
    intent_overrides: dict | None = None,
) -> dict:
    base = {
        "use_llm": use_llm,
        "skip_provision": skip_provision,
        "skip_migrate": skip_migrate,
        "skip_recon": skip_recon,
        "skip_tests": skip_tests,
        "skip_docs": skip_docs,
        "include_integration_tests": integration_tests,
        "include_slow_tests": integration_tests,
    }
    if intent_overrides:
        for key, val in intent_overrides.items():
            if key in base or key.startswith("include_"):
                base[key] = val
    return base


def _format_api_error(exc: Exception, *, context: str = "request") -> str:
    """User-friendly error for the chat UI (avoids Gradio traceback overlay)."""
    name = type(exc).__name__
    if "InternalServerError" in name or "500" in str(exc):
        return (
            f"**{context.title()} temporarily unavailable**\n\n"
            "Anthropic returned HTTP 500 (their servers). Wait 10-30 seconds and retry.\n\n"
            "**Workaround:** Use the **Operations** tab — Full pipeline / Migrate / Reconcile "
            "do not need freeform chat."
        )
    if "RateLimitError" in name or "429" in str(exc):
        return (
            f"**Rate limit during {context}**\n\n"
            "Too many LLM requests. Wait a minute, or run one pipeline step at a time."
        )
    if "AuthenticationError" in name or "401" in str(exc):
        return "**Invalid API key** — check `ANTHROPIC_API_KEY` in `.env`."
    return f"**Error during {context}** (`{name}`). Check the terminal for details."


def _is_greeting(text: str) -> bool:
    """Only exact short greetings use the instant welcome (not LLM)."""
    t = text.strip().lower().rstrip("!.?")
    return t in {"hi", "hello", "hey", "yo"}


def _greeting_reply() -> str:
    return """Hello! I'm your **Migration Accelerator** copilot.

**Try these commands:**
| Command | Action |
|---------|--------|
| `run full pipeline` | Provision, migrate, reconcile, test, document |
| `migrate` | Transpile all SQL files |
| `reconcile` | Compare Teradata vs BigQuery results |
| `status` | List migration runs |
| `help` | Full command reference |

**Tip:** The **Operations** tab has one-click buttons with live agent progress.

Ask a **question** (e.g. `How does reconciliation work?`) for a **Claude** answer."""


def _llm_chat(message: str, history: list[dict]) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return "Set `ANTHROPIC_API_KEY` in `.env` to use the AI assistant."

    from accelarator.llm import ask_claude

    # Keep prompt compact — large history + nested instructions can aggravate transient API errors.
    recent = [
        m for m in history[-6:]
        if m.get("content") and not str(m["content"]).startswith("_")
    ]
    context = "\n".join(
        f"{m['role']}: {m['content'][:300]}" for m in recent
    )
    prompt = f"Conversation:\n{context}\n\nUser: {message}\n\nReply helpfully and concisely."
    try:
        return ask_claude(
            prompt=prompt,
            system=(
                "You are the Migration Accelerator copilot for Teradata to BigQuery SQL migration. "
                "Answer questions about migration, reconciliation, testing, and documentation."
            ),
            max_tokens=1400,
        )
    except Exception as exc:
        return _format_api_error(exc, context="AI chat")


def _transpile_file(filename: str) -> tuple[str, str]:
    files = read_source_migration_files()
    if not filename or filename not in files:
        return "", f"File not found: {filename}"
    try:
        req = MigrationRequest(
            source=SourceDatabase.TERADATA,
            target=TargetDatabase.BIGQUERY,
            output_format=OutputFormat.TARGET_SQL_ONLY,
            code=files[filename],
            code_type=CodeType.SQL_QUERY,
            source_filename=filename,
        )
        resp = transpile_request(req)
    except Exception as exc:
        return "", _format_api_error(exc, context=f"transpile `{filename}`")
    out = resp.transpilation.generated_code or ""
    status = f"**{filename}** -> `{resp.status.value}`"
    if resp.errors:
        status += "\n\n" + "\n".join(f"- {e}" for e in resp.errors)
    return out, status


def _transpile_adhoc(sql: str) -> tuple[str, str]:
    if not sql.strip():
        return "", "Paste Teradata SQL first."
    try:
        req = MigrationRequest(
            source=SourceDatabase.TERADATA,
            target=TargetDatabase.BIGQUERY,
            output_format=OutputFormat.TARGET_SQL_ONLY,
            code=sql,
            code_type=CodeType.SQL_QUERY,
            source_filename="studio.sql",
        )
        resp = transpile_request(req)
    except Exception as exc:
        return "", _format_api_error(exc, context="transpile SQL")
    out = resp.transpilation.generated_code or ""
    return out, f"Status: `{resp.status.value}`"


def _stream_ops(
    use_llm: bool,
    skip_provision: bool,
    skip_migrate: bool,
    skip_recon: bool,
    skip_tests: bool,
    skip_docs: bool,
    integration_tests: bool,
    preset: str = "full",
):
    """Generator for Operations tab — streams pipeline + stepper."""
    enable: dict[str, list[str]] = {
        "full": ["skip_provision", "skip_migrate", "skip_recon", "skip_tests", "skip_docs"],
        "provision": ["skip_provision"],
        "migrate": ["skip_provision", "skip_migrate"],
        "recon": ["skip_recon"],
        "tests": ["skip_tests"],
        "docs": ["skip_docs"],
    }
    config: dict = {
        "use_llm": use_llm,
        "skip_provision": True,
        "skip_migrate": True,
        "skip_recon": True,
        "skip_tests": True,
        "skip_docs": True,
        "include_integration_tests": integration_tests,
        "include_slow_tests": integration_tests,
    }
    for key in enable.get(preset, enable["full"]):
        config[key] = False
    if skip_provision:
        config["skip_provision"] = True
    if skip_migrate:
        config["skip_migrate"] = True
    if skip_recon:
        config["skip_recon"] = True
    if skip_tests:
        config["skip_tests"] = True
    if skip_docs:
        config["skip_docs"] = True

    init_metadata_db()
    completed: list[str] = []
    log_md = format_live_status({"phase": "starting", "agent_log": [], "errors": []}, running=True)
    summary = f"### Running: `{preset}` pipeline\n\n"

    yield (
        agent_pipeline_html(active="environment_provisioner", completed=completed),
        log_md,
        summary + "_Starting agents…_",
        dashboard_metrics_html(),
        runs_table_data(),
    )

    try:
        for event in stream_pipeline(**config):
            if event.active_node and event.active_node not in completed:
                completed.append(event.active_node)
            active = "" if event.done else ""
            yield (
                agent_pipeline_html(active=active, completed=completed),
                event.status_markdown,
                event.chat_chunk,
                dashboard_metrics_html(),
                runs_table_data(),
            )
    except Exception as exc:
        err = _format_api_error(exc, context=f"`{preset}` pipeline")
        yield (
            agent_pipeline_html(completed=completed),
            err,
            f"### Pipeline failed\n\n{err}",
            dashboard_metrics_html(),
            runs_table_data(),
        )


def _handle_chat_impl(
    message: str,
    history: list[dict],
    use_llm: bool,
    skip_provision: bool,
    skip_migrate: bool,
    skip_recon: bool,
    skip_tests: bool,
    skip_docs: bool,
    integration_tests: bool,
):
    if not message or not message.strip():
        yield history, "_Ready._"
        return

    history = history + [{"role": "user", "content": message.strip()}]

    if _is_greeting(message):
        history = history + [{"role": "assistant", "content": _greeting_reply()}]
        yield history, "_Ready._"
        return

    action, overrides = parse_user_intent(message)

    if action == "help":
        history = history + [{"role": "assistant", "content": HELP_MARKDOWN}]
        yield history, "_Ready._"
        return

    if action == "status":
        history = history + [{"role": "assistant", "content": migration_status_markdown()}]
        yield history, "_Ready._"
        return

    if action == "migrate_file" and overrides:
        history = history + [{"role": "assistant", "content": "⏳ Transpiling…"}]
        yield history, "Transpiling…"
        out, status = _transpile_file(overrides["filename"])
        body = status + ("\n\n```sql\n" + out[:3000] + "\n```" if out else "")
        history = history[:-1] + [{"role": "assistant", "content": body}]
        yield history, "_Done._"
        return

    if action == "migrate_sql" and overrides:
        out, status = _transpile_adhoc(overrides["sql"])
        body = status + ("\n\n```sql\n" + out[:3000] + "\n```" if out else "")
        history = history + [{"role": "assistant", "content": body}]
        yield history, "_Done._"
        return

    if action == "pipeline" and overrides is not None:
        config = _pipeline_config(
            use_llm, skip_provision, skip_migrate, skip_recon, skip_tests, skip_docs,
            integration_tests, overrides,
        )
        init_metadata_db()
        history = history + [{"role": "assistant", "content": "Pipeline starting..."}]
        yield history, format_live_status({"phase": "start", "agent_log": [], "errors": []})
        try:
            for event in stream_pipeline(**config):
                history = history[:-1] + [{"role": "assistant", "content": event.chat_chunk}]
                yield history, event.status_markdown
        except Exception as exc:
            err = _format_api_error(exc, context="pipeline")
            history = history[:-1] + [{"role": "assistant", "content": err}]
            yield history, err
        return

    if not use_llm:
        history = history + [{
            "role": "assistant",
            "content": (
                "LLM is disabled in settings. Use **Operations** tab for tool-only steps, "
                "or enable **LLM agents** for chat."
            ),
        }]
        yield history, "_Ready._"
        return

    history = history + [{"role": "assistant", "content": "Thinking..."}]
    yield history, "Claude (LLM) responding..."
    try:
        reply = _llm_chat(message, history[:-2])
        if reply and not reply.startswith("**Error") and not reply.startswith("Set `ANTHROPIC"):
            reply = f"_Claude · migration copilot_\n\n{reply}"
    except Exception as exc:
        reply = _format_api_error(exc, context="AI chat")
    history = history[:-1] + [{"role": "assistant", "content": reply}]
    yield history, "_Ready._"


def _handle_chat(
    message: str,
    history: list[dict],
    use_llm: bool,
    skip_provision: bool,
    skip_migrate: bool,
    skip_recon: bool,
    skip_tests: bool,
    skip_docs: bool,
    integration_tests: bool,
):
    """Outer wrapper — never let exceptions reach Gradio error toast."""
    try:
        yield from _handle_chat_impl(
            message, history, use_llm, skip_provision, skip_migrate,
            skip_recon, skip_tests, skip_docs, integration_tests,
        )
    except Exception as exc:
        err = _format_api_error(exc, context="chat")
        hist = list(history or [])
        if message and message.strip():
            hist = hist + [{"role": "user", "content": message.strip()}]
        hist = hist + [{"role": "assistant", "content": err}]
        yield hist, err


def _refresh_dashboard():
    return (
        dashboard_metrics_html(),
        runs_table_data(),
        f'<div id="env-badges">{env_status_html()}</div>',
        artifacts_markdown(),
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Migration Accelerator") as demo:
        gr.HTML(HEADER_HTML)

        # Shared settings (referenced by multiple tabs)
        with gr.Accordion("⚙️ Global pipeline settings", open=False):
            with gr.Row():
                use_llm = gr.Checkbox(value=True, label="LLM agents (transpile, analysis, docs)")
                integration_tests = gr.Checkbox(value=False, label="Integration tests")
            with gr.Row():
                skip_provision = gr.Checkbox(value=False, label="Skip provision")
                skip_migrate = gr.Checkbox(value=False, label="Skip migrate")
                skip_recon = gr.Checkbox(value=False, label="Skip recon")
                skip_tests = gr.Checkbox(value=False, label="Skip tests")
                skip_docs = gr.Checkbox(value=False, label="Skip docs")

        env_badges = gr.HTML(f'<div id="env-badges">{env_status_html()}</div>')

        with gr.Tabs():
            # ── Dashboard ──────────────────────────────────────────────────
            with gr.Tab("📊 Dashboard"):
                metrics = gr.HTML(dashboard_metrics_html())
                with gr.Row():
                    refresh_dash = gr.Button("↻ Refresh", size="sm")
                runs_df = gr.Dataframe(
                    headers=RUNS_HEADERS,
                    value=runs_table_data(),
                    label="Recent migration runs",
                    interactive=False,
                    wrap=True,
                )
                gr.Markdown("#### Agent pipeline")
                dash_pipeline = gr.HTML(agent_pipeline_html())

            # ── Operations ───────────────────────────────────────────────
            with gr.Tab("🚀 Operations"):
                gr.Markdown(
                    "Run the LangGraph agent pipeline with **live stepper** and activity log."
                )
                with gr.Row():
                    op_full = gr.Button("▶ Full pipeline", variant="primary")
                    op_prov = gr.Button("Provision")
                    op_mig = gr.Button("Migrate")
                    op_rec = gr.Button("Reconcile")
                    op_test = gr.Button("Tests")
                    op_docs = gr.Button("Docs")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1):
                        op_stepper = gr.HTML(agent_pipeline_html())
                    with gr.Column(scale=1):
                        op_activity = gr.Markdown(
                            value="_Activity log appears here during runs._",
                            label="Live activity",
                        )
                op_summary = gr.Markdown(label="Run summary")

            # ── AI Assistant ─────────────────────────────────────────────
            with gr.Tab("💬 AI Assistant"):
                with gr.Row():
                    with gr.Column(scale=3):
                        chatbot = gr.Chatbot(label="Migration copilot", height=480)
                        with gr.Row():
                            chat_in = gr.Textbox(
                                placeholder="Ask anything · run full pipeline · migrate file.sql · status",
                                show_label=False,
                                scale=5,
                                lines=2,
                            )
                            chat_send = gr.Button("Send", variant="primary", scale=1)
                        with gr.Row():
                            for label, text in [
                                ("Full run", "run full pipeline"),
                                ("Migrate", "migrate"),
                                ("Reconcile", "reconcile"),
                                ("Docs", "generate docs"),
                                ("Ask Claude", "How does the migration pipeline work?"),
                            ]:
                                b = gr.Button(label, size="sm")
                                b.click(lambda t=text: t, outputs=chat_in)
                    with gr.Column(scale=2):
                        chat_activity = gr.Markdown(
                            value="_Agent activity during pipeline commands._",
                            label="Activity",
                        )
                        gr.Markdown(
                            "**Commands** run the pipeline (no chat LLM). "
                            "**Questions** (`?` or *how/what/why*) go to **Claude**. "
                            "Enable **LLM agents** in settings above."
                        )

            # ── Migrations ───────────────────────────────────────────────
            with gr.Tab("📁 Migrations"):
                run_ids = [r[0] for r in runs_table_data()]
                with gr.Row():
                    run_select = gr.Dropdown(
                        choices=run_ids,
                        label="Select run",
                        value=run_ids[0] if run_ids else None,
                    )
                    refresh_runs = gr.Button("↻ Refresh runs", size="sm")
                run_meta = gr.Markdown("_Select a run._")
                with gr.Row():
                    run_source = gr.Code(label="Teradata source SQL", language="sql", lines=14)
                    run_target = gr.Code(label="BigQuery target SQL", language="sql", lines=14)

            # ── SQL Studio ───────────────────────────────────────────────
            with gr.Tab("🛠️ SQL Studio"):
                files = list_source_sql_files()
                with gr.Row():
                    file_pick = gr.Dropdown(
                        choices=files,
                        label="Source migration file",
                        value=files[0] if files else None,
                    )
                    studio_load = gr.Button("Load", size="sm")
                    studio_run = gr.Button("⚡ Transpile to BigQuery", variant="primary", size="sm")
                with gr.Row():
                    studio_source = gr.Code(label="Teradata SQL", language="sql", lines=16)
                    studio_target = gr.Code(label="Generated BigQuery SQL", language="sql", lines=16)
                studio_status = gr.Markdown()

            # ── Reports ────────────────────────────────────────────────
            with gr.Tab("📄 Reports"):
                art_list = gr.Markdown(artifacts_markdown())
                with gr.Row():
                    art_pick = gr.Dropdown(
                        choices=list_artifact_paths(),
                        label="Preview artifact",
                        value="(select)",
                    )
                    art_refresh = gr.Button("↻ Refresh list", size="sm")
                art_preview = gr.Markdown(label="Preview")

            # ── Agents ─────────────────────────────────────────────────
            with gr.Tab("🤖 Agents"):
                agent_rows = [
                    [i, s.name, s.role.upper(), "Yes" if s.uses_llm else "No", s.wraps]
                    for i, s in enumerate(AGENT_PIPELINE, 1)
                ]
                gr.Dataframe(
                    headers=["#", "Agent", "Role", "LLM", "Wraps"],
                    value=agent_rows,
                    interactive=False,
                    label="Sequential agent catalog",
                )
                gr.HTML(agent_pipeline_html())

        # ── Wiring ───────────────────────────────────────────────────────
        pipe_inputs = [
            use_llm, skip_provision, skip_migrate, skip_recon, skip_tests, skip_docs,
            integration_tests,
        ]
        chat_inputs = [chat_in, chatbot, *pipe_inputs]

        def _bind_op(preset: str):
            def _run(use_llm, sp, sm, sr, st, sd, it):
                yield from _stream_ops(use_llm, sp, sm, sr, st, sd, it, preset)
            return _run

        for preset, btn in [
            ("full", op_full), ("provision", op_prov), ("migrate", op_mig),
            ("recon", op_rec), ("tests", op_test), ("docs", op_docs),
        ]:
            btn.click(
                _bind_op(preset),
                inputs=pipe_inputs,
                outputs=[op_stepper, op_activity, op_summary, metrics, runs_df],
            )

        chat_send.click(_handle_chat, inputs=chat_inputs, outputs=[chatbot, chat_activity])
        chat_in.submit(_handle_chat, inputs=chat_inputs, outputs=[chatbot, chat_activity])

        refresh_dash.click(
            _refresh_dashboard,
            outputs=[metrics, runs_df, env_badges, art_list],
        )

        def _on_run_select(rid):
            meta, src, tgt = run_detail_markdown(rid)
            return meta, src, tgt

        run_select.change(_on_run_select, inputs=run_select, outputs=[run_meta, run_source, run_target])

        def _refresh_run_tab():
            data = runs_table_data()
            ids = [r[0] for r in data]
            return data, gr.update(choices=ids, value=ids[0] if ids else None)

        refresh_runs.click(_refresh_run_tab, outputs=[runs_df, run_select])

        studio_load.click(
            lambda f: load_source_sql(f),
            inputs=file_pick,
            outputs=studio_source,
        )
        studio_run.click(_transpile_file, inputs=file_pick, outputs=[studio_target, studio_status])

        art_pick.change(read_artifact_preview, inputs=art_pick, outputs=art_preview)
        art_refresh.click(
            lambda: (artifacts_markdown(), gr.update(choices=list_artifact_paths())),
            outputs=[art_list, art_pick],
        )

        demo.load(
            _refresh_dashboard,
            outputs=[metrics, runs_df, env_badges, art_list],
        )

    return demo


def main() -> None:
    init_metadata_db()
    demo = build_ui()
    base_port = int(os.getenv("GRADIO_PORT", os.getenv("GRADIO_SERVER_PORT", "7860")))
    host = os.getenv("GRADIO_HOST", "127.0.0.1")

    for offset in range(10):
        port = base_port + offset
        try:
            print(f"Migration Accelerator at http://{host}:{port}")
            demo.launch(
                server_name=host,
                server_port=port,
                inbrowser=offset == 0,
                show_error=False,
                css=CSS,
                theme=gr.themes.Base(
                    primary_hue=gr.themes.colors.blue,
                    secondary_hue=gr.themes.colors.slate,
                    neutral_hue=gr.themes.colors.slate,
                    font=gr.themes.GoogleFont("Inter"),
                ).set(
                    body_background_fill="#0f172a",
                    block_background_fill="#1e293b",
                    block_border_width="1px",
                    block_label_text_weight="600",
                    button_primary_background_fill="linear-gradient(90deg, #2563eb, #3b82f6)",
                    button_primary_background_fill_hover="linear-gradient(90deg, #1d4ed8, #2563eb)",
                ),
            )
            return
        except OSError as exc:
            if "empty port" not in str(exc).lower() or offset == 9:
                raise
            print(f"Port {port} busy, trying {port + 1}…")


if __name__ == "__main__":
    main()
