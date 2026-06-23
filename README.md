# Migration Accelerator

AI-powered SQL migration tool that transpiles Teradata SQL to BigQuery using Claude, with automated validation, reconciliation, and documentation.

## Features

- **Interactive migration assistant** — select source/target databases, output format, and source files
- **LLM transpilation** — data engineer generates migrated code via Claude
- **Data manager validation** — reviews output for accuracy and retries up to 3 times
- **Reconciliation** — compare Teradata vs BigQuery query results
- **Regression tests** — automated test suite with markdown reports
- **Documentation** — auto-generated migration docs and data lineage
- **Synthetic data** — generate test data from DDL schemas

## Setup

```bash
uv sync
```

Copy `.env.example` to `.env` and fill in credentials:

```
ANTHROPIC_API_KEY=...
TD_HOST=...
TD_USER=...
TD_PASSWORD=...
GCP_PROJECT_ID=...
GCP_TARGET_DATASET=migration_target
```

## Usage

### Run migration assistant

```bash
uv run python -m accelarator.migration_assistant.translator
```

Reads SQL from `src/source_files_for_migration/`, writes transpiled output to `src/target_files_migration/`.

### Provision Teradata source tables

```bash
uv run python scripts/init_teradata_source.py
uv run python scripts/generate_synthetic_data.py
```

### Reconciliation

```bash
uv run python scripts/run_recon_all.py
uv run python -m reconciliation.compare_results
```

### Regression tests

```bash
uv run python -m test_generator
uv run python -m test_generator --integration --slow
uv run python -m test_generator --catalog --catalog-docs
```

### Generate documentation

```bash
uv run python -m documentation
```

## Project structure

```
migration-accelerator/
├── src/
│   ├── accelarator/              # Core package (LLM, GCP, metadata, data gen)
│   ├── reconciliation/           # Recon workflows, compare, reports
│   ├── test_generator/           # Regression test suite
│   ├── documentation/            # Doc + lineage generator
│   ├── input_schema/             # Base table DDL (Teradata)
│   └── source_files_for_migration/  # Input migration SQL
├── scripts/                      # Setup and batch utilities
├── metadata/                     # DuckDB run history (gitignored)
├── reconciliation/               # Recon CSV exports + reports (gitignored)
├── test_results/                 # Regression reports (gitignored)
├── documentation/                # Generated migration docs (gitignored)
├── docs/                         # Human-written reference (test catalog)
├── docker/                       # Local Teradata compose (optional)
└── credentials/                  # GCP service account JSON (gitignored)
```

## Supported databases

**Source:** Teradata (primary), Oracle, SQL Server, Netezza, PostgreSQL, MySQL

**Target:** BigQuery (primary), Snowflake, Redshift, Azure Synapse, Spark, PostgreSQL
