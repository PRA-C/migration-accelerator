"""FastAPI backend for Migration Accelerator."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from accelarator.metadata import init_metadata_db
from agents.chat_service import PipelineOptions, iter_pipeline_events, process_chat_message
from agents.chat_service import transpile_sql_adhoc, transpile_sql_file
from agents.ui_api import (
    agent_catalog,
    dashboard_metrics,
    env_status,
    get_run_detail,
    list_artifacts,
    list_runs,
    list_sql_files,
    load_sql_file,
    pipeline_steps,
    read_artifact,
)
from api.schemas import ChatRequest, PipelineOptionsModel, TranspileRequest

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

app = FastAPI(
    title="Migration Accelerator API",
    description="Teradata to BigQuery migration agent pipeline",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_metadata_db()


def _to_pipeline_options(m: PipelineOptionsModel) -> PipelineOptions:
    return PipelineOptions(
        use_llm=m.use_llm,
        skip_provision=m.skip_provision,
        skip_migrate=m.skip_migrate,
        skip_recon=m.skip_recon,
        skip_tests=m.skip_tests,
        skip_docs=m.skip_docs,
        integration_tests=m.integration_tests,
        preset=m.preset,
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "migration-accelerator"}


@app.get("/api/dashboard")
def dashboard() -> dict:
    return {
        "metrics": dashboard_metrics(),
        "env": env_status(),
        "runs": list_runs()[:20],
    }


@app.get("/api/agents")
def agents(completed: str = "", active: str = "") -> dict:
    done = [x for x in completed.split(",") if x]
    return {
        "catalog": agent_catalog(),
        "steps": pipeline_steps(completed=done, active=active),
    }


@app.get("/api/migrations")
def migrations() -> list[dict]:
    return list_runs()


@app.get("/api/migrations/{run_id}")
def migration_detail(run_id: int) -> dict:
    detail = get_run_detail(run_id)
    if not detail:
        raise HTTPException(404, f"Run {run_id} not found")
    return detail


@app.get("/api/sql/files")
def sql_files() -> list[str]:
    return list_sql_files()


@app.get("/api/sql/files/{filename}")
def sql_file_content(filename: str) -> dict:
    content = load_sql_file(filename)
    if not content and filename not in list_sql_files():
        raise HTTPException(404, f"File not found: {filename}")
    return {"filename": filename, "content": content}


@app.post("/api/sql/transpile")
def transpile(body: TranspileRequest) -> dict:
    if body.filename:
        out, status = transpile_sql_file(body.filename)
        return {"sql": out, "status": status, "filename": body.filename}
    if body.sql:
        out, status = transpile_sql_adhoc(body.sql)
        return {"sql": out, "status": status}
    raise HTTPException(400, "Provide filename or sql")


@app.get("/api/reports")
def reports() -> list[dict]:
    return list_artifacts()


@app.get("/api/reports/preview")
def report_preview(path: str = Query(...)) -> dict:
    return {"path": path, "content": read_artifact(path)}


@app.post("/api/chat")
def chat(body: ChatRequest) -> dict:
    history = [{"role": m.role, "content": m.content} for m in body.history]
    events = list(process_chat_message(body.message, history, _to_pipeline_options(body.options)))
    replies = [e for e in events if e.get("type") in ("reply", "pipeline_complete")]
    pipeline = [e for e in events if e.get("type", "").startswith("pipeline")]
    last = replies[-1] if replies else (pipeline[-1] if pipeline else {"content": ""})
    return {"events": events, "reply": last.get("content", ""), "source": last.get("source", "system")}


def _queue_get(q: queue.Queue, timeout: float):
    try:
        return q.get(timeout=timeout)
    except queue.Empty:
        return "__PING__"


@app.post("/api/pipeline/stream")
async def pipeline_stream(body: PipelineOptionsModel):
    """Stream pipeline events without blocking the asyncio event loop."""
    options = _to_pipeline_options(body)
    thread_q: queue.Queue = queue.Queue()

    def produce() -> None:
        try:
            for event in iter_pipeline_events(options):
                thread_q.put(event)
        except Exception as exc:
            thread_q.put({
                "type": "error",
                "message": str(exc),
                "completed_nodes": [],
            })
        finally:
            thread_q.put(None)

    threading.Thread(target=produce, daemon=True).start()

    async def generate():
        while True:
            item = await asyncio.to_thread(_queue_get, thread_q, 20.0)
            if item == "__PING__":
                yield {"comment": "keepalive"}
                continue
            if item is None:
                break
            yield {"event": "pipeline", "data": json.dumps(item)}

    return EventSourceResponse(generate())


# Serve built React app in production
if FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
