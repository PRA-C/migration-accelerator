"""Test Teradata connectivity (ClearScape / trial cloud)."""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

from accelarator.source.teradata_config import load_teradata_config
from accelarator.source.teradata_store import get_teradata_connection


def main() -> int:
    try:
        import teradatasql  # noqa: F401
    except ImportError:
        print("teradatasql is not installed. Run: uv sync")
        return 1

    config = load_teradata_config()
    print(f"Connecting to Teradata at {config.host}:{config.port} ...")

    try:
        with get_teradata_connection(config) as conn:
            cur = conn.cursor()
            cur.execute("SELECT CURRENT_TIMESTAMP, USER, DATABASE")
            row = cur.fetchone()
            print("Connection successful.")
            print(f"  Timestamp : {row[0]}")
            print(f"  User      : {row[1]}")
            print(f"  Database  : {row[2]}")
            return 0
    except Exception as exc:
        print(f"Connection failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
