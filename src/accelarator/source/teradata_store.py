"""Teradata source database for migration development and reconciliation."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from accelarator.data_gen.engine import generate, read_ddl_files
from accelarator.gcp.config import INPUT_SCHEMA_DIR, SYNTHETIC_DATA_DIR
from accelarator.source.teradata_config import INPUT_DDL_DIALECT, load_teradata_config

SOURCE_TABLES = ("customers", "orders", "products")
DEFAULT_ROW_COUNTS = {"customers": 3000, "orders": 12000, "products": 100}
DEFAULT_SEED = 42
INSERT_BATCH_SIZE = 500


def get_teradata_connection(config=None):
    import teradatasql

    config = config or load_teradata_config()
    return teradatasql.connect(**config.connect_kwargs())


def _clean_ddl(ddl: str) -> str:
    return ddl.strip().rstrip(";")


def _qualified_table(database: str, table: str) -> str:
    return f"{database}.{table}"


def _drop_table(cursor, database: str, table: str) -> None:
    try:
        cursor.execute(f"DROP TABLE {_qualified_table(database, table)}")
    except Exception:
        pass


DATE_COLUMNS = frozenset({"signup_date", "order_date"})
TIMESTAMP_COLUMNS = frozenset({"created_at"})


def _normalize_frame_for_teradata(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce pandas values to Teradata-friendly literals for INSERT."""
    normalized = frame.copy()
    for col in normalized.columns:
        if col in DATE_COLUMNS:
            normalized[col] = pd.to_datetime(normalized[col], errors="coerce").dt.strftime("%Y-%m-%d")
        elif col in TIMESTAMP_COLUMNS or col.endswith("_at"):
            normalized[col] = pd.to_datetime(normalized[col], errors="coerce").dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        elif col.endswith("_id") or col in {"customer_id", "order_id", "product_id"}:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce").astype("Int64")
    return normalized


def _row_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def _insert_dataframe(cursor, database: str, table: str, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0

    frame = _normalize_frame_for_teradata(frame)
    cols = list(frame.columns)
    col_list = ", ".join(cols)
    placeholders = ", ".join(["?"] * len(cols))
    sql = (
        f"INSERT INTO {_qualified_table(database, table)} ({col_list}) "
        f"VALUES ({placeholders})"
    )

    rows: list[tuple[Any, ...]] = []
    for record in frame.itertuples(index=False, name=None):
        rows.append(tuple(_row_value(v) for v in record))

    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        batch = rows[start : start + INSERT_BATCH_SIZE]
        cursor.executemany(sql, batch)

    return len(rows)


def provision_teradata_tables(
    database: str | None = None,
    *,
    tables: tuple[str, ...] = SOURCE_TABLES,
    csv_dir: str = SYNTHETIC_DATA_DIR,
    input_dir: str = INPUT_SCHEMA_DIR,
    use_csv: bool = True,
) -> dict[str, int]:
    """Create base tables in Teradata and load synthetic CSVs (or generate in-memory)."""
    from pathlib import Path

    from accelarator.gcp.loader import csv_path_for_table

    config = load_teradata_config()
    database = database or config.database
    ddl_dict = read_ddl_files(input_dir)
    loaded: dict[str, int] = {}

    with get_teradata_connection(config) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DATABASE {database}")

        for table_stem in tables:
            ddl = ddl_dict.get(table_stem)
            if not ddl:
                raise FileNotFoundError(f"No DDL for '{table_stem}' in {input_dir}")

            _drop_table(cursor, database, table_stem)
            cursor.execute(_clean_ddl(ddl))

            if use_csv:
                csv_path = csv_path_for_table(table_stem, csv_dir)
                if not csv_path.exists():
                    raise FileNotFoundError(
                        f"CSV not found: {csv_path}. Run scripts/generate_synthetic_data.py first."
                    )
                frame = pd.read_csv(csv_path)
            else:
                n_rows = DEFAULT_ROW_COUNTS.get(table_stem, 1000)
                frame = generate(
                    ddl,
                    table_stem,
                    n_rows=n_rows,
                    dialect=INPUT_DDL_DIALECT,
                    seed=DEFAULT_SEED,
                )

            loaded[table_stem] = _insert_dataframe(cursor, database, table_stem, frame)

        conn.commit()

    return loaded


def run_teradata_query(sql: str, database: str | None = None) -> pd.DataFrame:
    """Execute SQL against Teradata and return a DataFrame."""
    config = load_teradata_config()
    database = database or config.database
    query = sql.strip().rstrip(";")

    with get_teradata_connection(config) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DATABASE {database}")
        cursor.execute(query)
        if cursor.description is None:
            return pd.DataFrame()
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=columns)


def table_name_from_teradata_ddl(ddl: str) -> str:
    match = re.search(r"CREATE\s+(?:MULTISET\s+|SET\s+)?TABLE\s+(\w+)", ddl, re.IGNORECASE)
    if not match:
        raise ValueError("Could not extract table name from Teradata DDL")
    return match.group(1)
