"""Build the full regression test registry."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from accelarator.gcp.loader import _normalize_frame_for_schema
from accelarator.gcp.schema import _sanitize_bigquery_ddl, ddl_to_bigquery_create, table_name_from_ddl
from accelarator.source.teradata_config import load_teradata_config
from reconciliation.compare_results import compare_dataframes
from reconciliation.recon_report import _rule_based_analysis

from .suite import TestCase, _require, note_pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MIGRATION_DIR = PROJECT_ROOT / "src" / "source_files_for_migration"
INPUT_SCHEMA_DIR = PROJECT_ROOT / "src" / "input_schema"
RECON_SOURCE = PROJECT_ROOT / "reconciliation" / "source_results"
RECON_TARGET = PROJECT_ROOT / "reconciliation" / "target_results"

EXPECTED_MIGRATION_SQL = (
    "customer_order_lifetime.sql",
    "customer_product_spend.sql",
    "inactive_high_value_customers.sql",
    "product_revenue_contribution.sql",
    "regional_monthly_sales.sql",
    "signup_cohort_retention.sql",
)

EXPECTED_INPUT_TABLES = ("customers.sql", "orders.sql", "products.sql")


def _test_schema_sanitize_datetime() -> None:
    raw = "CREATE TABLE t (created_at DATETIME(0), ts TIMESTAMP(6))"
    cleaned = _sanitize_bigquery_ddl(raw)
    _require("DATETIME(0)" not in cleaned, "DATETIME precision should be stripped")
    _require("TIMESTAMP(6)" not in cleaned, "TIMESTAMP precision should be stripped")
    _require("DATETIME" in cleaned and "TIMESTAMP" in cleaned, "Base types should remain")
    note_pass("Input contained DATETIME(0) and TIMESTAMP(6); output uses plain DATETIME and TIMESTAMP.")


def _test_ddl_to_bigquery_customers() -> None:
    ddl = (INPUT_SCHEMA_DIR / "customers.sql").read_text(encoding="utf-8")
    sql = ddl_to_bigquery_create(ddl, "proj", "dataset")
    _require("CREATE OR REPLACE TABLE `proj.dataset.customers`" in sql, "Qualified table name expected")
    _require("DATETIME(0)" not in sql, "BQ DDL should not contain DATETIME(0)")


def _test_table_name_from_ddl() -> None:
    ddl = (INPUT_SCHEMA_DIR / "orders.sql").read_text(encoding="utf-8")
    _require(table_name_from_ddl(ddl) == "orders", "Table name should be orders")


def _test_loader_truncates_strings() -> None:
    frame = pd.DataFrame({"phone": ["123456789012345678901", "short"]})
    schema = [bigquery.SchemaField("phone", "STRING", mode="NULLABLE", max_length=20)]
    out = _normalize_frame_for_schema(frame, schema)
    _require(out["phone"].iloc[0] == "12345678901234567890", "Phone should truncate to 20 chars")
    _require(out["phone"].iloc[1] == "short", "Short values should be unchanged")


def _test_compare_identical_frames() -> None:
    df = pd.DataFrame({"id": [1, 2], "amount": [10.0, 20.0]})
    result = compare_dataframes(df, df.copy())
    _require(result.passed, f"Identical frames should pass: {result.message}")


def _test_compare_row_count_mismatch() -> None:
    src = pd.DataFrame({"id": [1, 2]})
    tgt = pd.DataFrame({"id": [1]})
    result = compare_dataframes(src, tgt)
    _require(not result.passed, "Row count mismatch should fail")
    _require(not result.row_counts_match, "row_counts_match should be false")


def _test_compare_numeric_tolerance() -> None:
    src = pd.DataFrame({"id": [1], "value": [1.0000001]})
    tgt = pd.DataFrame({"id": [1], "value": [1.0000002]})
    result = compare_dataframes(src, tgt, rtol=1e-4, atol=1e-4)
    _require(result.passed, f"Values within tolerance should pass: {result.message}")


def _test_compare_numeric_failure() -> None:
    src = pd.DataFrame({"id": [1], "value": [100.0]})
    tgt = pd.DataFrame({"id": [1], "value": [200.0]})
    result = compare_dataframes(src, tgt)
    _require(not result.passed, "Large numeric delta should fail")


def _test_compare_order_id_keyed_match() -> None:
    src = pd.DataFrame(
        {"order_id": [10, 20], "product_id": [1, 2], "amount": [50.0, 75.0]}
    )
    tgt = pd.DataFrame(
        {"order_id": [20, 10], "product_id": [2, 1], "amount": [75.0, 50.0]}
    )
    result = compare_dataframes(src, tgt)
    _require(result.passed, f"Order-id keyed rows should match: {result.message}")


def _test_compare_schema_mismatch() -> None:
    src = pd.DataFrame({"a": [1]})
    tgt = pd.DataFrame({"b": [1]})
    result = compare_dataframes(src, tgt)
    _require(not result.passed, "Schema mismatch should fail")
    _require(not result.columns_match, "columns_match should be false")


def _test_rule_analysis_passed() -> None:
    from reconciliation.compare_results import CompareResult

    result = CompareResult(
        run_id=1,
        source_file="demo.sql",
        passed=True,
        source_rows=10,
        target_rows=10,
        columns_match=True,
        row_counts_match=True,
        source_csv="",
        target_csv="",
        report_path="",
        message="ok",
    )
    text = _rule_based_analysis(result, "SELECT 1", "SELECT 1")
    _require("semantically equivalent" in text.lower(), "Passed analysis should mention equivalence")


def _test_rule_analysis_pct_failure() -> None:
    from reconciliation.compare_results import ColumnDiff, CompareResult

    result = CompareResult(
        run_id=4,
        source_file="pct.sql",
        passed=False,
        source_rows=7,
        target_rows=7,
        columns_match=True,
        row_counts_match=True,
        source_csv="",
        target_csv="",
        report_path="",
        message="fail",
        column_diffs=[ColumnDiff(column="pct_of_total_revenue", mismatch_count=7)],
    )
    text = _rule_based_analysis(result, "SELECT 1", "SELECT 2")
    _require("pct_of_total_revenue" in text or "percentage" in text.lower(), "Should explain pct mismatch")


def _test_migration_sql_files_exist() -> None:
    missing = [name for name in EXPECTED_MIGRATION_SQL if not (SOURCE_MIGRATION_DIR / name).exists()]
    _require(not missing, f"Missing migration SQL files: {missing}")


def _test_input_schema_files_exist() -> None:
    missing = [name for name in EXPECTED_INPUT_TABLES if not (INPUT_SCHEMA_DIR / name).exists()]
    _require(not missing, f"Missing input schema files: {missing}")


def _test_teradata_env_aliases() -> None:
    """TERADATA_* env vars should be accepted when TD_* are unset."""
    saved = {k: os.environ.get(k) for k in ("TD_HOST", "TD_USER", "TD_PASSWORD", "TERADATA_HOST", "TERADATA_USER", "TERADATA_PASSWORD")}
    try:
        for key in saved:
            os.environ.pop(key, None)
        os.environ["TERADATA_HOST"] = "trial.example.com"
        os.environ["TERADATA_USER"] = "demo_user"
        os.environ["TERADATA_PASSWORD"] = "secret"
        cfg = load_teradata_config()
        _require(cfg.host == "trial.example.com", "TERADATA_HOST fallback failed")
        _require(cfg.user == "demo_user", "TERADATA_USER fallback failed")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _test_teradata_connection() -> None:
    from accelarator.source.teradata_store import get_teradata_connection

    config = load_teradata_config()
    with get_teradata_connection(config) as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        row = cur.fetchone()
        _require(row is not None and row[0] == 1, "Teradata health query failed")


def _test_bigquery_connection() -> None:
    from accelarator.gcp.client import test_connection

    result = test_connection()
    _require(bool(result.get("project_id")), f"BigQuery connection failed: {result}")


def _test_live_reconciliation_exports() -> None:
    """Exported CSVs exist, row counts match, and compare outcomes match metadata."""
    from accelarator.metadata import get_migration_run, list_migration_runs

    runs = [r for r in list_migration_runs() if r.get("source_result_path") and r.get("target_result_path")]
    _require(runs, "No reconciliation exports in metadata — run recon prep first")
    failures: list[str] = []
    for run in runs:
        run_id = int(run["run_id"])
        src = RECON_SOURCE / str(run_id) / "query_result.csv"
        tgt = RECON_TARGET / str(run_id) / "query_result.csv"
        if not src.exists() or not tgt.exists():
            failures.append(f"run {run_id}: missing CSV on disk")
            continue
        result = compare_dataframes(pd.read_csv(src), pd.read_csv(tgt), run_id=run_id)
        if not result.row_counts_match:
            failures.append(f"run {run_id}: row count mismatch ({result.source_rows} vs {result.target_rows})")
        stored = get_migration_run(run_id)
        if stored and stored.get("recon_passed") is not None and stored["recon_passed"] != result.passed:
            failures.append(
                f"run {run_id}: metadata recon_passed={stored['recon_passed']} "
                f"but comparison passed={result.passed}"
            )
    _require(not failures, "Reconciliation export issues:\n" + "\n".join(failures))


REGRESSION_TESTS: list[TestCase] = [
    TestCase(
        "schema_001",
        "sanitize_datetime_precision",
        "unit",
        "BigQuery DDL sanitizer strips DATETIME(n) and TIMESTAMP(n) precision.",
        _test_schema_sanitize_datetime,
    ),
    TestCase(
        "schema_002",
        "ddl_to_bigquery_customers",
        "unit",
        "Teradata customers DDL transpiles to qualified BigQuery CREATE TABLE.",
        _test_ddl_to_bigquery_customers,
    ),
    TestCase(
        "schema_003",
        "table_name_from_ddl",
        "unit",
        "Extract table name from orders DDL.",
        _test_table_name_from_ddl,
    ),
    TestCase(
        "loader_001",
        "truncate_string_columns",
        "unit",
        "CSV loader truncates STRING columns to BigQuery max_length.",
        _test_loader_truncates_strings,
    ),
    TestCase(
        "compare_001",
        "identical_frames_pass",
        "unit",
        "Identical dataframes should pass reconciliation comparison.",
        _test_compare_identical_frames,
    ),
    TestCase(
        "compare_002",
        "row_count_mismatch_fails",
        "unit",
        "Different row counts should fail comparison.",
        _test_compare_row_count_mismatch,
    ),
    TestCase(
        "compare_003",
        "numeric_tolerance_pass",
        "unit",
        "Numeric values within rtol/atol should pass.",
        _test_compare_numeric_tolerance,
    ),
    TestCase(
        "compare_004",
        "numeric_delta_fails",
        "unit",
        "Large numeric deltas should fail comparison.",
        _test_compare_numeric_failure,
    ),
    TestCase(
        "compare_005",
        "order_id_keyed_alignment",
        "unit",
        "Rows align on order_id regardless of sort order.",
        _test_compare_order_id_keyed_match,
    ),
    TestCase(
        "compare_006",
        "schema_mismatch_fails",
        "unit",
        "Different column sets should fail comparison.",
        _test_compare_schema_mismatch,
    ),
    TestCase(
        "report_001",
        "rule_analysis_passed",
        "unit",
        "Rule-based report text for passed runs.",
        _test_rule_analysis_passed,
    ),
    TestCase(
        "report_002",
        "rule_analysis_pct_failure",
        "unit",
        "Rule-based report explains pct_of_total_revenue mismatches.",
        _test_rule_analysis_pct_failure,
    ),
    TestCase(
        "assets_001",
        "migration_sql_files_exist",
        "assets",
        "All six Teradata migration SQL samples are present.",
        _test_migration_sql_files_exist,
    ),
    TestCase(
        "assets_002",
        "input_schema_files_exist",
        "assets",
        "Core input_schema DDL files (customers, orders, products) exist.",
        _test_input_schema_files_exist,
    ),
    TestCase(
        "config_001",
        "teradata_env_aliases",
        "unit",
        "TERADATA_* environment variables work as TD_* fallbacks.",
        _test_teradata_env_aliases,
    ),
    TestCase(
        "integration_001",
        "teradata_connection",
        "integration",
        "Live Teradata trial/cloud connection accepts queries.",
        _test_teradata_connection,
        requires_env=("TERADATA_HOST", "TERADATA_USER", "TERADATA_PASSWORD"),
        slow=True,
    ),
    TestCase(
        "integration_002",
        "bigquery_connection",
        "integration",
        "Live BigQuery connection succeeds with configured credentials.",
        _test_bigquery_connection,
        requires_env=("GCP_PROJECT_ID",),
        slow=True,
    ),
    TestCase(
        "integration_003",
        "live_reconciliation_exports",
        "integration",
        "Exported reconciliation CSVs exist with matching row counts and metadata consistency.",
        _test_live_reconciliation_exports,
        slow=True,
    ),
]
