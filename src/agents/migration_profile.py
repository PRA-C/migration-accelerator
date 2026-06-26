"""Source/target migration profile — shared by UI, synthetic data, and transpiler."""

from __future__ import annotations

from accelarator.migration_assistant.io_handlers import SourceDatabase, TargetDatabase

# Values match SourceDatabase / TargetDatabase enum .value strings.
SOURCE_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "teradata", "label": "Teradata"},
    {"value": "oracle", "label": "Oracle"},
    {"value": "mssql", "label": "SQL Server"},
    {"value": "netezza", "label": "Netezza"},
    {"value": "postgres", "label": "PostgreSQL"},
    {"value": "mysql", "label": "MySQL"},
)

TARGET_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "snowflake", "label": "Snowflake"},
    {"value": "redshift", "label": "Redshift"},
    {"value": "bigquery", "label": "BigQuery"},
    {"value": "azure_synapse", "label": "Azure Synapse"},
    {"value": "spark", "label": "Spark"},
    {"value": "postgres", "label": "PostgreSQL"},
)

DEFAULT_SOURCE = "teradata"
DEFAULT_TARGET = "bigquery"

# Pairs where live provision + recon execution are implemented today.
PROVISIONED_PAIRS: frozenset[tuple[str, str]] = frozenset({("teradata", "bigquery")})

# Map migration source → DDL dialect for synthetic data generation (sqlglot).
SOURCE_TO_DDL_DIALECT: dict[str, str] = {
    "teradata": "teradata",
    "oracle": "oracle",
    "mssql": "tsql",
    "netezza": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
}

SHORT_LABELS: dict[str, str] = {
    "teradata": "TD",
    "oracle": "OR",
    "mssql": "SS",
    "netezza": "NZ",
    "postgres": "PG",
    "mysql": "MY",
    "snowflake": "SF",
    "redshift": "RS",
    "bigquery": "BQ",
    "azure_synapse": "AS",
    "spark": "SP",
}


def normalize_source(value: str | None) -> str:
    v = (value or DEFAULT_SOURCE).strip().lower()
    if any(o["value"] == v for o in SOURCE_OPTIONS):
        return v
    return DEFAULT_SOURCE


def normalize_target(value: str | None) -> str:
    v = (value or DEFAULT_TARGET).strip().lower()
    if any(o["value"] == v for o in TARGET_OPTIONS):
        return v
    return DEFAULT_TARGET


def display_name(db: str) -> str:
    for opts in (SOURCE_OPTIONS, TARGET_OPTIONS):
        for o in opts:
            if o["value"] == db:
                return o["label"]
    return db.replace("_", " ").title()


def short_label(db: str) -> str:
    return SHORT_LABELS.get(db, db[:2].upper())


def source_to_dialect(source: str) -> str:
    return SOURCE_TO_DDL_DIALECT.get(normalize_source(source), "teradata")


def supports_live_provision(source: str, target: str) -> bool:
    return (normalize_source(source), normalize_target(target)) in PROVISIONED_PAIRS


def parse_source_database(value: str) -> SourceDatabase:
    return SourceDatabase(normalize_source(value))


def parse_target_database(value: str) -> TargetDatabase:
    return TargetDatabase(normalize_target(value))


def profile_catalog() -> dict[str, list[dict[str, str]]]:
    return {
        "sources": [dict(o) for o in SOURCE_OPTIONS],
        "targets": [dict(o) for o in TARGET_OPTIONS],
        "defaults": {"source": DEFAULT_SOURCE, "target": DEFAULT_TARGET},
        "provisioned_pairs": [
            {"source": s, "target": t} for s, t in sorted(PROVISIONED_PAIRS)
        ],
    }
