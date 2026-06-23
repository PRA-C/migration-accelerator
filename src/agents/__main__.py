"""
Run the full migration accelerator agent pipeline (LangGraph).

Agents execute sequentially:
  1. EnvironmentProvisioner
  2. MigrationIntake
  3. MigrationTranspiler (Data Engineer + Data Manager LLM loop)
  4. ReconPreparer
  5. ReconComparator + ReconAnalyst
  6. RegressionRunner + QAAnalyst
  7. DocumentationGenerator + DocWriter

Usage:
    uv run python -m agents
    uv run python -m agents --skip-provision --skip-migrate
    uv run python -m agents --no-llm
    uv run python -m agents --integration --slow
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from agents.registry import AGENT_PIPELINE
from agents.runner import PIPELINE_REPORT_PATH, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run migration accelerator agents sequentially via LangGraph"
    )
    parser.add_argument("--no-llm", action="store_true", help="Disable all LLM agents")
    parser.add_argument("--skip-provision", action="store_true", help="Skip schema provisioning")
    parser.add_argument("--skip-migrate", action="store_true", help="Skip migration transpilation")
    parser.add_argument("--skip-recon", action="store_true", help="Skip reconciliation prep/compare")
    parser.add_argument("--skip-tests", action="store_true", help="Skip regression tests")
    parser.add_argument("--skip-docs", action="store_true", help="Skip documentation generation")
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Include integration regression tests (implies --slow)",
    )
    parser.add_argument("--slow", action="store_true", help="Include slow regression tests")
    parser.add_argument("--list-agents", action="store_true", help="List pipeline agents and exit")
    args = parser.parse_args(argv)

    if args.list_agents:
        print("Migration accelerator agent pipeline (sequential):\n")
        for idx, spec in enumerate(AGENT_PIPELINE, start=1):
            llm = "LLM" if spec.uses_llm else "tool"
            print(f"  {idx}. [{llm:4}] {spec.name}")
            print(f"       {spec.description}")
            print(f"       wraps: {spec.wraps}\n")
        return 0

    final_state, report_path = run_pipeline(
        use_llm=not args.no_llm,
        skip_provision=args.skip_provision,
        skip_migrate=args.skip_migrate,
        skip_recon=args.skip_recon,
        skip_tests=args.skip_tests,
        skip_docs=args.skip_docs,
        include_integration_tests=args.integration,
        include_slow_tests=args.slow or args.integration,
    )

    print("\n" + "=" * 80)
    print("AGENT PIPELINE COMPLETE")
    print("=" * 80)
    for entry in final_state.get("agent_log", []):
        status = entry.get("status", "?").upper()
        agent = entry.get("agent", "?")
        msg = entry.get("message", "")
        ms = entry.get("duration_ms", 0)
        timing = f" ({ms:.0f} ms)" if ms else ""
        print(f"  [{status:7}] {agent:<24} {msg}{timing}")
    print("=" * 80)
    print(f"  Pipeline report → {report_path}")
    if final_state.get("recon_report_path"):
        print(f"  Recon report     → {final_state['recon_report_path']}")
    if final_state.get("regression_report_path"):
        print(f"  Regression report → {final_state['regression_report_path']}")
    if final_state.get("docs_path"):
        print(f"  Documentation    → {final_state['docs_path']}/")
    print("=" * 80)

    errors = final_state.get("errors", [])
    tests_failed = final_state.get("tests_failed") or 0
    compare_failed = final_state.get("compare_failed") or 0
    if errors or tests_failed or compare_failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
