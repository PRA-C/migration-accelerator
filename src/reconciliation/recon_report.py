"""Generate a single markdown reconciliation report with detailed pass/fail analysis."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from reconciliation.compare_results import CompareResult

load_dotenv()

RECON_REPORT_PATH = Path("reconciliation/reconciliation_report.md")

RECON_ANALYST_SYSTEM = (
    "You are a senior data engineer analyzing SQL migration reconciliation results. "
    "Teradata is the source; BigQuery is the target. Explain mismatches by linking "
    "observed column differences to likely SQL semantic or dialect gaps. "
    "Be specific, practical, and concise. Output markdown only."
)

_RULE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (
        ("product_id", "price_delta", "match_quality"),
        "Non-deterministic tie-breaking when multiple products match an order price band "
        "(ROW_NUMBER without a stable secondary ORDER BY). Teradata and BigQuery can pick "
        "different rows when `price_delta` ties.",
    ),
    (
        ("pct_of_total_revenue",),
        "Percentage-of-total revenue differs because Teradata uses nested window aggregation "
        "(`SUM(SUM(...)) OVER ()`) while BigQuery uses `SAFE_DIVIDE` — rounding and "
        "aggregation order can diverge slightly.",
    ),
    (
        ("rolling_3mo_revenue",),
        "Rolling 3-month average differs because the BigQuery rewrite computes the window "
        "over pre-aggregated monthly revenue, while Teradata applies the window in the "
        "same grouped query — frame boundaries and ordering are not equivalent.",
    ),
    (
        ("conversion_rate_pct", "repeat_rate_pct"),
        "Rate percentages differ only at floating-point precision after CAST/NUMERIC "
        "conversion between engines.",
    ),
    (
        ("(schema)",),
        "Result schemas differ — column names or column counts do not match between "
        "source and target exports.",
    ),
    (
        ("(keys)",),
        "Rows could not be aligned on inferred business keys — key sets differ between "
        "source and target result sets.",
    ),
]


def _rule_based_analysis(result: CompareResult, source_sql: str, target_sql: str) -> str:
    """Build a deterministic explanation when LLM is unavailable."""
    lines: list[str] = []
    if result.passed:
        lines.append(
            f"All {result.source_rows} rows and columns match within tolerance. "
            "The migrated BigQuery SQL appears semantically equivalent to the Teradata source "
            "for this dataset."
        )
        return "\n".join(lines)

    if not result.row_counts_match:
        lines.append(
            f"Row counts differ (source={result.source_rows}, target={result.target_rows}). "
            "This usually indicates missing filters, different join cardinality, or rows dropped "
            "by dialect-specific syntax (e.g. QUALIFY, NULL handling)."
        )
        return "\n".join(lines)

    if not result.columns_match:
        lines.append(
            "The source and target result schemas differ. Verify SELECT aliases, column order, "
            "and that both queries project the same expressions."
        )
        return "\n".join(lines)

    mismatch_cols = {diff.column for diff in result.column_diffs}
    for keys, explanation in _RULE_HINTS:
        if mismatch_cols & set(keys):
            lines.append(explanation)

    if not lines and result.column_diffs:
        lines.append(
            "Column-level mismatches were detected but do not match a known pattern. "
            "Review the source vs generated SQL for differences in joins, filters, "
            "aggregations, or window specifications."
        )

    if result.column_diffs:
        lines.append("\n**Affected columns:**")
        for diff in result.column_diffs:
            detail = f"- `{diff.column}`: {diff.mismatch_count} row(s) differ"
            if diff.max_numeric_diff is not None:
                detail += f" (max numeric delta: {diff.max_numeric_diff:.6g})"
            if diff.sample_mismatch:
                detail += f" — sample: {diff.sample_mismatch}"
            lines.append(detail)

    if source_sql.strip() and target_sql.strip():
        lines.append(
            "\n**Review focus:** Compare window functions, tie-break ORDER BY columns, "
            "date arithmetic, and percentage/division expressions between the SQL blocks below."
        )

    return "\n".join(lines)


def _truncate_sql(sql: str, limit: int = 2500) -> str:
    text = sql.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n-- ... truncated ..."


def _llm_analysis(payload: list[dict]) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from accelarator.llm import ask_claude

        prompt = (
            "Analyze these migration reconciliation results.\n\n"
            "For each **failed** run, provide a `### Run <id>: <file>` subsection with:\n"
            "1. **Verdict** (one line)\n"
            "2. **Root cause** — connect column mismatches to SQL/dialect differences\n"
            "3. **Severity** — critical / moderate / minor\n"
            "4. **Recommended fix** — concrete SQL changes for BigQuery or Teradata\n\n"
            "For each **passed** run, provide a `### Run <id>: <file>` subsection with one "
            "sentence confirming equivalence.\n\n"
            "Do not invent row counts. Use only the facts provided.\n\n"
            f"```json\n{json.dumps(payload, indent=2)}\n```"
        )
        return ask_claude(prompt=prompt, system=RECON_ANALYST_SYSTEM, max_tokens=4096)
    except Exception:
        return None


def _build_run_payload(
    result: CompareResult,
    *,
    source_sql: str,
    target_sql: str,
) -> dict:
    return {
        "run_id": result.run_id,
        "source_file": result.source_file,
        "passed": result.passed,
        "source_rows": result.source_rows,
        "target_rows": result.target_rows,
        "columns_match": result.columns_match,
        "row_counts_match": result.row_counts_match,
        "column_diffs": [diff.__dict__ for diff in result.column_diffs],
        "source_sql_excerpt": _truncate_sql(source_sql),
        "target_sql_excerpt": _truncate_sql(target_sql),
    }


def _executive_summary(results: list[CompareResult]) -> str:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    lines = [
        f"- **Total runs compared:** {len(results)}",
        f"- **Passed:** {passed}",
        f"- **Failed:** {failed}",
        "",
        "| Run | SQL file | Status | Source rows | Target rows |",
        "|-----|----------|--------|-------------|-------------|",
    ]
    for result in sorted(results, key=lambda r: r.run_id):
        status = "PASSED" if result.passed else "FAILED"
        label = result.source_file or f"run {result.run_id}"
        lines.append(
            f"| {result.run_id} | {label} | {status} | "
            f"{result.source_rows} | {result.target_rows} |"
        )
    return "\n".join(lines)


def generate_reconciliation_report(
    results: list[CompareResult],
    *,
    use_llm: bool = True,
    output_path: Path | None = None,
) -> Path:
    """Write a single markdown reconciliation report and return its path."""
    from accelarator.metadata import get_migration_run

    output_path = output_path or RECON_REPORT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payloads: list[dict] = []
    rule_sections: list[str] = []

    for result in sorted(results, key=lambda r: r.run_id):
        run = get_migration_run(result.run_id) or {}
        source_sql = run.get("source_code") or ""
        target_sql = run.get("generated_code") or ""
        payloads.append(
            _build_run_payload(result, source_sql=source_sql, target_sql=target_sql)
        )
        label = result.source_file or f"run {result.run_id}"
        status = "PASSED" if result.passed else "FAILED"
        rule_sections.append(f"### Run {result.run_id}: {label}\n")
        rule_sections.append(f"**Status:** {status}  ")
        rule_sections.append(
            f"**Rows:** source={result.source_rows}, target={result.target_rows}  "
        )
        rule_sections.append("")
        rule_sections.append(_rule_based_analysis(result, source_sql, target_sql))
        rule_sections.append("")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    parts = [
        "# Migration Reconciliation Report",
        "",
        f"**Generated:** {generated_at}  ",
        "**Pipeline:** Teradata (source) → BigQuery (target)  ",
        "",
        "## Executive Summary",
        "",
        _executive_summary(results),
        "",
        "## Detailed Analysis",
        "",
    ]

    llm_section: str | None = None
    if use_llm:
        llm_section = _llm_analysis(payloads)

    if llm_section:
        parts.append(llm_section.strip())
        parts.append("")
        parts.append("## Rule-Based Reference Notes")
        parts.append("")
        parts.append(
            "_Deterministic notes from the comparison engine (column diffs and known patterns)._"
        )
        parts.append("")
        parts.extend(rule_sections)
    else:
        parts.extend(rule_sections)

    parts.extend(
        [
            "## SQL Appendix",
            "",
            "_Excerpts of source (Teradata) and generated (BigQuery) SQL per run._",
            "",
        ]
    )
    for item in payloads:
        parts.append(f"### Run {item['run_id']}: {item.get('source_file') or 'unknown'}")
        parts.append("")
        parts.append("**Teradata source SQL**")
        parts.append("")
        parts.append("```sql")
        parts.append(item["source_sql_excerpt"])
        parts.append("```")
        parts.append("")
        parts.append("**BigQuery target SQL**")
        parts.append("")
        parts.append("```sql")
        parts.append(item["target_sql_excerpt"])
        parts.append("```")
        parts.append("")

    output_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    return output_path
