"""Shared LangGraph state for the migration accelerator agent pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentMessage(TypedDict, total=False):
    """One agent step in the pipeline execution log."""

    agent: str
    role: str
    status: str
    message: str
    duration_ms: float
    details: dict[str, Any]


class PipelineState(TypedDict, total=False):
    """State passed sequentially through all pipeline agents."""

    phase: str
    use_llm: bool
    skip_synthetic: bool
    skip_provision: bool
    skip_migrate: bool
    skip_recon: bool
    skip_tests: bool
    skip_docs: bool
    include_integration_tests: bool
    include_slow_tests: bool
    source_database: str
    target_database: str
    source_schema: str
    target_schema: str
    synthetic_tables_generated: int
    migration_count: int
    migration_succeeded: int
    migration_failed: int
    run_ids: list[int]
    recon_prepared: int
    recon_failed: int
    compare_passed: int
    compare_failed: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    docs_path: str
    recon_report_path: str
    regression_report_path: str
    errors: Annotated[list[str], operator.add]
    agent_log: Annotated[list[AgentMessage], operator.add]


def agent_message(
    agent: str,
    status: str,
    message: str,
    *,
    role: str = "tool",
    duration_ms: float = 0.0,
    details: dict[str, Any] | None = None,
) -> AgentMessage:
    return {
        "agent": agent,
        "role": role,
        "status": status,
        "message": message,
        "duration_ms": round(duration_ms, 1),
        "details": details or {},
    }
