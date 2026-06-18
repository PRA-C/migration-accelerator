# Migration Accelerator

AI-powered SQL migration tool that transpiles source database code to target platforms using Claude, with automated validation and retry.

## Features

- **Interactive migration assistant** — select source/target databases, output format, and source files
- **LLM transpilation** — data engineer generates migrated code via Claude
- **Data manager validation** — reviews output for accuracy and retries up to 3 times
- **File-based workflow** — read from `src/source_files_for_migration/`, write to `src/target_files_migration/`
- **Synthetic data engine** — generate test data from DDL schemas in `src/input_schema/`

## Setup

```bash
uv sync
uv pip install -e .
```

Create a `.env` file:

```
ANTHROPIC_API_KEY=your_key_here
```

## Usage

### Run migration assistant

```bash
uv run python -m accelarator.migration_assistant.translator
```

1. Select source and target database
2. Choose output format (Target SQL, PySpark, Python connector, dbt, etc.)
3. Load SQL from `src/source_files_for_migration/` or paste manually
4. Confirm — migrated output is saved to `src/target_files_migration/`

### Generate synthetic data

```bash
uv run python -m src.accelarator.data_gen.engine
```

## Project structure

```
src/
├── accelarator/
│   ├── llm.py                    # Claude API + data manager validation
│   ├── migration_assistant/
│   │   ├── translator.py         # Interactive CLI
│   │   ├── transpiler.py         # LLM transpilation loop
│   │   └── io_handlers.py        # Models and file I/O
│   └── data_gen/
│       └── engine.py             # Synthetic data generator
├── source_files_for_migration/   # Input SQL/procedures
└── target_files_migration/       # Generated migration output
```

## Supported databases

**Source:** Teradata, Oracle, SQL Server, Netezza, PostgreSQL, MySQL

**Target:** Snowflake, Redshift, BigQuery, Azure Synapse, Spark, PostgreSQL
