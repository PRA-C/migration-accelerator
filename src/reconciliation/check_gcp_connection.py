"""
Verify Google Cloud / BigQuery connectivity for reconciliation workflows.

Usage:
    uv run python -m reconciliation.check_gcp_connection
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def _load_service_account_project(credentials_path: Path) -> str | None:
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
        return data.get("project_id")
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    print("=" * 72)
    print("Google Cloud / BigQuery connection check")
    print("=" * 72)

    all_ok = True

    project_id = os.getenv("GCP_PROJECT_ID", "").strip()
    location = os.getenv("GCP_LOCATION", "US").strip()
    source_dataset = os.getenv("GCP_SOURCE_DATASET", "migration_source").strip()
    target_dataset = os.getenv("GCP_TARGET_DATASET", "migration_target").strip()
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip().strip('"')

    all_ok &= _check("GCP_PROJECT_ID set", bool(project_id), project_id or "missing")
    all_ok &= _check("GCP_LOCATION set", bool(location), location)

    creds_file = Path(credentials_path) if credentials_path else None
    if not credentials_path:
        all_ok &= _check(
            "GOOGLE_APPLICATION_CREDENTIALS set",
            False,
            "missing — set path to service account JSON in .env",
        )
    else:
        all_ok &= _check(
            "Credentials file exists",
            creds_file.is_file(),
            str(creds_file),
        )
        if creds_file and creds_file.is_file():
            sa_project = _load_service_account_project(creds_file)
            all_ok &= _check(
                "Service account JSON readable",
                sa_project is not None,
                f"project_id={sa_project}" if sa_project else "invalid JSON",
            )
            if sa_project and project_id:
                all_ok &= _check(
                    "Project ID matches service account",
                    sa_project == project_id,
                    f"env={project_id}, json={sa_project}",
                )

    if not all_ok:
        print("\nFix the failed checks above, then re-run.")
        return 1

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    try:
        from google.cloud import bigquery
        from google.cloud.exceptions import GoogleCloudError
    except ImportError:
        print("\n  [FAIL] google-cloud-bigquery not installed")
        print("  Run: uv sync")
        return 1

    print("\nConnecting to BigQuery...")
    try:
        client = bigquery.Client(project=project_id, location=location)
        datasets = list(client.list_datasets(max_results=20))
        _check("BigQuery API reachable", True, f"{len(datasets)} dataset(s) visible")

        dataset_ids = {d.dataset_id for d in datasets}
        for label, ds in [("Source dataset", source_dataset), ("Target dataset", target_dataset)]:
            exists = ds in dataset_ids
            _check(
                f"{label} '{ds}'",
                exists,
                "found" if exists else "not found yet (run scripts/gcp_bootstrap.py)",
            )

        # Lightweight query to confirm job execution permissions
        job = client.query("SELECT 1 AS connection_ok")
        row = next(job.result())
        _check("Test query (SELECT 1)", row.connection_ok == 1, "job submitted successfully")

        print("\n" + "=" * 72)
        print("Google Cloud connection is working.")
        print(f"  Project:  {project_id}")
        print(f"  Location: {location}")
        print(f"  Source:   `{project_id}.{source_dataset}`")
        print(f"  Target:   `{project_id}.{target_dataset}`")
        if source_dataset not in dataset_ids or target_dataset not in dataset_ids:
            print("\n  Note: bootstrap datasets with:")
            print("    uv run python scripts/gcp_bootstrap.py --role both")
        print("=" * 72)
        return 0

    except GoogleCloudError as exc:
        print(f"\n  [FAIL] BigQuery error: {exc}")
        print("\nCommon fixes:")
        print("  • Enable BigQuery API in GCP Console")
        print("  • Grant service account BigQuery Admin or Data Editor + Job User")
        print("  • Confirm GOOGLE_APPLICATION_CREDENTIALS path is correct")
        return 1
    except Exception as exc:
        print(f"\n  [FAIL] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
