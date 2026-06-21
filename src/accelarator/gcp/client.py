"""BigQuery client helpers."""

from __future__ import annotations

import os

from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError

from .config import GCPConfig, load_gcp_config


def _apply_credentials(config: GCPConfig) -> None:
    """Ensure GOOGLE_APPLICATION_CREDENTIALS is set from .env before client creation."""
    if config.credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config.credentials_path


def get_bigquery_client(config: GCPConfig | None = None) -> bigquery.Client:
    config = config or load_gcp_config()
    _apply_credentials(config)
    return bigquery.Client(project=config.project_id, location=config.location)


def test_connection(config: GCPConfig | None = None) -> dict:
    """Verify BigQuery connectivity and return project metadata."""
    config = config or load_gcp_config()
    client = get_bigquery_client(config)

    try:
        datasets = list(client.list_datasets(max_results=5))
        return {
            "project_id": config.project_id,
            "location": config.location,
            "source_dataset": config.source_dataset,
            "target_dataset": config.target_dataset,
            "dataset_count_sample": len(datasets),
            "sample_datasets": [dataset.dataset_id for dataset in datasets],
        }
    except GoogleCloudError as exc:
        raise RuntimeError(f"BigQuery connection failed: {exc}") from exc
