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

### Run full agent pipeline (LangGraph)

Runs all agents sequentially: provision → migrate → reconcile → test → document.

```bash
uv run python -m agents
uv run python -m agents --list-agents
uv run python -m agents --skip-provision --skip-migrate --no-llm
```

### Web UI (React + FastAPI)

**Development** — run API and frontend in two terminals:

```bash
# Terminal 1 — API on http://127.0.0.1:8000
uv run python -m api

# Terminal 2 — React dev server on http://127.0.0.1:5173 (proxies /api)
cd frontend && npm install && npm run dev
```

**Production** — build the frontend and serve it from the API:

```bash
cd frontend && npm install && npm run build
uv run python -m api
```

Open http://127.0.0.1:8000 for the dashboard, operations (SSE pipeline), AI chat, migrations, SQL studio, and reports.

### Legacy Gradio UI

```bash
uv run python app.py
```

Deprecated in favor of the React + FastAPI UI above.

## Project structure

```
migration-accelerator/
├── src/
│   ├── accelarator/              # Core package (LLM, GCP, metadata, data gen)
│   ├── reconciliation/           # Recon workflows, compare, reports
│   ├── test_generator/           # Regression test suite
│   ├── documentation/            # Doc + lineage generator
│   ├── agents/                   # LangGraph agent pipeline orchestrator
│   ├── api/                      # FastAPI REST + SSE backend
│   ├── frontend/                 # React + Vite UI (npm)
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
