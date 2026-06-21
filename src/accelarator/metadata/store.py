"""DuckDB metadata store for migration and synthetic data run history."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import duckdb

if TYPE_CHECKING:
    from accelarator.migration_assistant.io_handlers import MigrationRequest, MigrationResponse

METADATA_DIR = "metadata"
METADATA_DB_PATH = f"{METADATA_DIR}/accelerator.duckdb"

_MIGRATION_TABLE_DDL = """
CREATE SEQUENCE IF NOT EXISTS migration_runs_id_seq START 1;
CREATE TABLE IF NOT EXISTS migration_runs (
    run_id BIGINT PRIMARY KEY DEFAULT nextval('migration_runs_id_seq'),
    request_id VARCHAR NOT NULL,
    source_file VARCHAR,
    target_file VARCHAR,
    target_file_path VARCHAR,
    source_type VARCHAR NOT NULL,
    target_type VARCHAR NOT NULL,
    output_format VARCHAR,
    source_code TEXT,
    generated_code TEXT,
    status VARCHAR NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    error_type VARCHAR,
    validation_passed BOOLEAN,
    validation_feedback TEXT,
    code_length_original INTEGER,
    code_length_generated INTEGER,
    processing_time_ms DOUBLE,
    warnings TEXT,
    recon_ind VARCHAR,
    source_schema VARCHAR,
    target_schema VARCHAR,
    source_result_path VARCHAR,
    target_result_path VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_SYNTHETIC_TABLE_DDL = """
CREATE SEQUENCE IF NOT EXISTS synthetic_data_runs_id_seq START 1;
CREATE TABLE IF NOT EXISTS synthetic_data_runs (
    run_id BIGINT PRIMARY KEY DEFAULT nextval('synthetic_data_runs_id_seq'),
    table_name VARCHAR NOT NULL,
    dialect VARCHAR NOT NULL,
    input_schema_path VARCHAR,
    output_file_path VARCHAR,
    row_count INTEGER,
    column_count INTEGER,
    seed INTEGER,
    status VARCHAR NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_metadata_db(db_path: str = METADATA_DB_PATH) -> Path:
    """Create metadata folder and DuckDB tables if missing."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(path)) as conn:
        conn.execute(_MIGRATION_TABLE_DDL)
        conn.execute(_SYNTHETIC_TABLE_DDL)
        conn.execute(
            "ALTER TABLE migration_runs ADD COLUMN IF NOT EXISTS recon_ind VARCHAR"
        )
        for col in (
            "source_schema",
            "target_schema",
            "source_result_path",
            "target_result_path",
        ):
            conn.execute(f"ALTER TABLE migration_runs ADD COLUMN IF NOT EXISTS {col} VARCHAR")

    return path


def _connect(db_path: str = METADATA_DB_PATH) -> duckdb.DuckDBPyConnection:
    init_metadata_db(db_path)
    return duckdb.connect(str(db_path))


def log_migration_result(
    request: "MigrationRequest",
    response: "MigrationResponse",
    db_path: str = METADATA_DB_PATH,
) -> int:
    """Persist a migration run to DuckDB and return the run_id."""
    trans = response.transpilation
    target_file = next(iter(response.generated_files), None)
    target_path = response.generated_files.get(target_file) if target_file else None
    error_message = trans.error_message or (response.errors[0] if response.errors else None)
    error_type = trans.error_type or ("ValidationError" if not trans.validation_passed else None)

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO migration_runs (
                request_id, source_file, target_file, target_file_path,
                source_type, target_type, output_format,
                source_code, generated_code,
                status, success, error_message, error_type,
                validation_passed, validation_feedback,
                code_length_original, code_length_generated,
                processing_time_ms, warnings, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING run_id
            """,
            [
                request.request_id,
                request.source_filename,
                target_file,
                target_path,
                request.source.value,
                request.target.value,
                request.output_format.value,
                request.code,
                trans.generated_code,
                response.status.value,
                response.status.value == "success",
                error_message,
                error_type,
                trans.validation_passed,
                trans.validation_feedback,
                trans.code_length_original or len(request.code),
                trans.code_length_generated,
                response.processing_time_ms,
                json.dumps(response.warnings) if response.warnings else None,
                datetime.now(),
            ],
        ).fetchone()

    return int(row[0])


def list_migration_runs(
    *,
    pending_only: bool = False,
    db_path: str = METADATA_DB_PATH,
) -> list[dict]:
    """Return migration runs from metadata, optionally filtered to unreconciled."""
    query = """
        SELECT
            run_id, request_id, source_file, target_file,
            source_type, target_type, output_format,
            status, success, validation_passed, recon_ind,
            source_schema, target_schema,
            source_result_path, target_result_path,
            created_at
        FROM migration_runs
    """
    if pending_only:
        query += " WHERE recon_ind IS NULL"
    query += " ORDER BY run_id DESC"

    with _connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
        columns = [
            "run_id", "request_id", "source_file", "target_file",
            "source_type", "target_type", "output_format",
            "status", "success", "validation_passed", "recon_ind",
            "source_schema", "target_schema",
            "source_result_path", "target_result_path",
            "created_at",
        ]
        return [dict(zip(columns, row)) for row in rows]


def get_migration_run(run_id: int, db_path: str = METADATA_DB_PATH) -> dict | None:
    """Fetch a single migration run including SQL payloads."""
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                run_id, request_id, source_file, target_file, target_file_path,
                source_type, target_type, output_format,
                source_code, generated_code,
                status, success, validation_passed, recon_ind,
                error_message,
                source_schema, target_schema,
                source_result_path, target_result_path,
                created_at
            FROM migration_runs
            WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()
        if not row:
            return None
        columns = [
            "run_id", "request_id", "source_file", "target_file", "target_file_path",
            "source_type", "target_type", "output_format",
            "source_code", "generated_code",
            "status", "success", "validation_passed", "recon_ind",
            "error_message",
            "source_schema", "target_schema",
            "source_result_path", "target_result_path",
            "created_at",
        ]
        return dict(zip(columns, row))


def update_run_recon_metadata(
    run_id: int,
    *,
    recon_ind: str | None = None,
    source_schema: str | None = None,
    target_schema: str | None = None,
    source_result_path: str | None = None,
    target_result_path: str | None = None,
    db_path: str = METADATA_DB_PATH,
) -> None:
    """Update reconciliation fields on a migration run."""
    updates: list[str] = []
    values: list[object] = []

    field_map = {
        "recon_ind": recon_ind,
        "source_schema": source_schema,
        "target_schema": target_schema,
        "source_result_path": source_result_path,
        "target_result_path": target_result_path,
    }
    for column, value in field_map.items():
        if value is not None:
            updates.append(f"{column} = ?")
            values.append(value)

    if not updates:
        return

    values.append(run_id)
    sql = f"UPDATE migration_runs SET {', '.join(updates)} WHERE run_id = ?"

    with _connect(db_path) as conn:
        conn.execute(sql, values)


def update_recon_ind(
    run_id: int,
    recon_ind: str,
    db_path: str = METADATA_DB_PATH,
) -> None:
    """Set reconciliation indicator on a migration run (passed, failed, skipped)."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE migration_runs SET recon_ind = ? WHERE run_id = ?",
            [recon_ind, run_id],
        )


def log_synthetic_data_result(
    *,
    table_name: str,
    dialect: str,
    input_schema_path: Optional[str] = None,
    output_file_path: Optional[str] = None,
    row_count: Optional[int] = None,
    column_count: Optional[int] = None,
    seed: Optional[int] = None,
    success: bool,
    error_message: Optional[str] = None,
    db_path: str = METADATA_DB_PATH,
) -> int:
    """Persist a synthetic data generation run to DuckDB and return the run_id."""
    status = "success" if success else "failed"

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO synthetic_data_runs (
                table_name, dialect, input_schema_path, output_file_path,
                row_count, column_count, seed,
                status, success, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING run_id
            """,
            [
                table_name,
                dialect,
                input_schema_path,
                output_file_path,
                row_count,
                column_count,
                seed,
                status,
                success,
                error_message,
                datetime.now(),
            ],
        ).fetchone()

    return int(row[0])
