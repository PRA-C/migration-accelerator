"""Load synthetic CSV files into BigQuery tables."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from .config import DEFAULT_MIGRATION_TABLES, SYNTHETIC_DATA_DIR
from .schema import table_name_from_ddl
from accelarator.data_gen.engine import read_ddl_files


def csv_path_for_table(table_stem: str, csv_dir: str = SYNTHETIC_DATA_DIR) -> Path:
    return Path(csv_dir) / f"{table_stem}.csv"


def _normalize_frame_for_schema(frame: pd.DataFrame, schema: list) -> pd.DataFrame:
    """Coerce pandas columns to match BigQuery table schema before CSV load."""
    normalized = frame.copy()
    for field in schema:
        col = field.name
        if col not in normalized.columns:
            continue
        if field.field_type in ("INTEGER", "INT64"):
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce").astype("Int64")
        elif field.field_type == "DATE":
            normalized[col] = pd.to_datetime(normalized[col], errors="coerce").dt.strftime("%Y-%m-%d")
        elif field.field_type in ("DATETIME", "TIMESTAMP"):
            normalized[col] = pd.to_datetime(normalized[col], errors="coerce").dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        elif field.field_type in ("NUMERIC", "BIGNUMERIC"):
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce").map(
                lambda v: f"{v:.2f}" if pd.notna(v) else ""
            )
    return normalized


def load_csv_to_table(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    table_stem: str,
    csv_dir: str = SYNTHETIC_DATA_DIR,
    input_dir: str = "src/input_schema",
) -> int:
    """Load a synthetic CSV into the matching BigQuery table. Returns row count loaded."""
    csv_path = csv_path_for_table(table_stem, csv_dir)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV not found: {csv_path}. Run scripts/generate_synthetic_data.py first."
        )

    ddl_dict = read_ddl_files(input_dir)
    ddl = ddl_dict.get(table_stem)
    if not ddl:
        raise FileNotFoundError(f"No DDL found for '{table_stem}'")

    table_name = table_name_from_ddl(ddl)
    table_ref = f"{project_id}.{dataset_id}.{table_name}"

    table = client.get_table(table_ref)
    frame = _normalize_frame_for_schema(pd.read_csv(csv_path), table.schema)

    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    buffer.seek(0)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=table.schema,
        allow_quoted_newlines=True,
    )

    job = client.load_table_from_file(
        io.BytesIO(buffer.getvalue().encode("utf-8")),
        table_ref,
        job_config=job_config,
    )
    job.result()
    table = client.get_table(table_ref)
    return table.num_rows


def load_synthetic_data(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    tables: tuple[str, ...] | None = None,
    csv_dir: str = SYNTHETIC_DATA_DIR,
    input_dir: str = "src/input_schema",
) -> dict[str, int]:
    """Load all synthetic CSVs for the given table stems."""
    tables = tables or DEFAULT_MIGRATION_TABLES
    loaded: dict[str, int] = {}

    for table_stem in tables:
        row_count = load_csv_to_table(
            client,
            project_id,
            dataset_id,
            table_stem,
            csv_dir=csv_dir,
            input_dir=input_dir,
        )
        loaded[table_stem] = row_count

    return loaded
