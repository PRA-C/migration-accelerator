"""Reconcile row counts between BigQuery source and target datasets."""

from __future__ import annotations

from dataclasses import dataclass

from google.cloud import bigquery

from .client import get_bigquery_client
from .config import DEFAULT_MIGRATION_TABLES, GCPConfig, load_gcp_config
from .schema import table_name_from_ddl
from accelarator.data_gen.engine import read_ddl_files


@dataclass
class ReconcileRow:
    table_stem: str
    table_name: str
    source_rows: int
    target_rows: int

    @property
    def matched(self) -> bool:
        return self.source_rows == self.target_rows


def _count_rows(client: bigquery.Client, project_id: str, dataset_id: str, table_name: str) -> int:
    query = f"SELECT COUNT(*) AS row_count FROM `{project_id}.{dataset_id}.{table_name}`"
    result = client.query(query).result()
    return next(result).row_count


def reconcile_datasets(
    config: GCPConfig | None = None,
    tables: tuple[str, ...] | None = None,
    input_dir: str = "src/input_schema",
) -> list[ReconcileRow]:
    """Compare base-table row counts between source and target datasets."""
    config = config or load_gcp_config()
    tables = tables or DEFAULT_MIGRATION_TABLES
    ddl_dict = read_ddl_files(input_dir)
    client = get_bigquery_client(config)

    rows: list[ReconcileRow] = []
    for stem in tables:
        ddl = ddl_dict.get(stem)
        if not ddl:
            raise FileNotFoundError(f"No DDL found for '{stem}'")

        table_name = table_name_from_ddl(ddl)
        source_rows = _count_rows(client, config.project_id, config.source_dataset, table_name)
        target_rows = _count_rows(client, config.project_id, config.target_dataset, table_name)
        rows.append(
            ReconcileRow(
                table_stem=stem,
                table_name=table_name,
                source_rows=source_rows,
                target_rows=target_rows,
            )
        )

    return rows
