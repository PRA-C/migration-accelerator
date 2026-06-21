"""Transpile input DDL to BigQuery and create tables."""

from __future__ import annotations

import re

import sqlglot
from google.cloud import bigquery
from sqlglot import exp

from accelarator.data_gen.engine import read_ddl_files

from .config import DEFAULT_MIGRATION_TABLES, INPUT_SCHEMA_DIR


def table_name_from_ddl(ddl: str) -> str:
    parsed = sqlglot.parse_one(ddl, read="duckdb")
    table = parsed.find(exp.Table)
    if not table or not table.name:
        raise ValueError("Could not extract table name from DDL")
    return table.name


def ddl_to_bigquery_create(
    ddl: str,
    project_id: str,
    dataset_id: str,
) -> str:
    """Convert DuckDB-style input DDL to a qualified BigQuery CREATE OR REPLACE TABLE."""
    table_name = table_name_from_ddl(ddl)
    bq_ddl = sqlglot.transpile(ddl, read="duckdb", write="bigquery")[0]
    qualified = f"`{project_id}.{dataset_id}.{table_name}`"
    return re.sub(
        r"^CREATE TABLE\s+\w+",
        f"CREATE OR REPLACE TABLE {qualified}",
        bq_ddl,
        count=1,
    )


def ensure_dataset(client: bigquery.Client, project_id: str, dataset_id: str, location: str) -> None:
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    dataset_ref.location = location
    client.create_dataset(dataset_ref, exists_ok=True)


def create_tables_from_schema(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    input_dir: str = INPUT_SCHEMA_DIR,
    tables: tuple[str, ...] | None = None,
) -> list[str]:
    """Create BigQuery tables from input_schema DDL files."""
    tables = tables or DEFAULT_MIGRATION_TABLES
    ddl_dict = read_ddl_files(input_dir)
    created: list[str] = []

    for stem in tables:
        ddl = ddl_dict.get(stem)
        if not ddl:
            raise FileNotFoundError(f"No DDL found for table '{stem}' in {input_dir}")

        create_sql = ddl_to_bigquery_create(ddl, project_id, dataset_id)
        client.query(create_sql).result()
        created.append(table_name_from_ddl(ddl))

    return created
