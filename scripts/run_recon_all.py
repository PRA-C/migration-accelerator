"""Provision recon schemas and prepare all pending migration runs."""
from __future__ import annotations

from accelarator.metadata import get_migration_run, list_migration_runs
from reconciliation.recon_executor import prepare_migration_run
from reconciliation.schema_provisioner import provision_recon_schemas


def main() -> None:
    provision_recon_schemas()
    prepared = failed = 0
    for run in sorted(list_migration_runs(), key=lambda r: r["run_id"]):
        result = prepare_migration_run(get_migration_run(run["run_id"]), provision=False)
        print(
            f"run {run['run_id']}: {result.recon_ind} "
            f"src={result.source_rows} tgt={result.target_rows}"
        )
        if result.recon_ind == "prepared":
            prepared += 1
        else:
            failed += 1
            print(" ", result.message[:200])
    print(f"SUMMARY prepared={prepared} failed={failed}")


if __name__ == "__main__":
    main()
