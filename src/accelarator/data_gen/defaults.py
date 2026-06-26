"""Defaults for synthetic data generation from input_schema DDL."""

from __future__ import annotations

from typing import Any

from accelarator.gcp.config import INPUT_SCHEMA_DIR, SYNTHETIC_DATA_DIR
from accelarator.source.teradata_config import INPUT_DDL_DIALECT

from .engine import process_all_tables

DEFAULT_TABLES: tuple[str, ...] = ("customers", "orders", "products")
DEFAULT_ROW_COUNTS: dict[str, int] = {
    "customers": 3000,
    "orders": 12000,
    "products": 100,
}
DEFAULT_MAPPINGS_FILE = "src/input_schema/column_mappings.yaml"
DEFAULT_SEED = 42


def generate_migration_tables(
    *,
    input_dir: str = INPUT_SCHEMA_DIR,
    output_dir: str = SYNTHETIC_DATA_DIR,
    tables: tuple[str, ...] = DEFAULT_TABLES,
    row_config: dict[str, int] | None = None,
    dialect: str = INPUT_DDL_DIALECT,
    seed: int = DEFAULT_SEED,
    mappings_file: str = DEFAULT_MAPPINGS_FILE,
) -> dict[str, Any]:
    """Read input_schema DDL and write CSVs to synthetic_data_gen."""
    return process_all_tables(
        input_dir=input_dir,
        output_dir=output_dir,
        tables_to_process=list(tables),
        row_config=row_config or dict(DEFAULT_ROW_COUNTS),
        dialect=dialect,
        seed=seed,
        mappings_file=mappings_file,
    )
