"""Run migration SQL and export query results for later reconciliation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from accelarator.gcp.client import get_bigquery_client
from accelarator.gcp.config import load_gcp_config
from accelarator.source.teradata_store import run_teradata_query

RECON_SOURCE_RESULTS_DIR = Path("reconciliation/source_results")
RECON_TARGET_RESULTS_DIR = Path("reconciliation/target_results")


@dataclass
class ExportedResult:
    run_id: int
    side: str  # source | target
    schema_name: str
    row_count: int
    column_count: int
    csv_path: str
    metadata_path: str


def _clean_sql(sql: str) -> str:
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return "\n".join(lines).strip().rstrip(";")


def _run_dir(base: Path, run_id: int) -> Path:
    path = base / str(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def execute_teradata_query(sql: str, database: str) -> pd.DataFrame:
    return run_teradata_query(_clean_sql(sql), database=database)


def execute_bigquery_query(sql: str, dataset_id: str) -> pd.DataFrame:
    from google.cloud import bigquery

    config = load_gcp_config()
    client = get_bigquery_client(config)
    query = _clean_sql(sql)
    job_config = bigquery.QueryJobConfig(
        default_dataset=f"{config.project_id}.{dataset_id}",
    )
    return client.query(query, job_config=job_config).to_dataframe()


def export_query_result(
    *,
    run_id: int,
    side: str,
    schema_name: str,
    sql: str,
    source_type: str,
    target_type: str,
) -> ExportedResult:
    """Execute SQL and write CSV + metadata JSON under reconciliation/."""
    if side == "source":
        if source_type.lower() != "teradata":
            raise ValueError(f"Unsupported source type for export: {source_type}")
        frame = execute_teradata_query(sql, schema_name)
        base_dir = RECON_SOURCE_RESULTS_DIR
    elif side == "target":
        if target_type.lower() != "bigquery":
            raise ValueError(f"Unsupported target type for export: {target_type}")
        frame = execute_bigquery_query(sql, schema_name)
        base_dir = RECON_TARGET_RESULTS_DIR
    else:
        raise ValueError(f"side must be 'source' or 'target', got {side!r}")

    run_dir = _run_dir(base_dir, run_id)
    csv_path = run_dir / "query_result.csv"
    metadata_path = run_dir / "metadata.json"

    frame.to_csv(csv_path, index=False)

    metadata = {
        "run_id": run_id,
        "side": side,
        "schema_name": schema_name,
        "row_count": len(frame),
        "column_count": len(frame.columns),
        "columns": list(frame.columns),
        "csv_path": str(csv_path),
        "exported_at": datetime.now().isoformat(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return ExportedResult(
        run_id=run_id,
        side=side,
        schema_name=schema_name,
        row_count=len(frame),
        column_count=len(frame.columns),
        csv_path=str(csv_path),
        metadata_path=str(metadata_path),
    )


def export_result_paths(run_id: int) -> tuple[str, str]:
    source_csv = RECON_SOURCE_RESULTS_DIR / str(run_id) / "query_result.csv"
    target_csv = RECON_TARGET_RESULTS_DIR / str(run_id) / "query_result.csv"
    return str(source_csv), str(target_csv)
