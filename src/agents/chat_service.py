"""Chat and pipeline orchestration for API and legacy UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterator

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

from .streaming import (
    HELP_MARKDOWN,
    format_live_status,
    migration_status_markdown,
    parse_user_intent,
    stream_pipeline,
)


@dataclass
class PipelineOptions:
    use_llm: bool = True
    skip_provision: bool = False
    skip_migrate: bool = False
    skip_recon: bool = False
    skip_tests: bool = False
    skip_docs: bool = False
    integration_tests: bool = False
    preset: str = "full"


def format_api_error(exc: Exception, *, context: str = "request") -> str:
    name = type(exc).__name__
    if "InternalServerError" in name or "500" in str(exc):
        return (
            f"**{context.title()} temporarily unavailable**\n\n"
            "Anthropic returned HTTP 500. Wait and retry, or use Operations."
        )
    if "RateLimitError" in name or "429" in str(exc):
        return f"**Rate limit during {context}** — wait a minute and retry."
    if "AuthenticationError" in name or "401" in str(exc):
        return "**Invalid API key** — check ANTHROPIC_API_KEY in .env."
    return f"**Error during {context}** ({name})."


def is_greeting(text: str) -> bool:
    t = text.strip().lower().rstrip("!.?")
    return t in {"hi", "hello", "hey", "yo"}


def greeting_reply() -> str:
    return (
        "Hello! I'm your Migration Accelerator copilot.\n\n"
        "Try: `run full pipeline`, `migrate`, `reconcile`, `status`, or ask a question."
    )


def llm_chat(message: str, history: list[dict[str, str]]) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return "Set ANTHROPIC_API_KEY in .env to use the AI assistant."
    from accelarator.llm import ask_claude

    recent = [m for m in history[-6:] if m.get("content")]
    context = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in recent)
    prompt = f"Conversation:\n{context}\n\nUser: {message}\n\nReply helpfully and concisely."
    try:
        return ask_claude(
            prompt=prompt,
            system=(
                "Migration Accelerator copilot for Teradata to BigQuery SQL migration. "
                "Answer questions about migration, reconciliation, testing, documentation."
            ),
            max_tokens=1400,
        )
    except Exception as exc:
        return format_api_error(exc, context="AI chat")


def build_pipeline_config(
    options: PipelineOptions,
    intent_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enable: dict[str, list[str]] = {
        "full": ["skip_provision", "skip_migrate", "skip_recon", "skip_tests", "skip_docs"],
        "provision": ["skip_provision"],
        "migrate": ["skip_provision", "skip_migrate"],
        "recon": ["skip_recon"],
        "tests": ["skip_tests"],
        "docs": ["skip_docs"],
    }
    config: dict[str, Any] = {
        "use_llm": options.use_llm,
        "skip_provision": True,
        "skip_migrate": True,
        "skip_recon": True,
        "skip_tests": True,
        "skip_docs": True,
        "include_integration_tests": options.integration_tests,
        "include_slow_tests": options.integration_tests,
    }
    for key in enable.get(options.preset, enable["full"]):
        config[key] = False
    if options.skip_provision:
        config["skip_provision"] = True
    if options.skip_migrate:
        config["skip_migrate"] = True
    if options.skip_recon:
        config["skip_recon"] = True
    if options.skip_tests:
        config["skip_tests"] = True
    if options.skip_docs:
        config["skip_docs"] = True
    if intent_overrides:
        config.update(intent_overrides)
    return config


def iter_pipeline_events(options: PipelineOptions) -> Iterator[dict[str, Any]]:
    """Yield JSON-serializable pipeline stream events."""
    init_metadata_db()
    config = build_pipeline_config(options)
    completed: list[str] = []

    yield {
        "type": "start",
        "preset": options.preset,
        "activity": format_live_status({"phase": "starting", "agent_log": [], "errors": []}),
        "completed_nodes": completed,
    }

    try:
        for event in stream_pipeline(**config):
            if (
                event.node_status == "complete"
                and event.active_node
                and event.active_node not in completed
            ):
                completed.append(event.active_node)
            yield {
                "type": "progress" if not event.done else "complete",
                "phase": event.phase,
                "active_node": event.active_node,
                "node_status": event.node_status,
                "completed_nodes": list(completed),
                "activity": event.status_markdown,
                "summary": event.chat_chunk,
                "done": event.done,
                "report_path": event.report_path,
            }
    except Exception as exc:
        yield {
            "type": "error",
            "message": format_api_error(exc, context=f"{options.preset} pipeline"),
            "completed_nodes": completed,
        }


def process_chat_message(
    message: str,
    history: list[dict[str, str]],
    options: PipelineOptions,
) -> Iterator[dict[str, Any]]:
    """Process one chat message; may yield multiple events for streaming pipeline."""
    if not message.strip():
        yield {"type": "reply", "content": "", "source": "system"}
        return

    if is_greeting(message):
        yield {"type": "reply", "content": greeting_reply(), "source": "local"}
        return

    action, overrides = parse_user_intent(message)

    if action == "help":
        yield {"type": "reply", "content": HELP_MARKDOWN, "source": "local"}
        return

    if action == "status":
        yield {"type": "reply", "content": migration_status_markdown(), "source": "local"}
        return

    if action == "migrate_file" and overrides:
        out, status = transpile_sql_file(overrides["filename"])
        body = status + (f"\n\n```sql\n{out[:3000]}\n```" if out else "")
        yield {"type": "reply", "content": body, "source": "transpile"}
        return

    if action == "migrate_sql" and overrides:
        out, status = transpile_sql_adhoc(overrides["sql"])
        body = status + (f"\n\n```sql\n{out[:3000]}\n```" if out else "")
        yield {"type": "reply", "content": body, "source": "transpile"}
        return

    if action == "pipeline" and overrides is not None:
        pipe_opts = PipelineOptions(
            use_llm=options.use_llm,
            skip_provision=options.skip_provision,
            skip_migrate=options.skip_migrate,
            skip_recon=options.skip_recon,
            skip_tests=options.skip_tests,
            skip_docs=options.skip_docs,
            integration_tests=options.integration_tests,
            preset=options.preset,
        )
        cfg = build_pipeline_config(pipe_opts, overrides)
        pipe_opts_dict = {**cfg}
        # Re-run with merged overrides via custom config
        init_metadata_db()
        completed: list[str] = []
        yield {"type": "pipeline_start", "content": "Pipeline starting..."}
        try:
          for event in stream_pipeline(**cfg):
              if (
                  event.node_status == "complete"
                  and event.active_node
                  and event.active_node not in completed
              ):
                  completed.append(event.active_node)
              yield {
                    "type": "pipeline_progress" if not event.done else "pipeline_complete",
                    "content": event.chat_chunk,
                    "activity": event.status_markdown,
                    "completed_nodes": list(completed),
                }
        except Exception as exc:
            yield {"type": "reply", "content": format_api_error(exc, context="pipeline"), "source": "error"}
        return

    if not options.use_llm:
        yield {
            "type": "reply",
            "content": "LLM disabled. Enable use_llm or use Operations.",
            "source": "local",
        }
        return

    reply = llm_chat(message, history)
    source = "llm" if not reply.startswith("**") else "error"
    if source == "llm":
        reply = f"Claude · migration copilot\n\n{reply}"
    yield {"type": "reply", "content": reply, "source": source}


def transpile_sql_file(filename: str) -> tuple[str, str]:
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
        return "", format_api_error(exc, context=f"transpile {filename}")
    out = resp.transpilation.generated_code or ""
    status = f"{filename} -> {resp.status.value}"
    if resp.errors:
        status += "\n" + "\n".join(f"- {e}" for e in resp.errors)
    return out, status


def transpile_sql_adhoc(sql: str) -> tuple[str, str]:
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
        return "", format_api_error(exc, context="transpile SQL")
    return resp.transpilation.generated_code or "", f"Status: {resp.status.value}"
