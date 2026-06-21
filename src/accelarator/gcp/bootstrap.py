"""Bootstrap BigQuery source/target datasets with schema and synthetic data."""

from __future__ import annotations

from dataclasses import dataclass

from .client import get_bigquery_client
from .config import DEFAULT_MIGRATION_TABLES, GCPConfig, INPUT_SCHEMA_DIR, SYNTHETIC_DATA_DIR, load_gcp_config
from .loader import load_synthetic_data
from .schema import create_tables_from_schema, ensure_dataset


@dataclass
class BootstrapResult:
    dataset_id: str
    tables_created: list[str]
    rows_loaded: dict[str, int]


def bootstrap_dataset(
    role: str,
    config: GCPConfig | None = None,
    tables: tuple[str, ...] | None = None,
    csv_dir: str = SYNTHETIC_DATA_DIR,
    input_dir: str = INPUT_SCHEMA_DIR,
) -> BootstrapResult:
    """
    Create schema and load synthetic CSVs into a BigQuery dataset.

    role: 'source' or 'target'
    """
    if role not in {"source", "target"}:
        raise ValueError("role must be 'source' or 'target'")

    config = config or load_gcp_config()
    tables = tables or DEFAULT_MIGRATION_TABLES
    dataset_id = config.source_dataset if role == "source" else config.target_dataset

    client = get_bigquery_client(config)
    ensure_dataset(client, config.project_id, dataset_id, config.location)
    created = create_tables_from_schema(
        client,
        config.project_id,
        dataset_id,
        input_dir=input_dir,
        tables=tables,
    )
    loaded = load_synthetic_data(
        client,
        config.project_id,
        dataset_id,
        tables=tables,
        csv_dir=csv_dir,
        input_dir=input_dir,
    )

    return BootstrapResult(
        dataset_id=dataset_id,
        tables_created=created,
        rows_loaded=loaded,
    )


def bootstrap_source_and_target(
    config: GCPConfig | None = None,
    tables: tuple[str, ...] | None = None,
    csv_dir: str = SYNTHETIC_DATA_DIR,
    input_dir: str = INPUT_SCHEMA_DIR,
) -> dict[str, BootstrapResult]:
    """Bootstrap both source and target datasets with identical schema and data."""
    return {
        "source": bootstrap_dataset(
            "source",
            config=config,
            tables=tables,
            csv_dir=csv_dir,
            input_dir=input_dir,
        ),
        "target": bootstrap_dataset(
            "target",
            config=config,
            tables=tables,
            csv_dir=csv_dir,
            input_dir=input_dir,
        ),
    }
