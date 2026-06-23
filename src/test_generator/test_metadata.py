"""Extended documentation for each regression test (used in reports and catalog)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TestMetadata:
    component: str
    verifies: str
    steps: str
    expected: str


TEST_METADATA: dict[str, TestMetadata] = {
    "schema_001": TestMetadata(
        component="`src/accelarator/gcp/schema.py` → `_sanitize_bigquery_ddl()`",
        verifies="BigQuery rejects `DATETIME(0)` / `TIMESTAMP(n)` in CREATE TABLE DDL.",
        steps=(
            "1. Build sample DDL containing `DATETIME(0)` and `TIMESTAMP(6)`.\n"
            "2. Run `_sanitize_bigquery_ddl()`.\n"
            "3. Assert precision parentheses are removed."
        ),
        expected="Sanitized SQL contains plain `DATETIME` and `TIMESTAMP` without `(n)`.",
    ),
    "schema_002": TestMetadata(
        component="`src/accelarator/gcp/schema.py` → `ddl_to_bigquery_create()`",
        verifies="Teradata input DDL transpiles to a qualified BigQuery CREATE OR REPLACE TABLE.",
        steps=(
            "1. Read `src/input_schema/customers.sql`.\n"
            "2. Transpile to BigQuery for project `proj` / dataset `dataset`.\n"
            "3. Assert qualified table name and no invalid DATETIME precision."
        ),
        expected="SQL starts with `CREATE OR REPLACE TABLE \\`proj.dataset.customers\\``.",
    ),
    "schema_003": TestMetadata(
        component="`src/accelarator/gcp/schema.py` → `table_name_from_ddl()`",
        verifies="Table name is parsed correctly from Teradata DDL via sqlglot.",
        steps="1. Parse `orders.sql` DDL.\n2. Extract table identifier.",
        expected="Returned table name is `orders`.",
    ),
    "loader_001": TestMetadata(
        component="`src/accelarator/gcp/loader.py` → `_normalize_frame_for_schema()`",
        verifies="STRING columns are truncated to BigQuery `max_length` before CSV load.",
        steps=(
            "1. Create a dataframe with a 21-character phone value.\n"
            "2. Apply normalization against a STRING(20) schema field.\n"
            "3. Assert value is sliced to 20 characters."
        ),
        expected="Long string values are truncated; short values unchanged.",
    ),
    "compare_001": TestMetadata(
        component="`src/reconciliation/compare_results.py` → `compare_dataframes()`",
        verifies="Identical source/target result sets are reported as passed.",
        steps="1. Build two identical dataframes.\n2. Run comparison.",
        expected="`passed=True`, row counts match, no column diffs.",
    ),
    "compare_002": TestMetadata(
        component="`src/reconciliation/compare_results.py` → `compare_dataframes()`",
        verifies="Row count mismatches are detected and fail the comparison.",
        steps="1. Source has 2 rows, target has 1.\n2. Run comparison.",
        expected="`passed=False`, `row_counts_match=False`.",
    ),
    "compare_003": TestMetadata(
        component="`src/reconciliation/compare_results.py` → `_compare_column()`",
        verifies="Numeric values within rtol/atol are treated as equal.",
        steps="1. Compare 1.0000001 vs 1.0000002 with rtol=1e-4.\n2. Run comparison.",
        expected="`passed=True` (floating-point tolerance applied).",
    ),
    "compare_004": TestMetadata(
        component="`src/reconciliation/compare_results.py` → `_compare_column()`",
        verifies="Large numeric deltas fail the comparison.",
        steps="1. Compare 100.0 vs 200.0 on the same key.\n2. Run comparison.",
        expected="`passed=False` with numeric column mismatch.",
    ),
    "compare_005": TestMetadata(
        component="`src/reconciliation/compare_results.py` → `_align_frames()` / `_infer_merge_keys()`",
        verifies="Rows with the same `order_id` align even when sort order differs.",
        steps=(
            "1. Build source/target with same order_ids but shuffled rows.\n"
            "2. Compare using order_id as merge key."
        ),
        expected="`passed=True` — values match per order_id.",
    ),
    "compare_006": TestMetadata(
        component="`src/reconciliation/compare_results.py` → `compare_dataframes()`",
        verifies="Different column names fail before row-level compare.",
        steps="1. Source column `a`, target column `b`.\n2. Run comparison.",
        expected="`passed=False`, `columns_match=False`.",
    ),
    "report_001": TestMetadata(
        component="`src/reconciliation/recon_report.py` → `_rule_based_analysis()`",
        verifies="Passed reconciliation runs get a clear success explanation.",
        steps="1. Build a synthetic passed CompareResult.\n2. Generate rule-based analysis text.",
        expected="Text mentions semantic equivalence / all rows match.",
    ),
    "report_002": TestMetadata(
        component="`src/reconciliation/recon_report.py` → `_rule_based_analysis()`",
        verifies="Failed runs with `pct_of_total_revenue` diffs get a targeted explanation.",
        steps="1. Build failed result with pct column diff.\n2. Generate rule-based analysis.",
        expected="Text references percentage/window calculation differences.",
    ),
    "assets_001": TestMetadata(
        component="`src/source_files_for_migration/` (sample migration SQL)",
        verifies="All six Teradata→BigQuery migration sample files exist on disk.",
        steps="1. Check each file in EXPECTED_MIGRATION_SQL list.",
        expected="All six `.sql` files are present.",
    ),
    "assets_002": TestMetadata(
        component="`src/input_schema/` (base table DDL)",
        verifies="Core synthetic-data DDL files exist for recon provisioning.",
        steps="1. Check customers.sql, orders.sql, products.sql.",
        expected="All three DDL files are present.",
    ),
    "config_001": TestMetadata(
        component="`src/accelarator/source/teradata_config.py` → `load_teradata_config()`",
        verifies="`TERADATA_*` env vars work when `TD_*` vars are unset.",
        steps=(
            "1. Clear TD_* and TERADATA_* vars.\n"
            "2. Set TERADATA_HOST/USER/PASSWORD.\n"
            "3. Load config and assert values."
        ),
        expected="Config reads trial credentials from TERADATA_* fallbacks.",
    ),
    "integration_001": TestMetadata(
        component="`src/accelarator/source/teradata_store.py` + Teradata trial host",
        verifies="Live Teradata connection executes `SELECT 1`.",
        steps="1. Load config from `.env`.\n2. Open connection.\n3. Run health query.",
        expected="Query returns row with value `1`.",
    ),
    "integration_002": TestMetadata(
        component="`src/accelarator/gcp/client.py` → `test_connection()`",
        verifies="Live BigQuery client lists datasets in configured project.",
        steps="1. Load GCP config.\n2. Create BigQuery client.\n3. List datasets (sample).",
        expected="Returns project_id and sample dataset list without error.",
    ),
    "integration_003": TestMetadata(
        component="`reconciliation/source_results/` + `metadata/accelerator.duckdb`",
        verifies=(
            "Exported recon CSVs exist on disk, row counts match, and "
            "`recon_passed` in metadata matches comparison engine output."
        ),
        steps=(
            "1. Load migration runs with export paths from metadata.\n"
            "2. Verify CSV files exist.\n"
            "3. Compare row counts and metadata `recon_passed` vs compare result."
        ),
        expected="No missing files, row count mismatches, or metadata/compare disagreements.",
    ),
}


def metadata_for(test_id: str) -> TestMetadata | None:
    return TEST_METADATA.get(test_id)
