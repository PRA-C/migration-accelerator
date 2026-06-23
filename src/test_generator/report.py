"""Markdown regression report generation with optional LLM analysis."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .runner import SuiteResult, TestOutcome

load_dotenv()

TEST_RESULTS_DIR = Path("test_results")
REPORT_PATH = TEST_RESULTS_DIR / "regression_report.md"

REGRESSION_ANALYST_SYSTEM = (
    "You are a QA engineer reviewing a migration accelerator regression test run. "
    "Summarize failures, group by root cause, and suggest concrete fixes. "
    "Output markdown only."
)


def _llm_failure_analysis(result: SuiteResult) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

    failures = [o for o in result.outcomes if o.status == "failed"]
    if not failures:
        return None

    try:
        from accelarator.llm import ask_claude

        payload = [
            {
                "test_id": o.test_id,
                "name": o.name,
                "category": o.category,
                "description": o.description,
                "message": o.message,
                "error_tail": o.error.splitlines()[-8:] if o.error else [],
            }
            for o in failures
        ]
        prompt = (
            "Analyze these regression test failures for a SQL migration accelerator "
            "(Teradata source, BigQuery target, DuckDB metadata, reconciliation tooling).\n\n"
            "Provide:\n"
            "1. **Failure summary** (bullet list)\n"
            "2. **Likely root causes** grouped by theme\n"
            "3. **Recommended fixes** (actionable, ordered by priority)\n\n"
            f"```json\n{json.dumps(payload, indent=2)}\n```"
        )
        return ask_claude(prompt=prompt, system=REGRESSION_ANALYST_SYSTEM, max_tokens=3000)
    except Exception:
        return None


def _status_badge(status: str) -> str:
    return {"passed": "PASSED", "failed": "FAILED", "skipped": "SKIPPED"}.get(status, status.upper())


def _format_outcome(outcome: TestOutcome) -> list[str]:
    status = _status_badge(outcome.status)
    lines = [
        f"### {outcome.test_id}: {outcome.name}",
        "",
        f"**Status:** {status} &nbsp;|&nbsp; **Category:** {outcome.category} &nbsp;|&nbsp; "
        f"**Duration:** {outcome.duration_ms:.1f} ms",
        "",
        f"**Summary:** {outcome.description}",
        "",
    ]

    if outcome.component:
        lines.extend(["**Component under test:**", "", outcome.component, ""])
    if outcome.verifies:
        lines.extend(["**What this guards:**", "", outcome.verifies, ""])
    if outcome.steps:
        lines.extend(["**Steps executed:**", ""])
        for step in outcome.steps.split("\n"):
            step = step.strip()
            if step:
                lines.append(step)
        lines.append("")
    if outcome.expected:
        lines.extend(["**Expected result:**", "", outcome.expected, ""])

    if outcome.status == "passed":
        lines.extend(["**Actual result:**", "", outcome.message])
        if outcome.pass_notes:
            for note in outcome.pass_notes:
                lines.append(f"- {note}")
        lines.append("")
    elif outcome.status == "skipped":
        lines.extend(
            [
                "**Actual result:** Skipped — not executed in this run.",
                "",
                f"**Why skipped:** {outcome.skip_reason}",
                "",
                "**To include this test:** "
                + (
                    "`uv run python -m test_generator --integration --slow`"
                    if outcome.category == "integration"
                    else "`uv run python -m test_generator --slow`"
                ),
                "",
            ]
        )
    elif outcome.status == "failed":
        lines.extend(["**Actual result:** Failed", "", f"**Failure message:** `{outcome.message}`", ""])
        if outcome.error:
            lines.append("<details><summary>Full stack trace</summary>")
            lines.append("")
            lines.append("```text")
            lines.append(outcome.error.strip())
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    lines.append("---")
    lines.append("")
    return lines


def generate_regression_report(
    result: SuiteResult,
    *,
    use_llm: bool = True,
    output_path: Path | None = None,
) -> Path:
    """Write markdown regression report and return output path."""
    output_path = output_path or REPORT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    parts = [
        "# Regression Test Report",
        "",
        f"**Generated:** {generated}  ",
        f"**Duration:** {result.duration_ms:.0f} ms  ",
        "",
        "## Summary",
        "",
        f"- **Total:** {len(result.outcomes)}",
        f"- **Passed:** {result.passed}",
        f"- **Failed:** {result.failed}",
        f"- **Skipped:** {result.skipped}",
        "",
        "| Test ID | Name | Category | Status | Duration (ms) |",
        "|---------|------|----------|--------|---------------|",
    ]

    for outcome in result.outcomes:
        parts.append(
            f"| {outcome.test_id} | {outcome.name} | {outcome.category} | "
            f"{_status_badge(outcome.status)} | {outcome.duration_ms:.1f} |"
        )

    parts.extend(["", "## Results by Category", ""])

    for category in ("unit", "assets", "integration"):
        cat_outcomes = [o for o in result.outcomes if o.category == category]
        if not cat_outcomes:
            continue
        parts.append(f"### {category.title()}")
        parts.append("")
        for outcome in cat_outcomes:
            parts.extend(_format_outcome(outcome))

    failed = [o for o in result.outcomes if o.status == "failed"]
    if failed:
        parts.extend(["## Failure Analysis", ""])
        llm_text = _llm_failure_analysis(result) if use_llm else None
        if llm_text:
            parts.append(llm_text.strip())
            parts.append("")
        else:
            parts.append(
                "_LLM analysis unavailable — set `ANTHROPIC_API_KEY` or see per-test "
                "stack traces above._"
            )
            parts.append("")
            for outcome in failed:
                parts.append(f"- **{outcome.test_id}** `{outcome.name}`: {outcome.message}")
            parts.append("")

    parts.extend(
        [
            "## Run Configuration",
            "",
            f"- Started: `{result.started_at}`",
            f"- Finished: `{result.finished_at}`",
            "",
            "Re-run:",
            "",
            "```powershell",
            "uv run python -m test_generator",
            "uv run python -m test_generator --integration --slow",
            "```",
            "",
        ]
    )

    output_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    return output_path
