"""Generate synthetic CSVs from Teradata-style input_schema DDL."""

from __future__ import annotations

import sys

from accelarator.data_gen.engine import process_all_tables
from accelarator.source.teradata_config import INPUT_DDL_DIALECT

DEFAULT_ROW_COUNTS = {
    "customers": 3000,
    "orders": 12000,
    "products": 100,
}


def main() -> int:
    process_all_tables(
        tables_to_process=["customers", "orders", "products"],
        row_config=DEFAULT_ROW_COUNTS,
        dialect=INPUT_DDL_DIALECT,
        mappings_file="src/input_schema/column_mappings.yaml",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
