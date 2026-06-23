"""Provision Teradata base tables and load synthetic CSVs."""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

from accelarator.source.teradata_config import load_teradata_config
from accelarator.source.teradata_store import provision_teradata_tables


def main() -> int:
    config = load_teradata_config()
    print(f"Provisioning Teradata database: {config.database}")
    loaded = provision_teradata_tables(config.database)
    for table, count in loaded.items():
        print(f"  {table}: {count} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
