"""Reconciliation utilities for migration source vs target validation."""

__all__ = ["compare_reconciliation_results", "compare_runs", "run_migration_recon"]


def compare_reconciliation_results():
    from .compare_results import main

    return main()


def compare_runs(*args, **kwargs):
    from .compare_results import compare_runs as _compare_runs

    return _compare_runs(*args, **kwargs)


def run_migration_recon():
    from .migration_recon import main

    return main()
