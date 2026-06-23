# Regression Test Catalog

**Generated:** 2026-06-23 22:50:09 UTC  
**Source:** `src/test_generator/registry.py` (`REGRESSION_TESTS`)  
**Total tests:** 18  

> This file is auto-generated. Edit test definitions in `registry.py`, then run 
> `uv run python -m test_generator --catalog` to refresh.

## Quick reference

| Category | Count | How to include |
|----------|-------|----------------|
| unit | 13 | default run |
| assets | 2 | default run |
| integration | 3 | `--integration --slow` |

## Commands

```powershell
# Regenerate this catalog only
uv run python -m test_generator --catalog

# Run unit + asset tests
uv run python -m test_generator

# Run full suite (includes integration)
uv run python -m test_generator --integration --slow

# Run specific tests
uv run python -m test_generator --test-ids compare_001,schema_001
```

## Unit tests

| Test ID | Name | Description | Required env | Slow | Run with |
|---------|------|-------------|--------------|------|----------|
| `schema_001` | sanitize_datetime_precision | BigQuery DDL sanitizer strips DATETIME(n) and TIMESTAMP(n) precision. | — | no | `uv run python -m test_generator` |
| `schema_002` | ddl_to_bigquery_customers | Teradata customers DDL transpiles to qualified BigQuery CREATE TABLE. | — | no | `uv run python -m test_generator` |
| `schema_003` | table_name_from_ddl | Extract table name from orders DDL. | — | no | `uv run python -m test_generator` |
| `loader_001` | truncate_string_columns | CSV loader truncates STRING columns to BigQuery max_length. | — | no | `uv run python -m test_generator` |
| `compare_001` | identical_frames_pass | Identical dataframes should pass reconciliation comparison. | — | no | `uv run python -m test_generator` |
| `compare_002` | row_count_mismatch_fails | Different row counts should fail comparison. | — | no | `uv run python -m test_generator` |
| `compare_003` | numeric_tolerance_pass | Numeric values within rtol/atol should pass. | — | no | `uv run python -m test_generator` |
| `compare_004` | numeric_delta_fails | Large numeric deltas should fail comparison. | — | no | `uv run python -m test_generator` |
| `compare_005` | order_id_keyed_alignment | Rows align on order_id regardless of sort order. | — | no | `uv run python -m test_generator` |
| `compare_006` | schema_mismatch_fails | Different column sets should fail comparison. | — | no | `uv run python -m test_generator` |
| `report_001` | rule_analysis_passed | Rule-based report text for passed runs. | — | no | `uv run python -m test_generator` |
| `report_002` | rule_analysis_pct_failure | Rule-based report explains pct_of_total_revenue mismatches. | — | no | `uv run python -m test_generator` |
| `config_001` | teradata_env_aliases | TERADATA_* environment variables work as TD_* fallbacks. | — | no | `uv run python -m test_generator` |

### `schema_001` — sanitize_datetime_precision

- **Category:** unit
- **Description:** BigQuery DDL sanitizer strips DATETIME(n) and TIMESTAMP(n) precision.
- **Typical run:** `uv run python -m test_generator`

### `schema_002` — ddl_to_bigquery_customers

- **Category:** unit
- **Description:** Teradata customers DDL transpiles to qualified BigQuery CREATE TABLE.
- **Typical run:** `uv run python -m test_generator`

### `schema_003` — table_name_from_ddl

- **Category:** unit
- **Description:** Extract table name from orders DDL.
- **Typical run:** `uv run python -m test_generator`

### `loader_001` — truncate_string_columns

- **Category:** unit
- **Description:** CSV loader truncates STRING columns to BigQuery max_length.
- **Typical run:** `uv run python -m test_generator`

### `compare_001` — identical_frames_pass

- **Category:** unit
- **Description:** Identical dataframes should pass reconciliation comparison.
- **Typical run:** `uv run python -m test_generator`

### `compare_002` — row_count_mismatch_fails

- **Category:** unit
- **Description:** Different row counts should fail comparison.
- **Typical run:** `uv run python -m test_generator`

### `compare_003` — numeric_tolerance_pass

- **Category:** unit
- **Description:** Numeric values within rtol/atol should pass.
- **Typical run:** `uv run python -m test_generator`

### `compare_004` — numeric_delta_fails

- **Category:** unit
- **Description:** Large numeric deltas should fail comparison.
- **Typical run:** `uv run python -m test_generator`

### `compare_005` — order_id_keyed_alignment

- **Category:** unit
- **Description:** Rows align on order_id regardless of sort order.
- **Typical run:** `uv run python -m test_generator`

### `compare_006` — schema_mismatch_fails

- **Category:** unit
- **Description:** Different column sets should fail comparison.
- **Typical run:** `uv run python -m test_generator`

### `report_001` — rule_analysis_passed

- **Category:** unit
- **Description:** Rule-based report text for passed runs.
- **Typical run:** `uv run python -m test_generator`

### `report_002` — rule_analysis_pct_failure

- **Category:** unit
- **Description:** Rule-based report explains pct_of_total_revenue mismatches.
- **Typical run:** `uv run python -m test_generator`

### `config_001` — teradata_env_aliases

- **Category:** unit
- **Description:** TERADATA_* environment variables work as TD_* fallbacks.
- **Typical run:** `uv run python -m test_generator`

## Assets tests

| Test ID | Name | Description | Required env | Slow | Run with |
|---------|------|-------------|--------------|------|----------|
| `assets_001` | migration_sql_files_exist | All six Teradata migration SQL samples are present. | — | no | `uv run python -m test_generator` |
| `assets_002` | input_schema_files_exist | Core input_schema DDL files (customers, orders, products) exist. | — | no | `uv run python -m test_generator` |

### `assets_001` — migration_sql_files_exist

- **Category:** assets
- **Description:** All six Teradata migration SQL samples are present.
- **Typical run:** `uv run python -m test_generator`

### `assets_002` — input_schema_files_exist

- **Category:** assets
- **Description:** Core input_schema DDL files (customers, orders, products) exist.
- **Typical run:** `uv run python -m test_generator`

## Integration tests

| Test ID | Name | Description | Required env | Slow | Run with |
|---------|------|-------------|--------------|------|----------|
| `integration_001` | teradata_connection | Live Teradata trial/cloud connection accepts queries. | TERADATA_HOST, TERADATA_USER, TERADATA_PASSWORD | yes | `uv run python -m test_generator --integration --slow` |
| `integration_002` | bigquery_connection | Live BigQuery connection succeeds with configured credentials. | GCP_PROJECT_ID | yes | `uv run python -m test_generator --integration --slow` |
| `integration_003` | live_reconciliation_exports | Exported reconciliation CSVs exist with matching row counts and metadata consistency. | — | yes | `uv run python -m test_generator --integration --slow` |

### `integration_001` — teradata_connection

- **Category:** integration
- **Description:** Live Teradata trial/cloud connection accepts queries.
- **Required env:** TERADATA_HOST, TERADATA_USER, TERADATA_PASSWORD
- **Slow:** yes (use `--slow` or `--integration`)
- **Typical run:** `uv run python -m test_generator --integration --slow`

### `integration_002` — bigquery_connection

- **Category:** integration
- **Description:** Live BigQuery connection succeeds with configured credentials.
- **Required env:** GCP_PROJECT_ID
- **Slow:** yes (use `--slow` or `--integration`)
- **Typical run:** `uv run python -m test_generator --integration --slow`

### `integration_003` — live_reconciliation_exports

- **Category:** integration
- **Description:** Exported reconciliation CSVs exist with matching row counts and metadata consistency.
- **Slow:** yes (use `--slow` or `--integration`)
- **Typical run:** `uv run python -m test_generator --integration --slow`
