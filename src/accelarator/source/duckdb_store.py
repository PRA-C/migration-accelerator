"""Local DuckDB source database for migration development and query validation."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from accelarator.data_gen.engine import generate, read_ddl_files

load_dotenv()

SOURCE_DATA_DIR = "data"
SOURCE_DB_PATH = os.getenv("DUCKDB_SOURCE_PATH", f"{SOURCE_DATA_DIR}/source.duckdb")
INPUT_SCHEMA_DIR = "src/input_schema"
SOURCE_TABLES = ("customers", "orders", "products")
DEFAULT_ROW_COUNTS = {"customers": 500, "orders": 2000, "products": 100}
DEFAULT_SEED = 42


def get_source_connection(db_path: str = SOURCE_DB_PATH) -> duckdb.DuckDBPyConnection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(db_path)


def init_source_db(
    db_path: str = SOURCE_DB_PATH,
    input_dir: str = INPUT_SCHEMA_DIR,
    row_counts: dict[str, int] | None = None,
    seed: int = DEFAULT_SEED,
    force: bool = False,
) -> str:
    """Create or refresh the DuckDB source database with schema and synthetic data."""
    row_counts = row_counts or DEFAULT_ROW_COUNTS
    ddl_dict = read_ddl_files(input_dir)
    ddl_dict = {name: ddl for name, ddl in ddl_dict.items() if name in SOURCE_TABLES}

    if not ddl_dict:
        raise RuntimeError(f"No DDL found for source tables in {input_dir}")

    if force and Path(db_path).exists():
        Path(db_path).unlink()

    conn = get_source_connection(db_path)
    try:
        for table_name, ddl in ddl_dict.items():
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.execute(ddl)

            n_rows = row_counts.get(table_name, 1000)
            df = generate(
                ddl,
                table_name,
                n_rows=n_rows,
                dialect="duckdb",
                seed=seed,
            )
            if df.empty:
                raise RuntimeError(f"No synthetic rows generated for {table_name}")

            conn.register("_load_df", df)
            conn.execute(f"INSERT INTO {table_name} SELECT * FROM _load_df")
            conn.unregister("_load_df")
    finally:
        conn.close()

    return db_path


def run_source_query(
    sql: str,
    db_path: str = SOURCE_DB_PATH,
    limit: int | None = None,
) -> list[tuple]:
    """Execute SQL against the source DuckDB and return fetched rows."""
    query = sql.strip().rstrip(";")
    if limit is not None:
        query = f"SELECT * FROM ({query}) AS _q LIMIT {limit}"

    conn = get_source_connection(db_path)
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()
