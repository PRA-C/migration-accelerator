"""Execute regression tests and collect outcomes."""

from __future__ import annotations

import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime

from .registry import REGRESSION_TESTS
from .suite import TestCase, consume_pass_notes
from .test_metadata import TestMetadata, metadata_for


@dataclass
class TestOutcome:
    test_id: str
    name: str
    category: str
    description: str
    status: str  # passed | failed | skipped
    duration_ms: float
    message: str = ""
    error: str = ""
    skip_reason: str = ""
    component: str = ""
    verifies: str = ""
    steps: str = ""
    expected: str = ""
    pass_notes: list[str] = field(default_factory=list)


def _outcome_from_test(
    test: TestCase,
    *,
    status: str,
    duration_ms: float,
    message: str = "",
    error: str = "",
    skip_reason: str = "",
    pass_notes: list[str] | None = None,
) -> TestOutcome:
    meta: TestMetadata | None = metadata_for(test.test_id)
    return TestOutcome(
        test_id=test.test_id,
        name=test.name,
        category=test.category,
        description=test.description,
        status=status,
        duration_ms=duration_ms,
        message=message,
        error=error,
        skip_reason=skip_reason,
        component=meta.component if meta else "",
        verifies=meta.verifies if meta else "",
        steps=meta.steps if meta else "",
        expected=meta.expected if meta else "",
        pass_notes=pass_notes or [],
    )


@dataclass
class SuiteResult:
    started_at: str
    finished_at: str
    duration_ms: float
    outcomes: list[TestOutcome] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "skipped")


def _env_missing(vars_needed: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for var in vars_needed:
        primary = os.getenv(var, "").strip()
        if primary:
            continue
        if var.startswith("TD_"):
            fallback = os.getenv("TERADATA_" + var[3:], "").strip()
            if fallback:
                continue
        missing.append(var)
    return missing


def _should_skip(test: TestCase, *, include_integration: bool, include_slow: bool) -> str | None:
    if test.category == "integration" and not include_integration:
        return "integration tests disabled (use --integration)"
    if test.slow and not include_slow:
        return "slow tests disabled (use --slow)"
    missing = _env_missing(test.requires_env)
    if missing:
        return f"missing env: {', '.join(missing)}"
    return None


def run_regression_suite(
    *,
    include_integration: bool = False,
    include_slow: bool = False,
    test_ids: list[str] | None = None,
) -> SuiteResult:
    """Run all matching regression tests."""
    started = time.perf_counter()
    started_at = datetime.now().isoformat()
    outcomes: list[TestOutcome] = []

    tests = REGRESSION_TESTS
    if test_ids:
        allowed = set(test_ids)
        tests = [t for t in tests if t.test_id in allowed]

    for test in tests:
        skip_reason = _should_skip(
            test,
            include_integration=include_integration,
            include_slow=include_slow,
        )
        if skip_reason:
            outcomes.append(
                _outcome_from_test(
                    test,
                    status="skipped",
                    duration_ms=0.0,
                    skip_reason=skip_reason,
                )
            )
            continue

        consume_pass_notes()
        t0 = time.perf_counter()
        try:
            test.fn()
            duration = (time.perf_counter() - t0) * 1000
            notes = consume_pass_notes()
            outcomes.append(
                _outcome_from_test(
                    test,
                    status="passed",
                    duration_ms=duration,
                    message="All assertions passed.",
                    pass_notes=notes,
                )
            )
        except Exception as exc:
            duration = (time.perf_counter() - t0) * 1000
            consume_pass_notes()
            outcomes.append(
                _outcome_from_test(
                    test,
                    status="failed",
                    duration_ms=duration,
                    message=str(exc),
                    error=traceback.format_exc(),
                )
            )

    total_ms = (time.perf_counter() - started) * 1000
    return SuiteResult(
        started_at=started_at,
        finished_at=datetime.now().isoformat(),
        duration_ms=total_ms,
        outcomes=outcomes,
    )
