"""Prepare migration runs for reconciliation: schemas, data, query results."""

from __future__ import annotations

from dataclasses import dataclass

from accelarator.metadata.store import update_run_recon_metadata

from .result_exporter import export_query_result, export_result_paths
from .schema_provisioner import provision_recon_schemas, recon_schema_names


@dataclass
class PrepareResult:
    run_id: int
    passed: bool
    source_schema: str
    target_schema: str
    source_rows: int | None
    target_rows: int | None
    source_result_path: str | None
    target_result_path: str | None
    message: str
    recon_ind: str  # prepared | failed | skipped


def prepare_migration_run(run: dict, *, provision: bool = True) -> PrepareResult:
    """
    For one migration run:
    1. Use shared source/target schema names (GCP_SOURCE_DATASET / GCP_TARGET_DATASET)
    2. Optionally create tables and load synthetic data (once per batch if provision=False)
    3. Execute source & target SQL
    4. Export results to reconciliation/ folders
    """
    run_id = int(run["run_id"])
    source_schema, target_schema = recon_schema_names()

    # Do not skip solely on success=false — SQL may still be runnable for recon export
    source_code = run.get("source_code") or ""
    generated_code = run.get("generated_code") or ""
    if not source_code.strip() or not generated_code.strip():
        return PrepareResult(
            run_id=run_id,
            passed=False,
            source_schema=source_schema,
            target_schema=target_schema,
            source_rows=None,
            target_rows=None,
            source_result_path=None,
            target_result_path=None,
            message="Missing source or generated SQL — skipped",
            recon_ind="skipped",
        )

    source_type = (run.get("source_type") or "").lower()
    target_type = (run.get("target_type") or "").lower()

    if source_type != "duckdb" or target_type != "bigquery":
        return PrepareResult(
            run_id=run_id,
            passed=False,
            source_schema=source_schema,
            target_schema=target_schema,
            source_rows=None,
            target_rows=None,
            source_result_path=None,
            target_result_path=None,
            message=f"Unsupported pair {source_type} → {target_type} (need duckdb → bigquery)",
            recon_ind="skipped",
        )

    try:
        if provision:
            provision_recon_schemas()

        print("    Running source query and exporting results...")
        source_export = export_query_result(
            run_id=run_id,
            side="source",
            schema_name=source_schema,
            sql=source_code,
            source_type=source_type,
            target_type=target_type,
        )

        print("    Running target query and exporting results...")
        target_export = export_query_result(
            run_id=run_id,
            side="target",
            schema_name=target_schema,
            sql=generated_code,
            source_type=source_type,
            target_type=target_type,
        )

        update_run_recon_metadata(
            run_id,
            recon_ind="prepared",
            source_schema=source_schema,
            target_schema=target_schema,
            source_result_path=source_export.csv_path,
            target_result_path=target_export.csv_path,
        )

        row_match = source_export.row_count == target_export.row_count
        return PrepareResult(
            run_id=run_id,
            passed=row_match,
            source_schema=source_schema,
            target_schema=target_schema,
            source_rows=source_export.row_count,
            target_rows=target_export.row_count,
            source_result_path=source_export.csv_path,
            target_result_path=target_export.csv_path,
            message=(
                f"Results exported. Row counts: source={source_export.row_count}, "
                f"target={target_export.row_count}"
            ),
            recon_ind="prepared",
        )

    except Exception as exc:
        update_run_recon_metadata(
            run_id,
            recon_ind="failed",
            source_schema=source_schema,
            target_schema=target_schema,
        )
        return PrepareResult(
            run_id=run_id,
            passed=False,
            source_schema=source_schema,
            target_schema=target_schema,
            source_rows=None,
            target_rows=None,
            source_result_path=export_result_paths(run_id)[0],
            target_result_path=export_result_paths(run_id)[1],
            message=f"Preparation failed: {exc}",
            recon_ind="failed",
        )
