"""
Compare exported source vs target reconciliation CSVs and record results in metadata.

Writes a markdown report to reconciliation/reconciliation_report.md and optional
machine-readable summary to reconciliation/comparison_results/summary.json.

Usage:
    uv run python -m reconciliation.compare_results
    uv run python -m reconciliation.compare_results --run-ids 1,3
    uv run python -m reconciliation.compare_results --no-llm
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from accelarator.metadata import (
    get_migration_run,
    init_metadata_db,
    list_migration_runs,
    update_run_recon_metadata,
)
from reconciliation.recon_report import RECON_REPORT_PATH, generate_reconciliation_report
from reconciliation.result_exporter import RECON_SOURCE_RESULTS_DIR, RECON_TARGET_RESULTS_DIR

RECON_COMPARISON_RESULTS_DIR = Path("reconciliation/comparison_results")
DEFAULT_NUMERIC_RTOL = 1e-4
DEFAULT_NUMERIC_ATOL = 1e-4

_MEASURE_HINTS = (
    "revenue",
    "spend",
    "amount",
    "count",
    "orders",
    "customers",
    "pct",
    "rate",
    "avg",
    "average",
    "rank",
    "percentile",
    "delta",
    "converted",
    "repeat",
    "buyers",
    "quality",
    "tenure",
)


def _is_measure_column(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in _MEASURE_HINTS)


def _infer_merge_keys(
    columns: list[str],
    source: pd.DataFrame,
    target: pd.DataFrame,
) -> list[str] | None:
    """Infer row identity columns for key-based comparison."""
    candidates: list[list[str]] = []
    if "order_id" in columns:
        candidates.append(["order_id"])

    non_measure = [c for c in columns if not _is_measure_column(c)]
    if non_measure and len(non_measure) < len(columns):
        candidates.append(non_measure)

    for keys in candidates:
        if not all(key in source.columns and key in target.columns for key in keys):
            continue
        if source[keys].duplicated().any() or target[keys].duplicated().any():
            continue
        return keys
    return None


def _looks_like_date_column(name: str) -> bool:
    lower = name.lower()
    return any(token in lower for token in ("date", "month", "cohort", "timestamp", "time"))


@dataclass
class ColumnDiff:
    column: str
    mismatch_count: int
    max_numeric_diff: float | None = None
    sample_mismatch: str | None = None


@dataclass
class CompareResult:
    run_id: int
    source_file: str | None
    passed: bool
    source_rows: int
    target_rows: int
    columns_match: bool
    row_counts_match: bool
    source_csv: str
    target_csv: str
    report_path: str
    message: str
    column_diffs: list[ColumnDiff] = field(default_factory=list)
    compared_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


def _csv_paths(run_id: int) -> tuple[Path, Path]:
    return (
        RECON_SOURCE_RESULTS_DIR / str(run_id) / "query_result.csv",
        RECON_TARGET_RESULTS_DIR / str(run_id) / "query_result.csv",
    )


def _normalize_series(series: pd.Series, column_name: str) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    if _looks_like_date_column(column_name):
        parsed = pd.to_datetime(series, errors="coerce", utc=False)
        if parsed.notna().any():
            return parsed.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

    return (
        series.astype("string")
        .str.strip()
        .replace({"<NA>": "", "nan": "", "None": ""})
        .fillna("")
    )


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {col: _normalize_series(frame[col], col) for col in frame.columns}
    )


def _align_frames(source: pd.DataFrame, target: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Align rows by natural keys when possible, otherwise sort all columns."""
    src = _normalize_frame(source)
    tgt = _normalize_frame(target)
    merge_keys = _infer_merge_keys(list(source.columns), source, target)
    if merge_keys:
        merged = src.merge(
            tgt,
            on=merge_keys,
            how="outer",
            suffixes=("_src", "_tgt"),
            indicator=True,
        )
        if (merged["_merge"] != "both").any():
            missing_src = int((merged["_merge"] == "right_only").sum())
            missing_tgt = int((merged["_merge"] == "left_only").sum())
            raise ValueError(
                f"Key alignment failed on {merge_keys}: "
                f"{missing_src} source-only rows, {missing_tgt} target-only rows"
            )

        value_columns = [c for c in source.columns if c not in merge_keys]
        src_aligned = pd.DataFrame({key: merged[key] for key in merge_keys})
        tgt_aligned = pd.DataFrame({key: merged[key] for key in merge_keys})
        for col in value_columns:
            src_aligned[col] = merged[f"{col}_src"]
            tgt_aligned[col] = merged[f"{col}_tgt"]
        return (
            src_aligned.sort_values(merge_keys, kind="mergesort").reset_index(drop=True),
            tgt_aligned.sort_values(merge_keys, kind="mergesort").reset_index(drop=True),
        )

    return _sorted_frame(src), _sorted_frame(tgt)


def _sorted_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    sort_cols = list(frame.columns)
    return frame.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)


def _string_series_equal(source: pd.Series, target: pd.Series) -> pd.Series:
    def _canonical(value: object) -> str:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return ""
        text = str(value).strip()
        return "" if text.lower() in {"", "nan", "none", "<na>"} else text

    src = source.map(_canonical)
    tgt = target.map(_canonical)
    return src == tgt


def _compare_column(
    source: pd.Series,
    target: pd.Series,
    *,
    rtol: float,
    atol: float,
) -> ColumnDiff | None:
    if pd.api.types.is_numeric_dtype(source) or pd.api.types.is_numeric_dtype(target):
        src_num = pd.to_numeric(source, errors="coerce")
        tgt_num = pd.to_numeric(target, errors="coerce")
        both_nan = src_num.isna() & tgt_num.isna()
        close = np.isclose(src_num, tgt_num, rtol=rtol, atol=atol, equal_nan=True)
        mismatch_mask = ~(close | both_nan)
        mismatch_count = int(mismatch_mask.sum())
        if mismatch_count == 0:
            return None
        diff = (src_num - tgt_num).abs()
        max_val = diff[mismatch_mask].max()
        max_diff = None if pd.isna(max_val) else float(max_val)
        idx = int(mismatch_mask.to_numpy().nonzero()[0][0])
        sample = f"row {idx}: source={src_num.iloc[idx]!r} target={tgt_num.iloc[idx]!r}"
        return ColumnDiff(
            column=str(source.name),
            mismatch_count=mismatch_count,
            max_numeric_diff=max_diff,
            sample_mismatch=sample,
        )

    src_str = source.astype(str)
    tgt_str = target.astype(str)
    mismatch_mask = ~_string_series_equal(source, target)
    mismatch_count = int(mismatch_mask.sum())
    if mismatch_count == 0:
        return None
    idx = int(mismatch_mask.to_numpy().nonzero()[0][0])
    sample = f"row {idx}: source={src_str.iloc[idx]!r} target={tgt_str.iloc[idx]!r}"
    return ColumnDiff(
        column=str(source.name),
        mismatch_count=mismatch_count,
        sample_mismatch=sample,
    )


def compare_dataframes(
    source: pd.DataFrame,
    target: pd.DataFrame,
    *,
    run_id: int = 0,
    source_file: str | None = None,
    source_csv: str = "",
    target_csv: str = "",
    rtol: float = DEFAULT_NUMERIC_RTOL,
    atol: float = DEFAULT_NUMERIC_ATOL,
) -> CompareResult:
    """Compare two result dataframes (used by run export and regression tests)."""
    source_rows = len(source)
    target_rows = len(target)
    row_counts_match = source_rows == target_rows
    columns_match = list(source.columns) == list(target.columns)

    column_diffs: list[ColumnDiff] = []
    if columns_match and row_counts_match:
        try:
            src_norm, tgt_norm = _align_frames(source, target)
        except ValueError as exc:
            column_diffs.append(
                ColumnDiff(
                    column="(keys)",
                    mismatch_count=1,
                    sample_mismatch=str(exc),
                )
            )
            src_norm = tgt_norm = pd.DataFrame()
        if not src_norm.empty:
            compare_columns = [c for c in source.columns if c in src_norm.columns]
            for col in compare_columns:
                diff = _compare_column(src_norm[col], tgt_norm[col], rtol=rtol, atol=atol)
                if diff is not None:
                    column_diffs.append(diff)
    elif not columns_match:
        column_diffs.append(
            ColumnDiff(
                column="(schema)",
                mismatch_count=1,
                sample_mismatch=(
                    f"source columns={list(source.columns)}; "
                    f"target columns={list(target.columns)}"
                ),
            )
        )

    passed = row_counts_match and columns_match and not column_diffs
    if passed:
        message = f"Reconciliation passed ({source_rows} rows, all columns match)"
    elif not row_counts_match:
        message = f"Row count mismatch: source={source_rows}, target={target_rows}"
    elif column_diffs:
        summary = ", ".join(
            f"{d.column} ({d.mismatch_count} mismatches)" for d in column_diffs[:3]
        )
        if len(column_diffs) > 3:
            summary += f", +{len(column_diffs) - 3} more"
        message = f"Data mismatch: {summary}"
    else:
        message = "Reconciliation failed"

    return CompareResult(
        run_id=run_id,
        source_file=source_file,
        passed=passed,
        source_rows=source_rows,
        target_rows=target_rows,
        columns_match=columns_match,
        row_counts_match=row_counts_match,
        source_csv=source_csv,
        target_csv=target_csv,
        report_path=str(RECON_REPORT_PATH),
        message=message,
        column_diffs=column_diffs,
    )


def compare_run_csvs(
    run_id: int,
    *,
    source_file: str | None = None,
    rtol: float = DEFAULT_NUMERIC_RTOL,
    atol: float = DEFAULT_NUMERIC_ATOL,
    write_json: bool = True,
) -> CompareResult:
    """Compare source and target CSV exports for one migration run."""
    source_path, target_path = _csv_paths(run_id)
    source_csv = str(source_path)
    target_csv = str(target_path)
    report_path = str(RECON_REPORT_PATH)

    if not source_path.exists() or not target_path.exists():
        message = "Missing source or target CSV — run reconciliation prep first"
        result = CompareResult(
            run_id=run_id,
            source_file=source_file,
            passed=False,
            source_rows=0,
            target_rows=0,
            columns_match=False,
            row_counts_match=False,
            source_csv=source_csv,
            target_csv=target_csv,
            report_path=report_path,
            message=message,
        )
        if write_json:
            _write_run_json(result)
        return result

    source = pd.read_csv(source_path)
    target = pd.read_csv(target_path)
    result = compare_dataframes(
        source,
        target,
        run_id=run_id,
        source_file=source_file,
        source_csv=source_csv,
        target_csv=target_csv,
        rtol=rtol,
        atol=atol,
    )
    if write_json:
        _write_run_json(result)
    return result


def _write_run_json(result: CompareResult) -> None:
    run_dir = RECON_COMPARISON_RESULTS_DIR / str(result.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_file = run_dir / "report.json"
    report_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def compare_runs(
    run_ids: list[int],
    *,
    rtol: float = DEFAULT_NUMERIC_RTOL,
    atol: float = DEFAULT_NUMERIC_ATOL,
    use_llm: bool = True,
    write_json: bool = False,
) -> list[CompareResult]:
    """Compare multiple runs, write markdown report, and update metadata."""
    results: list[CompareResult] = []
    for run_id in run_ids:
        run = get_migration_run(run_id)
        source_file = run.get("source_file") if run else None
        result = compare_run_csvs(
            run_id,
            source_file=source_file,
            rtol=rtol,
            atol=atol,
            write_json=write_json,
        )
        results.append(result)

    report_path = generate_reconciliation_report(results, use_llm=use_llm)
    report_path_str = str(report_path)

    for result in results:
        update_run_recon_metadata(
            result.run_id,
            recon_ind="passed" if result.passed else "failed",
            recon_passed=result.passed,
            recon_result_path=report_path_str,
        )
        result.report_path = report_path_str

    if write_json:
        _write_summary(results, report_path_str)
    return results


def _write_summary(results: list[CompareResult], report_path: str) -> None:
    RECON_COMPARISON_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for r in results if r.passed)
    summary = {
        "compared_at": datetime.now().isoformat(),
        "report_path": report_path,
        "total_runs": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "runs": [result.to_dict() for result in results],
    }
    summary_path = RECON_COMPARISON_RESULTS_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _parse_run_ids(raw: str, runs: list[dict]) -> list[int]:
    valid = {int(r["run_id"]) for r in runs}
    selected: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            for i in range(int(start_s), int(end_s) + 1):
                if i in valid:
                    selected.append(i)
        elif part.isdigit():
            val = int(part)
            if val in valid:
                selected.append(val)
    return sorted(set(selected))


def _runs_with_exports(runs: list[dict]) -> list[int]:
    ready: list[int] = []
    for run in runs:
        run_id = int(run["run_id"])
        source_path, target_path = _csv_paths(run_id)
        if source_path.exists() and target_path.exists():
            ready.append(run_id)
    return sorted(ready)


def _print_results(results: list[CompareResult]) -> None:
    print("\n" + "=" * 100)
    print("RECONCILIATION COMPARISON")
    print("=" * 100)
    for result in results:
        status = "PASSED" if result.passed else "FAILED"
        label = result.source_file or f"run {result.run_id}"
        print(
            f"  [{result.run_id:>4}] {label:<32} {status:<6} "
            f"rows={result.source_rows}/{result.target_rows}"
        )
        if not result.passed:
            print(f"         {result.message}")
    passed = sum(1 for r in results if r.passed)
    print("=" * 100)
    print(
        f"Summary: {passed}/{len(results)} passed | "
        f"report → {RECON_REPORT_PATH}"
    )
    print("=" * 100)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare reconciliation CSV exports")
    parser.add_argument(
        "--run-ids",
        help="Comma-separated run ids or ranges (e.g. 1,3,5-6). Default: all runs with CSV exports.",
    )
    parser.add_argument(
        "--prepared-only",
        action="store_true",
        help="Only compare runs whose recon_ind is 'prepared'",
    )
    parser.add_argument("--rtol", type=float, default=DEFAULT_NUMERIC_RTOL)
    parser.add_argument("--atol", type=float, default=DEFAULT_NUMERIC_ATOL)
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM narrative in the markdown report (rule-based analysis only)",
    )
    parser.add_argument(
        "--write-json",
        action="store_true",
        help="Also write per-run JSON and summary.json under comparison_results/",
    )
    args = parser.parse_args(argv)

    init_metadata_db()
    runs = list_migration_runs()

    if args.run_ids:
        run_ids = _parse_run_ids(args.run_ids, runs)
    elif args.prepared_only:
        run_ids = sorted(
            int(r["run_id"])
            for r in runs
            if r.get("recon_ind") == "prepared"
        )
    else:
        run_ids = _runs_with_exports(runs)

    if not run_ids:
        print("No runs selected for comparison.")
        return 1

    results = compare_runs(
        run_ids,
        rtol=args.rtol,
        atol=args.atol,
        use_llm=not args.no_llm,
        write_json=args.write_json,
    )
    _print_results(results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
