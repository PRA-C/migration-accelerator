"""
Interactive migration reconciliation prep against migration_runs metadata.

For each selected run:
  1. Use shared Teradata database (TD_DATABASE) and BigQuery dataset (GCP_TARGET_DATASET)
  2. Provision base tables once per batch (customers, orders, products)
  3. Execute source & target SQL
  4. Export CSV results per run_id for later comparison

Usage:
    uv run python -m reconciliation.migration_recon
"""

from __future__ import annotations

import io
import sys

from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from accelarator.metadata import (
    METADATA_DB_PATH,
    get_migration_run,
    init_metadata_db,
    list_migration_runs,
)
from reconciliation.recon_executor import prepare_migration_run
from reconciliation.result_exporter import RECON_SOURCE_RESULTS_DIR, RECON_TARGET_RESULTS_DIR
from reconciliation.schema_provisioner import provision_recon_schemas, recon_schema_names


def _format_recon_ind(value: str | None) -> str:
    return value if value else "-"


def _print_runs(runs: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("MIGRATION RUNS (metadata/accelerator.duckdb | source: Teradata → target: BigQuery)")
    print("=" * 100)
    if not runs:
        print("No migration runs found.")
        return

    for run in runs:
        label = run.get("source_file") or run.get("request_id") or "unknown"
        src_schema = run.get("source_schema") or "-"
        tgt_schema = run.get("target_schema") or "-"
        print(
            f"  [{run['run_id']:>4}] {label:<30} "
            f"{run['source_type']} → {run['target_type']:<10} "
            f"recon={_format_recon_ind(run.get('recon_ind')):<10} "
            f"src={src_schema:<16} tgt={tgt_schema}"
        )
        if run.get("recon_result_path"):
            passed = run.get("recon_passed")
            verdict = "passed" if passed else "failed" if passed is False else "-"
            print(f"         compare: {verdict}  report={run.get('recon_result_path')}")
    print("=" * 100)


def _parse_run_selection(raw: str, runs: list[dict]) -> list[int]:
    raw = raw.strip().upper()
    if not raw:
        return []

    run_ids = {int(r["run_id"]) for r in runs}

    if raw == "A":
        return sorted(run_ids)

    if raw == "P":
        return sorted(r["run_id"] for r in runs if r.get("recon_ind") is None)

    selected: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            for i in range(int(start_s), int(end_s) + 1):
                if i in run_ids:
                    selected.append(i)
        elif part.isdigit():
            val = int(part)
            if val in run_ids:
                selected.append(val)
    return sorted(set(selected))


def select_runs_for_recon() -> list[int]:
    runs = list_migration_runs()
    _print_runs(runs)

    if not runs:
        return []

    print("\nSelection options:")
    print("  • Enter run_id(s): 1,3,5")
    print("  • Range: 1-4")
    print("  • A = all runs")
    print("  • P = pending only (recon_ind IS NULL)")
    print("  • Q = quit")

    choice = input("\nSelect run(s) for reconciliation prep: ").strip()
    if choice.upper() == "Q":
        return []

    return _parse_run_selection(choice, runs)


def run_reconciliation_prep(run_ids: list[int]) -> None:
    if not run_ids:
        print("No runs selected.")
        return

    try:
        source_schema, target_schema = recon_schema_names()
    except ValueError as exc:
        print(f"\nConfiguration error: {exc}")
        return

    print(f"\nPreparing {len(run_ids)} run(s)...")
    print(f"  Shared schemas: Teradata {source_schema} / BigQuery {target_schema}")
    print(f"  Source results → {RECON_SOURCE_RESULTS_DIR}/{{run_id}}/")
    print(f"  Target results → {RECON_TARGET_RESULTS_DIR}/{{run_id}}/\n")

    prepared = failed = skipped = 0

    try:
        provision_recon_schemas()
    except Exception as exc:
        print(f"Schema provisioning failed: {exc}")
        return

    for run_id in run_ids:
        run = get_migration_run(run_id)
        if not run:
            print(f"  [{run_id}] NOT FOUND")
            failed += 1
            continue

        label = run.get("source_file") or run.get("request_id")
        if not run.get("success"):
            err = (run.get("error_message") or "validation failed")[:120]
            print(f"  [{run_id}] {label}  ⚠ migration validation failed: {err}...")
        else:
            print(f"  [{run_id}] {label}")

        result = prepare_migration_run(run, provision=False)

        print(f"         {result.message}")
        if result.source_schema:
            print(f"         schemas: {result.source_schema} / {result.target_schema}")
        if result.source_result_path:
            print(f"         source CSV: {result.source_result_path}")
        if result.target_result_path:
            print(f"         target CSV: {result.target_result_path}")

        if result.recon_ind == "prepared":
            prepared += 1
        elif result.recon_ind == "skipped":
            skipped += 1
        else:
            failed += 1

    print("\n" + "=" * 100)
    print(f"Prep complete: prepared={prepared}, failed={failed}, skipped={skipped}")
    print("Compare results: uv run python -m reconciliation.compare_results")
    print("Report: reconciliation/reconciliation_report.md")
    print("Compare CSVs under reconciliation/source_results vs reconciliation/target_results")
    print("=" * 100)


def main() -> int:
    init_metadata_db()
    print(f"\nMetadata DB: {METADATA_DB_PATH}\n")

    run_ids = select_runs_for_recon()
    if not run_ids:
        print("Exiting.")
        return 0

    confirm = input(
        f"\nProvision schemas, load synthetic data, and export results for run_id(s) {run_ids}? (yes/no): "
    ).strip().lower()
    if confirm not in ("yes", "y"):
        print("Cancelled.")
        return 0

    run_reconciliation_prep(run_ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
