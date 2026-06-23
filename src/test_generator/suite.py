"""Regression test case definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class TestCase:
    test_id: str
    name: str
    category: str
    description: str
    fn: Callable[[], None]
    requires_env: tuple[str, ...] = ()
    slow: bool = False


_pass_notes: list[str] = []


def note_pass(detail: str) -> None:
    """Record an extra line in the report for the current passing test."""
    _pass_notes.append(detail.strip())


def consume_pass_notes() -> list[str]:
    notes = list(_pass_notes)
    _pass_notes.clear()
    return notes


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
