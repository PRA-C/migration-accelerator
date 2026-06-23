"""
Generate migration documentation and data lineage under documentation/.

Usage:
    uv run python -m documentation
    uv run python -m documentation --no-llm
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from documentation.generator import DOCS_ROOT, generate_documentation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate migration docs and lineage")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM executive summary in migration_overview.md",
    )
    args = parser.parse_args(argv)

    root = generate_documentation(use_llm=not args.no_llm)
    print(f"Documentation generated under {root}/")
    print(f"  Index:    {root / 'README.md'}")
    print(f"  Overview: {root / 'migration_overview.md'}")
    print(f"  Lineage:  {root / 'lineage.md'}")
    print(f"  JSON:     {root / 'lineage.json'}")
    print(f"  Runs:     {root / 'migrations'}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
