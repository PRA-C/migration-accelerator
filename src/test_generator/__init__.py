"""Regression test suite for the migration accelerator."""

from .catalog import CATALOG_PATH, generate_test_catalog
from .registry import REGRESSION_TESTS
from .runner import run_regression_suite
from .suite import TestCase

__all__ = [
    "CATALOG_PATH",
    "REGRESSION_TESTS",
    "TestCase",
    "generate_test_catalog",
    "run_regression_suite",
]
