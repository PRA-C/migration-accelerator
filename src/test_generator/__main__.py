"""
Regression test suite for the migration accelerator.

Runs unit, asset, and optional integration tests; writes
test_results/regression_report.md (with optional LLM failure analysis)
and test_results/test_catalog.md (reference list of all test cases).

Usage:
    uv run python -m test_generator
    uv run python -m test_generator --integration --slow
    uv run python -m test_generator --catalog
    uv run python -m test_generator --no-llm
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from test_generator.catalog import CATALOG_PATH, generate_test_catalog
from test_generator.report import generate_regression_report
from test_generator.runner import run_regression_suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run migration accelerator regression tests")
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="Only generate test_results/test_catalog.md (no test execution)",
    )
    parser.add_argument(
        "--catalog-docs",
        action="store_true",
        help="Also write docs/regression_test_catalog.md (committed reference copy)",
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Include integration tests (Teradata, BigQuery, live reconciliation CSVs)",
    )
    parser.add_argument(
        "--slow",
        action="store_true",
        help="Include slow tests (required for integration tests)",
    )
    parser.add_argument(
        "--test-ids",
        help="Comma-separated test ids to run (e.g. compare_001,schema_001)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM failure analysis in the markdown report",
    )
    args = parser.parse_args(argv)

    if args.catalog:
        path = generate_test_catalog(also_write_docs=args.catalog_docs)
        print(f"Test catalog written to {path}")
        if args.catalog_docs:
            print("Also written to docs/regression_test_catalog.md")
        return 0

    test_ids = None
    if args.test_ids:
        test_ids = [part.strip() for part in args.test_ids.split(",") if part.strip()]

    include_slow = args.slow or args.integration
    result = run_regression_suite(
        include_integration=args.integration,
        include_slow=include_slow,
        test_ids=test_ids,
    )

    report_path = generate_regression_report(result, use_llm=not args.no_llm)
    catalog_path = generate_test_catalog(also_write_docs=args.catalog_docs)

    print("\n" + "=" * 80)
    print("REGRESSION TEST SUITE")
    print("=" * 80)
    for outcome in result.outcomes:
        print(
            f"  [{outcome.test_id}] {outcome.name:<32} "
            f"{outcome.status.upper():<7} {outcome.duration_ms:>8.1f} ms"
        )
        if outcome.status == "skipped":
            print(f"         skip: {outcome.skip_reason}")
        elif outcome.status == "failed":
            print(f"         error: {outcome.message}")
    print("=" * 80)
    print(
        f"Summary: passed={result.passed} failed={result.failed} "
        f"skipped={result.skipped}"
    )
    print(f"  Run report  → {report_path}")
    print(f"  Test catalog → {catalog_path}")
    print("=" * 80)

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
