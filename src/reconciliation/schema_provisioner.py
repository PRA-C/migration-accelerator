"""Create shared source/target schemas and load synthetic data."""

from __future__ import annotations

from accelarator.gcp.config import DEFAULT_MIGRATION_TABLES, INPUT_SCHEMA_DIR, SYNTHETIC_DATA_DIR, load_gcp_config
from accelarator.gcp.loader import load_synthetic_data
from accelarator.gcp.schema import create_tables_from_schema, ensure_dataset
from accelarator.source.teradata_config import load_teradata_config
from accelarator.source.teradata_store import provision_teradata_tables


def recon_schema_names() -> tuple[str, str]:
    """
    Shared source/target names for all reconciliation runs.

    Teradata database (TD_DATABASE) and BigQuery dataset (GCP_TARGET_DATASET).
    """
    td_config = load_teradata_config()
    gcp_config = load_gcp_config()
    return td_config.database, gcp_config.target_dataset


def schema_names_for_run(run_id: int) -> tuple[str, str]:
    """Deprecated alias — recon uses shared schemas; run_id is ignored."""
    del run_id
    return recon_schema_names()


def provision_teradata_schema(
    database: str,
    *,
    tables: tuple[str, ...] = DEFAULT_MIGRATION_TABLES,
    csv_dir: str = SYNTHETIC_DATA_DIR,
) -> dict[str, int]:
    """Create Teradata base tables and load synthetic CSVs."""
    return provision_teradata_tables(
        database,
        tables=tables,
        csv_dir=csv_dir,
        use_csv=True,
    )


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
    """Create shared Teradata database tables and BigQuery dataset with synthetic base tables."""
    source_database, target_schema = recon_schema_names()
    config = load_gcp_config()

    print(f"    Provisioning Teradata database: {source_database}")
    provision_teradata_schema(source_database)

    print(f"    Provisioning BigQuery dataset: {target_schema}")
    provision_bigquery_schema(
        target_schema,
        project_id=config.project_id,
        location=config.location,
    )
    return source_database, target_schema
