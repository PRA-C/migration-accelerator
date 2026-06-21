"""Create per-run source/target schemas and load synthetic data."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from accelarator.data_gen.engine import read_ddl_files
from accelarator.gcp.config import DEFAULT_MIGRATION_TABLES, INPUT_SCHEMA_DIR, SYNTHETIC_DATA_DIR, load_gcp_config
from accelarator.gcp.loader import csv_path_for_table, load_synthetic_data
from accelarator.gcp.schema import create_tables_from_schema, ensure_dataset
from accelarator.source.duckdb_store import SOURCE_DB_PATH, get_source_connection


def recon_schema_names() -> tuple[str, str]:
    """
    Shared source/target names for all reconciliation runs.

    Uses GCP_SOURCE_DATASET (DuckDB schema) and GCP_TARGET_DATASET (BigQuery dataset)
    from .env so base tables are created once, not per run_id.
    """
    config = load_gcp_config()
    return config.source_dataset, config.target_dataset


def schema_names_for_run(run_id: int) -> tuple[str, str]:
    """Deprecated alias — recon uses shared schemas; run_id is ignored."""
    del run_id
    return recon_schema_names()


def _qualify_duckdb_ddl(ddl: str, schema: str, table_stem: str) -> str:
    """Rewrite CREATE TABLE to place table inside a DuckDB schema."""
    table_name = table_stem
    return re.sub(
        rf"^CREATE TABLE\s+{table_name}\b",
        f"CREATE TABLE {schema}.{table_name}",
        ddl.strip(),
        count=1,
        flags=re.IGNORECASE,
    )


def provision_duckdb_schema(
    schema_name: str,
    *,
    db_path: str = SOURCE_DB_PATH,
    tables: tuple[str, ...] = DEFAULT_MIGRATION_TABLES,
    csv_dir: str = SYNTHETIC_DATA_DIR,
    input_dir: str = INPUT_SCHEMA_DIR,
) -> dict[str, int]:
    """Create DuckDB schema, base tables, and load synthetic CSVs."""
    ddl_dict = read_ddl_files(input_dir)
    loaded: dict[str, int] = {}

    conn = get_source_connection(db_path)
    try:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

        for table_stem in tables:
            ddl = ddl_dict.get(table_stem)
            if not ddl:
                raise FileNotFoundError(f"No DDL for '{table_stem}' in {input_dir}")

            qualified_ddl = _qualify_duckdb_ddl(ddl, schema_name, table_stem)
            conn.execute(f"DROP TABLE IF EXISTS {schema_name}.{table_stem}")
            conn.execute(qualified_ddl)

            csv_path = csv_path_for_table(table_stem, csv_dir)
            if not csv_path.exists():
                raise FileNotFoundError(
                    f"CSV not found: {csv_path}. Run scripts/generate_synthetic_data.py first."
                )

            frame = pd.read_csv(csv_path)
            conn.register("_load_df", frame)
            conn.execute(f"INSERT INTO {schema_name}.{table_stem} SELECT * FROM _load_df")
            conn.unregister("_load_df")

            count = conn.execute(f"SELECT COUNT(*) FROM {schema_name}.{table_stem}").fetchone()[0]
            loaded[table_stem] = int(count)
    finally:
        conn.close()

    return loaded


def provision_bigquery_schema(
    dataset_id: str,
    *,
    project_id: str,
    location: str,
    tables: tuple[str, ...] = DEFAULT_MIGRATION_TABLES,
    csv_dir: str = SYNTHETIC_DATA_DIR,
    input_dir: str = INPUT_SCHEMA_DIR,
) -> dict[str, int]:
    """Create BigQuery dataset, base tables, and load synthetic CSVs."""
    from accelarator.gcp.client import get_bigquery_client

    client = get_bigquery_client()
    ensure_dataset(client, project_id, dataset_id, location)
    create_tables_from_schema(
        client,
        project_id,
        dataset_id,
        input_dir=input_dir,
        tables=tables,
    )
    return load_synthetic_data(
        client,
        project_id,
        dataset_id,
        tables=tables,
        csv_dir=csv_dir,
        input_dir=input_dir,
    )


def provision_recon_schemas() -> tuple[str, str]:
    """Create shared DuckDB schema and BigQuery dataset with synthetic base tables."""
    source_schema, target_schema = recon_schema_names()
    config = load_gcp_config()

    print(f"    Provisioning DuckDB schema: {source_schema}")
    provision_duckdb_schema(source_schema)

    print(f"    Provisioning BigQuery dataset: {target_schema}")
    provision_bigquery_schema(
        target_schema,
        project_id=config.project_id,
        location=config.location,
    )
    return source_schema, target_schema
