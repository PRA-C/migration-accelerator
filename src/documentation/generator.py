"""Generate migration documentation and data lineage under documentation/."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from accelarator.data_gen.engine import read_ddl_files
from accelarator.gcp.schema import table_name_from_ddl
from accelarator.metadata import get_migration_run, init_metadata_db, list_migration_runs

from .lineage import is_base_table, lineage_edges_for_run, referenced_tables

load_dotenv()

DOCS_ROOT = Path("documentation")
MIGRATIONS_DIR = DOCS_ROOT / "migrations"
OVERVIEW_PATH = DOCS_ROOT / "migration_overview.md"
LINEAGE_PATH = DOCS_ROOT / "lineage.md"
LINEAGE_JSON_PATH = DOCS_ROOT / "lineage.json"
INDEX_PATH = DOCS_ROOT / "README.md"


def _load_env_schemas() -> tuple[str, str]:
    source = os.getenv("TD_DATABASE", os.getenv("TERADATA_DATABASE", "teradata_source"))
    target = os.getenv("GCP_TARGET_DATASET", "bigquery_target")
    return source, target


def _ddl_summary(input_dir: str = "src/input_schema") -> list[dict]:
    summary: list[dict] = []
    for stem, ddl in sorted(read_ddl_files(input_dir).items()):
        try:
            table = table_name_from_ddl(ddl)
        except ValueError:
            table = stem
        columns = []
        for line in ddl.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("CREATE", ")", "(", "--", "PRIMARY")):
                continue
            col = line.split()[0].strip("`")
            if col.upper() not in ("MULTISET", "TABLE", "SET"):
                columns.append(col)
        summary.append({"stem": stem, "table": table, "columns": columns})
    return summary


def _recon_status_label(run: dict) -> str:
    if run.get("recon_passed") is True:
        return "recon passed"
    if run.get("recon_passed") is False:
        return "recon failed"
    recon_ind = run.get("recon_ind")
    if recon_ind:
        return str(recon_ind)
    return "pending"


def _run_detail_markdown(run: dict, lineage: dict) -> str:
    run_id = int(run["run_id"])
    source_file = run.get("source_file") or "unknown.sql"
    source_sql = run.get("source_code") or ""
    target_sql = run.get("generated_code") or ""
    tables = lineage.get("input_tables", [])

    parts = [
        f"# Migration Run {run_id}: {source_file}",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        "",
        "## Summary",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Run ID | {run_id} |",
        f"| Request | `{run.get('request_id', '')}` |",
        f"| Source | {run.get('source_type')} `{run.get('source_schema') or '-'}` |",
        f"| Target | {run.get('target_type')} `{run.get('target_schema') or '-'}` |",
        f"| Transpilation | {'success' if run.get('success') else 'failed'} |",
        f"| Validation | {'passed' if run.get('validation_passed') else 'failed'} |",
        f"| Reconciliation | {_recon_status_label(run)} |",
        f"| Created | {run.get('created_at', '')} |",
        "",
        "## Data lineage (this query)",
        "",
        "**Reads from tables:**",
        "",
    ]
    if tables:
        for table in tables:
            tag = "base table" if is_base_table(table) else "referenced"
            parts.append(f"- `{table}` ({tag})")
    else:
        parts.append("- _No tables detected in SQL_")

    parts.extend(
        [
            "",
            "```mermaid",
            "flowchart LR",
        ]
    )
    src_schema = run.get("source_schema") or "source"
    tgt_schema = run.get("target_schema") or "target"
    for table in tables:
        parts.append(f"  {table}[{src_schema}.{table}] --> run{run_id}[{source_file}]")
    parts.append(f"  run{run_id} --> result[{tgt_schema} query result]")
    parts.append("```")
    parts.append("")

    if run.get("error_message"):
        parts.extend(["## Validation / errors", "", f"```text", str(run["error_message"]), "```", ""])

    parts.extend(["## Teradata source SQL", "", "```sql", source_sql.strip() or "-- empty", "```", ""])
    parts.extend(["## BigQuery target SQL", "", "```sql", target_sql.strip() or "-- empty", "```", ""])

    if run.get("source_result_path") or run.get("target_result_path"):
        parts.extend(
            [
                "## Reconciliation artifacts",
                "",
                f"- Source CSV: `{run.get('source_result_path') or '-'}`",
                f"- Target CSV: `{run.get('target_result_path') or '-'}`",
                f"- Report: `{run.get('recon_result_path') or '-'}`",
                "",
            ]
        )

    return "\n".join(parts)


def _overview_markdown(
    runs: list[dict],
    lineage_records: list[dict],
    ddl_rows: list[dict],
    *,
    executive_summary: str | None = None,
) -> str:
    source_schema, target_schema = _load_env_schemas()
    parts = [
        "# Migration Overview",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Pipeline:** Teradata (`{source_schema}`) → BigQuery (`{target_schema}`)  ",
        f"**Metadata:** `metadata/accelerator.duckdb`  ",
        "",
    ]
    if executive_summary:
        parts.extend(["## Executive summary", "", executive_summary.strip(), ""])
    parts.extend(
        [
            "## Platform inventory",
            "",
            "| Layer | Technology | Location |",
            "|-------|------------|----------|",
            f"| Source warehouse | Teradata | `{source_schema}` |",
            f"| Target warehouse | BigQuery | `{target_schema}` |",
            "| Run history | DuckDB | `metadata/accelerator.duckdb` |",
            "| Base DDL | Teradata | `src/input_schema/` |",
            "| Migration SQL | Teradata | `src/source_files_for_migration/` |",
            "| Synthetic data | CSV | `src/synthetic_data_gen/` |",
            "",
            "## Base tables (input schema)",
            "",
            "| Table | Columns |",
            "|-------|---------|",
        ]
    )
    for row in ddl_rows:
        if row["stem"] == "ecommerce":
            continue
        cols = ", ".join(f"`{c}`" for c in row["columns"][:8])
        if len(row["columns"]) > 8:
            cols += ", …"
        parts.append(f"| `{row['table']}` | {cols} |")

    parts.extend(
        [
            "",
            "## Migration runs",
            "",
            "| Run | SQL file | Source → Target | Transpile | Recon | Tables read |",
            "|-----|----------|-----------------|-----------|-------|-------------|",
        ]
    )
    lineage_by_id = {r["run_id"]: r for r in lineage_records}
    for run in sorted(runs, key=lambda r: int(r["run_id"])):
        rid = int(run["run_id"])
        lin = lineage_by_id.get(rid, {})
        tables = ", ".join(f"`{t}`" for t in lin.get("input_tables", [])[:4])
        if len(lin.get("input_tables", [])) > 4:
            tables += ", …"
        parts.append(
            f"| {rid} | {run.get('source_file', '-')} | "
            f"{run.get('source_type')} → {run.get('target_type')} | "
            f"{'✓' if run.get('success') else '✗'} | {_recon_status_label(run)} | {tables or '-'} |"
        )

    parts.extend(
        [
            "",
            "## Per-run documentation",
            "",
        ]
    )
    for run in sorted(runs, key=lambda r: int(r["run_id"])):
        rid = int(run["run_id"])
        stem = (run.get("source_file") or "run").replace(".sql", "")
        parts.append(f"- [Run {rid}: {run.get('source_file')}](migrations/run_{rid:03d}_{stem}.md)")

    parts.extend(
        [
            "",
            "## Related documents",
            "",
            "- [Data lineage diagram](lineage.md)",
            "- [Lineage JSON](lineage.json) (machine-readable)",
            "- [Reconciliation report](../reconciliation/reconciliation_report.md)",
            "",
        ]
    )
    return "\n".join(parts)


def _lineage_markdown(
    lineage_records: list[dict],
    ddl_rows: list[dict],
    runs: list[dict],
) -> str:
    source_schema, target_schema = _load_env_schemas()
    base_tables = [r["table"] for r in ddl_rows if r["stem"] != "ecommerce"]

    parts = [
        "# Data Lineage",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        "",
        "End-to-end flow from synthetic base tables through migration queries to reconciliation exports.",
        "",
        "## End-to-end pipeline",
        "",
        "```mermaid",
        "flowchart TB",
        "  subgraph ingest [Data ingest]",
        f"    csv[synthetic_data_gen CSV]",
        f"    td_load[Teradata {source_schema}]",
        f"    bq_load[BigQuery {target_schema}]",
        "  end",
        "  subgraph base [Base tables]",
    ]
    for table in base_tables:
        parts.append(f"    {table}[{table}]")
    parts.append("  end")
    parts.append("  subgraph migrations [Migration queries]")
    for run in sorted(runs, key=lambda r: int(r["run_id"])):
        rid = int(run["run_id"])
        label = (run.get("source_file") or f"run_{rid}").replace(".sql", "")
        parts.append(f"    run{rid}[run {rid}: {label}]")
    parts.append("  end")
    parts.append("  subgraph recon [Reconciliation]")
    parts.append("    src_csv[source_results CSV]")
    parts.append("    tgt_csv[target_results CSV]")
    parts.append("  end")
    parts.append("  csv --> td_load")
    parts.append("  csv --> bq_load")
    for table in base_tables:
        parts.append(f"  td_load --> {table}")
        parts.append(f"  bq_load --> {table}")
    for rec in lineage_records:
        rid = rec["run_id"]
        for table in rec.get("base_tables", []):
            parts.append(f"  {table} --> run{rid}")
        parts.append(f"  run{rid} --> src_csv")
        parts.append(f"  run{rid} --> tgt_csv")
    parts.extend(["```", "", "## Table usage matrix", ""])
    parts.append("| Base table | Used by migration runs |")
    parts.append("|------------|------------------------|")
    usage: dict[str, list[int]] = {t: [] for t in base_tables}
    for rec in lineage_records:
        for table in rec.get("base_tables", []):
            if table in usage:
                usage[table].append(rec["run_id"])
    for table in base_tables:
        run_ids = ", ".join(str(i) for i in sorted(usage[table])) or "—"
        parts.append(f"| `{table}` | {run_ids} |")

    parts.extend(["", "## Per-run lineage", ""])
    for rec in sorted(lineage_records, key=lambda r: r["run_id"]):
        parts.append(f"### Run {rec['run_id']}: `{rec['source_file']}`")
        parts.append("")
        parts.append(f"- **Source schema:** `{rec['source_schema']}`")
        parts.append(f"- **Target schema:** `{rec['target_schema']}`")
        parts.append(f"- **Tables read:** {', '.join(f'`{t}`' for t in rec.get('input_tables', [])) or '—'}")
        parts.append("")

    return "\n".join(parts)


def _index_markdown() -> str:
    return "\n".join(
        [
            "# Migration Accelerator Documentation",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            "",
            "Auto-generated documentation for SQL migrations and data lineage.",
            "",
            "## Documents",
            "",
            "| Document | Description |",
            "|----------|-------------|",
            "| [migration_overview.md](migration_overview.md) | All migration runs, base tables, platform inventory |",
            "| [lineage.md](lineage.md) | Data lineage diagrams and table usage matrix |",
            "| [lineage.json](lineage.json) | Machine-readable lineage graph |",
            "| [migrations/](migrations/) | Per-run SQL and lineage detail |",
            "",
            "## Regenerate",
            "",
            "```powershell",
            "uv run python -m documentation",
            "```",
            "",
        ]
    )


def _llm_executive_summary(runs: list[dict], lineage_records: list[dict]) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or not runs:
        return None
    try:
        from accelarator.llm import ask_claude

        payload = {
            "run_count": len(runs),
            "runs": [
                {
                    "run_id": int(r["run_id"]),
                    "source_file": r.get("source_file"),
                    "success": r.get("success"),
                    "recon_passed": r.get("recon_passed"),
                    "tables": next(
                        (x.get("input_tables") for x in lineage_records if x["run_id"] == int(r["run_id"])),
                        [],
                    ),
                }
                for r in runs
            ],
        }
        prompt = (
            "Write a short executive summary (3-5 paragraphs) for a Teradata→BigQuery "
            "migration portfolio. Cover scope, table dependencies, reconciliation status, "
            "and risks. Use markdown. Facts only from JSON.\n\n"
            f"```json\n{json.dumps(payload, indent=2)}\n```"
        )
        system = "You are a data migration architect writing clear technical documentation."
        return ask_claude(prompt=prompt, system=system, max_tokens=1500)
    except Exception:
        return None


def generate_documentation(*, use_llm: bool = True) -> Path:
    """Generate all documentation files. Returns documentation root path."""
    init_metadata_db()
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    runs_summary = list_migration_runs()
    default_src, default_tgt = _load_env_schemas()
    ddl_rows = _ddl_summary()

    lineage_records: list[dict] = []
    for summary in sorted(runs_summary, key=lambda r: int(r["run_id"])):
        run_id = int(summary["run_id"])
        run = get_migration_run(run_id) or summary
        src_schema = run.get("source_schema") or default_src
        tgt_schema = run.get("target_schema") or default_tgt
        record = lineage_edges_for_run(
            run_id,
            run.get("source_file") or "",
            run.get("source_code") or "",
            run.get("generated_code") or "",
            source_schema=src_schema,
            target_schema=tgt_schema,
        )
        lineage_records.append(record)

        stem = (run.get("source_file") or f"run_{run_id}").replace(".sql", "")
        detail_path = MIGRATIONS_DIR / f"run_{run_id:03d}_{stem}.md"
        detail_path.write_text(_run_detail_markdown(run, record), encoding="utf-8")

    executive_summary = _llm_executive_summary(runs_summary, lineage_records) if use_llm else None
    OVERVIEW_PATH.write_text(
        _overview_markdown(runs_summary, lineage_records, ddl_rows, executive_summary=executive_summary),
        encoding="utf-8",
    )
    LINEAGE_PATH.write_text(_lineage_markdown(lineage_records, ddl_rows, runs_summary), encoding="utf-8")

    lineage_doc = {
        "generated_at": datetime.now().isoformat(),
        "source_schema": default_src,
        "target_schema": default_tgt,
        "base_tables": [r for r in ddl_rows if r["stem"] != "ecommerce"],
        "runs": lineage_records,
    }
    LINEAGE_JSON_PATH.write_text(json.dumps(lineage_doc, indent=2), encoding="utf-8")
    INDEX_PATH.write_text(_index_markdown(), encoding="utf-8")

    return DOCS_ROOT
