"""Generate synthetic CSVs from Teradata-style input_schema DDL."""

from __future__ import annotations

import sys

from accelarator.data_gen.defaults import generate_migration_tables


def main() -> int:
    results = generate_migration_tables()
    if not results:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
