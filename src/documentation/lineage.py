"""Extract table references and lineage edges from SQL."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

_BASE_TABLES = frozenset({"customers", "orders", "products", "ecommerce"})


def _tables_via_regex(sql: str) -> set[str]:
    found: set[str] = set()
    patterns = (
        r"\bFROM\s+([a-zA-Z_][\w$]*)",
        r"\bJOIN\s+([a-zA-Z_][\w$]*)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            name = match.group(1).lower()
            if name not in {"select", "where", "group", "order", "inner", "left", "right", "outer"}:
                found.add(name)
    return found


def referenced_tables(sql: str, *, dialect: str = "teradata") -> list[str]:
    """Return sorted unique base table names referenced in SQL."""
    if not sql or not sql.strip():
        return []

    tables: set[str] = set()
    try:
        for statement in sqlglot.parse(sql, read=dialect):
            if statement is None:
                continue
            for table in statement.find_all(exp.Table):
                name = (table.name or "").strip().lower()
                if name:
                    tables.add(name)
    except Exception:
        tables |= _tables_via_regex(sql)

    if not tables:
        tables |= _tables_via_regex(sql)

    return sorted(tables)


def is_base_table(name: str) -> bool:
    return name.lower() in _BASE_TABLES


def lineage_edges_for_run(
    run_id: int,
    source_file: str,
    source_sql: str,
    target_sql: str,
    *,
    source_schema: str,
    target_schema: str,
) -> dict:
    """Build lineage record for one migration run."""
    src_tables = referenced_tables(source_sql, dialect="teradata")
    tgt_tables = referenced_tables(target_sql, dialect="bigquery")
    tables = sorted(set(src_tables) | set(tgt_tables))

    return {
        "run_id": run_id,
        "source_file": source_file,
        "source_schema": source_schema,
        "target_schema": target_schema,
        "input_tables": tables,
        "base_tables": [t for t in tables if is_base_table(t)],
        "edges": [
            {
                "from": f"{source_schema}.{table}",
                "to": f"migration_run_{run_id}",
                "via": source_file,
            }
            for table in tables
        ]
        + [
            {
                "from": f"migration_run_{run_id}",
                "to": f"{target_schema}.query_result",
                "via": "generated_sql",
            }
        ],
    }
