"""Generate a human-readable catalog of all regression test cases."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .registry import REGRESSION_TESTS
from .suite import TestCase
from .test_metadata import metadata_for

CATALOG_PATH = Path("test_results/test_catalog.md")
DOCS_CATALOG_PATH = Path("docs/regression_test_catalog.md")


def _env_label(test: TestCase) -> str:
    if not test.requires_env:
        return "—"
    return ", ".join(test.requires_env)


def _run_hint(test: TestCase) -> str:
    if test.category == "integration":
        return "`uv run python -m test_generator --integration --slow`"
    return "`uv run python -m test_generator`"


def generate_test_catalog(
    *,
    output_path: Path | None = None,
    also_write_docs: bool = False,
) -> Path:
    """Write markdown catalog of all registered tests. Returns primary output path."""
    output_path = output_path or CATALOG_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    by_category: dict[str, list[TestCase]] = {}
    for test in REGRESSION_TESTS:
        by_category.setdefault(test.category, []).append(test)

    parts = [
        "# Regression Test Catalog",
        "",
        f"**Generated:** {generated}  ",
        f"**Source:** `src/test_generator/registry.py` (`REGRESSION_TESTS`)  ",
        f"**Total tests:** {len(REGRESSION_TESTS)}  ",
        "",
        "> This file is auto-generated. Edit test definitions in `registry.py`, then run ",
        "> `uv run python -m test_generator --catalog` to refresh.",
        "",
        "## Quick reference",
        "",
        "| Category | Count | How to include |",
        "|----------|-------|----------------|",
    ]

    for category in ("unit", "assets", "integration"):
        tests = by_category.get(category, [])
        if not tests:
            continue
        include = (
            "`--integration --slow`" if category == "integration" else "default run"
        )
        parts.append(f"| {category} | {len(tests)} | {include} |")

    parts.extend(
        [
            "",
            "## Commands",
            "",
            "```powershell",
            "# Regenerate this catalog only",
            "uv run python -m test_generator --catalog",
            "",
            "# Run unit + asset tests",
            "uv run python -m test_generator",
            "",
            "# Run full suite (includes integration)",
            "uv run python -m test_generator --integration --slow",
            "",
            "# Run specific tests",
            "uv run python -m test_generator --test-ids compare_001,schema_001",
            "```",
            "",
        ]
    )

    for category in ("unit", "assets", "integration"):
        tests = by_category.get(category, [])
        if not tests:
            continue
        parts.append(f"## {category.title()} tests")
        parts.append("")
        parts.append(
            "| Test ID | Name | Description | Required env | Slow | Run with |"
        )
        parts.append(
            "|---------|------|-------------|--------------|------|----------|"
        )
        for test in tests:
            meta = metadata_for(test.test_id)
            verifies = meta.verifies if meta else test.description
            parts.append(
                f"| `{test.test_id}` | {test.name} | {verifies[:80]}{'…' if len(verifies) > 80 else ''} | "
                f"{_env_label(test)} | {'yes' if test.slow else 'no'} | {_run_hint(test)} |"
            )
        parts.append("")

        for test in tests:
            meta = metadata_for(test.test_id)
            parts.append(f"### `{test.test_id}` — {test.name}")
            parts.append("")
            parts.append(f"- **Category:** {test.category}")
            parts.append(f"- **Summary:** {test.description}")
            if meta:
                parts.append(f"- **Component:** {meta.component}")
                parts.append(f"- **Verifies:** {meta.verifies}")
                parts.append(f"- **Expected:** {meta.expected}")
            if test.requires_env:
                parts.append(f"- **Required env:** {', '.join(test.requires_env)}")
            if test.slow:
                parts.append("- **Slow:** yes (use `--slow` or `--integration`)")
            parts.append(f"- **Typical run:** {_run_hint(test)}")
            parts.append("")

    text = "\n".join(parts).strip() + "\n"
    output_path.write_text(text, encoding="utf-8")

    if also_write_docs:
        DOCS_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOCS_CATALOG_PATH.write_text(text, encoding="utf-8")

    return output_path
