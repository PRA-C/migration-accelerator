"""Clear migration and synthetic-data run history from metadata/accelerator.duckdb."""

from __future__ import annotations

import sys

from accelarator.metadata import METADATA_DB_PATH, clear_metadata_tables, list_migration_runs


def main() -> int:
    before = len(list_migration_runs())
    if before == 0:
        print(f"No migration runs in {METADATA_DB_PATH}.")
        return 0

    confirm = input(
        f"Delete all metadata rows ({before} migration run(s))? This cannot be undone. (yes/no): "
    ).strip().lower()
    if confirm not in ("yes", "y"):
        print("Cancelled.")
        return 0

    deleted = clear_metadata_tables()
    print(f"Cleared {METADATA_DB_PATH}:")
    for table, count in deleted.items():
        print(f"  {table}: {count} row(s) deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
