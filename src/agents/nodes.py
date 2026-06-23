"""LangGraph node functions — one agent per node, executed sequentially."""

from __future__ import annotations

import time
from typing import Any

from accelarator.metadata import get_migration_run, init_metadata_db, list_migration_runs
from accelarator.migration_assistant.io_handlers import (
    CodeType,
    MigrationRequest,
    OutputFormat,
    SourceDatabase,
    TargetDatabase,
    read_source_migration_files,
)
from accelarator.migration_assistant.transpiler import transpile_request

from .state import PipelineState, agent_message


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _all_run_ids() -> list[int]:
    return [int(r["run_id"]) for r in list_migration_runs()]


def environment_provisioner(state: PipelineState) -> dict[str, Any]:
    """Agent 1: provision Teradata + BigQuery schemas."""
    t0 = time.perf_counter()
    if state.get("skip_provision"):
        return {
            "phase": "intake",
            "agent_log": [
                agent_message(
                    "EnvironmentProvisioner",
                    "skipped",
                    "Skipped (--skip-provision)",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }

    try:
        from reconciliation.schema_provisioner import provision_recon_schemas

        source_schema, target_schema = provision_recon_schemas()
        return {
            "phase": "intake",
            "source_schema": source_schema,
            "target_schema": target_schema,
            "agent_log": [
                agent_message(
                    "EnvironmentProvisioner",
                    "success",
                    f"Provisioned Teradata `{source_schema}` and BigQuery `{target_schema}`",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }
    except Exception as exc:
        return {
            "phase": "intake",
            "errors": [f"EnvironmentProvisioner: {exc}"],
            "agent_log": [
                agent_message(
                    "EnvironmentProvisioner",
                    "failed",
                    str(exc),
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }


def migration_intake(state: PipelineState) -> dict[str, Any]:
    """Agent 2: load source migration SQL files."""
    t0 = time.perf_counter()
    if state.get("skip_migrate"):
        run_ids = _all_run_ids()
        return {
            "phase": "recon",
            "run_ids": run_ids,
            "agent_log": [
                agent_message(
                    "MigrationIntake",
                    "skipped",
                    f"Migration skipped; using {len(run_ids)} existing run(s) from metadata",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }

    files = read_source_migration_files()
    if not files:
        return {
            "phase": "recon",
            "migration_count": 0,
            "migration_succeeded": 0,
            "migration_failed": 0,
            "run_ids": _all_run_ids(),
            "errors": ["MigrationIntake: no source SQL files found"],
            "agent_log": [
                agent_message(
                    "MigrationIntake",
                    "failed",
                    "No files in src/source_files_for_migration/",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }

    return {
        "phase": "migrate",
        "migration_count": len(files),
        "agent_log": [
            agent_message(
                "MigrationIntake",
                "success",
                f"Loaded {len(files)} migration file(s): {', '.join(sorted(files))}",
                duration_ms=_elapsed_ms(t0),
                details={"files": sorted(files)},
            )
        ],
    }


def migration_transpiler(state: PipelineState) -> dict[str, Any]:
    """Agent 3: LLM transpilation loop (Data Engineer + Data Manager)."""
    t0 = time.perf_counter()
    if state.get("skip_migrate"):
        return {"agent_log": []}

    init_metadata_db()
    files = read_source_migration_files()
    succeeded = 0
    failed = 0
    run_ids: list[int] = []
    file_results: list[dict[str, Any]] = []

    for filename, code in sorted(files.items()):
        request = MigrationRequest(
            source=SourceDatabase.TERADATA,
            target=TargetDatabase.BIGQUERY,
            output_format=OutputFormat.TARGET_SQL_ONLY,
            code=code,
            code_type=CodeType.SQL_QUERY,
            source_filename=filename,
        )
        response = transpile_request(request)
        ok = response.status.value == "success"
        if ok:
            succeeded += 1
        else:
            failed += 1
        runs = [r for r in list_migration_runs() if r.get("request_id") == request.request_id]
        run_id = int(runs[-1]["run_id"]) if runs else None
        if run_id is not None:
            run_ids.append(run_id)
        err = (
            response.transpilation.error_message
            or (response.errors[0] if response.errors else None)
        )
        file_results.append(
            {
                "file": filename,
                "success": ok,
                "run_id": run_id,
                "error": err,
            }
        )

    status = "success" if failed == 0 else ("partial" if succeeded else "failed")
    errors = [f"MigrationTranspiler: {r['file']} — {r['error']}" for r in file_results if not r["success"]]

    return {
        "phase": "recon",
        "migration_succeeded": succeeded,
        "migration_failed": failed,
        "run_ids": run_ids or _all_run_ids(),
        "errors": errors,
        "agent_log": [
            agent_message(
                "MigrationTranspiler",
                status,
                f"Transpiled {succeeded}/{len(files)} migration(s) (LLM: Data Engineer + Data Manager)",
                role="llm",
                duration_ms=_elapsed_ms(t0),
                details={"results": file_results},
            )
        ],
    }


def recon_preparer(state: PipelineState) -> dict[str, Any]:
    """Agent 4: execute SQL and export reconciliation CSVs."""
    t0 = time.perf_counter()
    if state.get("skip_recon"):
        return {
            "phase": "compare",
            "agent_log": [
                agent_message(
                    "ReconPreparer",
                    "skipped",
                    "Skipped (--skip-recon)",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }

    from reconciliation.recon_executor import prepare_migration_run

    run_ids = state.get("run_ids") or _all_run_ids()
    prepared = 0
    failed = 0
    prep_results: list[dict[str, Any]] = []

    for run_id in run_ids:
        run = get_migration_run(run_id)
        if not run:
            failed += 1
            prep_results.append({"run_id": run_id, "status": "missing"})
            continue
        result = prepare_migration_run(run, provision=False)
        if result.recon_ind == "prepared":
            prepared += 1
        else:
            failed += 1
        prep_results.append(
            {
                "run_id": run_id,
                "status": result.recon_ind,
                "source_rows": result.source_rows,
                "target_rows": result.target_rows,
                "message": result.message[:200] if result.message else "",
            }
        )

    status = "success" if failed == 0 else ("partial" if prepared else "failed")
    return {
        "phase": "compare",
        "recon_prepared": prepared,
        "recon_failed": failed,
        "agent_log": [
            agent_message(
                "ReconPreparer",
                status,
                f"Prepared {prepared}/{len(run_ids)} run(s) for reconciliation",
                duration_ms=_elapsed_ms(t0),
                details={"runs": prep_results},
            )
        ],
    }


def recon_comparator(state: PipelineState) -> dict[str, Any]:
    """Agent 5: compare CSVs (ReconAnalyst report is generated inside compare_runs)."""
    t0 = time.perf_counter()
    if state.get("skip_recon"):
        return {"agent_log": []}

    from reconciliation.compare_results import compare_runs

    run_ids = state.get("run_ids") or _all_run_ids()
    if not run_ids:
        return {
            "errors": ["ReconComparator: no migration runs in metadata"],
            "agent_log": [
                agent_message(
                    "ReconComparator",
                    "failed",
                    "No runs to compare",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }

    use_llm = state.get("use_llm", True)
    results = compare_runs(run_ids, use_llm=use_llm, write_json=True)
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    report_path = results[0].report_path if results else ""

    compare_status = "success" if failed == 0 else "partial"
    return {
        "phase": "test",
        "compare_passed": passed,
        "compare_failed": failed,
        "recon_report_path": report_path,
        "agent_log": [
            agent_message(
                "ReconComparator",
                compare_status,
                f"Compared {len(results)} run(s): {passed} passed, {failed} failed",
                duration_ms=_elapsed_ms(t0),
                details={"report": report_path},
            ),
            agent_message(
                "ReconAnalyst",
                "success" if use_llm else "skipped",
                (
                    f"Reconciliation report written to {report_path}"
                    + (" (with LLM analysis)" if use_llm else " (rule-based only)")
                ),
                role="llm",
                duration_ms=0.0,
            ),
        ],
    }


def regression_runner(state: PipelineState) -> dict[str, Any]:
    """Agent 6: run regression test suite."""
    t0 = time.perf_counter()
    if state.get("skip_tests"):
        return {
            "phase": "document",
            "agent_log": [
                agent_message(
                    "RegressionRunner",
                    "skipped",
                    "Skipped (--skip-tests)",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }

    from test_generator.report import generate_regression_report
    from test_generator.runner import run_regression_suite

    include_integration = state.get("include_integration_tests", False)
    include_slow = state.get("include_slow_tests", False) or include_integration
    use_llm = state.get("use_llm", True)

    suite = run_regression_suite(
        include_integration=include_integration,
        include_slow=include_slow,
    )
    report_path = generate_regression_report(suite, use_llm=use_llm)

    test_status = "success" if suite.failed == 0 else "partial"
    return {
        "phase": "document",
        "tests_passed": suite.passed,
        "tests_failed": suite.failed,
        "tests_skipped": suite.skipped,
        "regression_report_path": str(report_path),
        "agent_log": [
            agent_message(
                "RegressionRunner",
                test_status,
                f"Tests: {suite.passed} passed, {suite.failed} failed, {suite.skipped} skipped",
                duration_ms=_elapsed_ms(t0),
            ),
            agent_message(
                "QAAnalyst",
                "success" if use_llm and suite.failed else "skipped",
                (
                    f"Regression report → {report_path}"
                    + (" (with LLM failure analysis)" if use_llm and suite.failed else "")
                ),
                role="llm",
                duration_ms=0.0,
            ),
        ],
    }


def documentation_generator(state: PipelineState) -> dict[str, Any]:
    """Agent 7: generate migration docs and lineage."""
    t0 = time.perf_counter()
    if state.get("skip_docs"):
        return {
            "phase": "done",
            "agent_log": [
                agent_message(
                    "DocumentationGenerator",
                    "skipped",
                    "Skipped (--skip-docs)",
                    duration_ms=_elapsed_ms(t0),
                )
            ],
        }

    from documentation.generator import generate_documentation

    use_llm = state.get("use_llm", True)
    docs_root = generate_documentation(use_llm=use_llm)

    return {
        "phase": "done",
        "docs_path": str(docs_root),
        "agent_log": [
            agent_message(
                "DocumentationGenerator",
                "success",
                f"Documentation written to {docs_root}/",
                duration_ms=_elapsed_ms(t0),
            ),
            agent_message(
                "DocWriter",
                "success" if use_llm else "skipped",
                (
                    f"Executive summary in {docs_root}/migration_overview.md"
                    if use_llm
                    else "LLM executive summary skipped (--no-llm)"
                ),
                role="llm",
                duration_ms=0.0,
            ),
        ],
    }
