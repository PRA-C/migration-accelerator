"""Google Cloud / BigQuery configuration from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

INPUT_SCHEMA_DIR = os.getenv("INPUT_SCHEMA_DIR", "src/input_schema")
SYNTHETIC_DATA_DIR = os.getenv("SYNTHETIC_DATA_DIR", "src/synthetic_data_gen")
DEFAULT_MIGRATION_TABLES = ("customers", "orders", "products")


@dataclass(frozen=True)
class GCPConfig:
    project_id: str
    location: str
    source_dataset: str
    target_dataset: str
    credentials_path: str | None = None

    @property
    def source_ref(self) -> str:
        return f"{self.project_id}.{self.source_dataset}"

    @property
    def target_ref(self) -> str:
        return f"{self.project_id}.{self.target_dataset}"


def load_gcp_config() -> GCPConfig:
    project_id = os.getenv("GCP_PROJECT_ID", "").strip()
    if not project_id:
        raise ValueError(
            "GCP_PROJECT_ID is required. Set it in .env (see .env.example)."
        )

    return GCPConfig(
        project_id=project_id,
        location=os.getenv("GCP_LOCATION", "US").strip(),
        source_dataset=os.getenv("GCP_SOURCE_DATASET", "migration_source").strip(),
        target_dataset=os.getenv("GCP_TARGET_DATASET", "migration_target").strip(),
        credentials_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip() or None,
    )
