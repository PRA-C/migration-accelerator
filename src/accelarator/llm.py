import json
import os
import re
from dataclasses import dataclass, field

from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

DATA_ENGINEER_SYSTEM = (
    "You are an expert data engineer specializing in database migration and code transpilation."
)
DATA_MANAGER_SYSTEM = (
    "You are a senior data manager reviewing migration output from a data engineer. "
    "Verify semantic equivalence, correct target dialect syntax, output format compliance, "
    "and that no business logic was dropped or altered incorrectly."
)

MAX_MIGRATION_ATTEMPTS = 3


@dataclass
class ValidationResult:
    passed: bool
    feedback: str
    issues: list[str] = field(default_factory=list)


def ask_claude(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=max_tokens,
        system=system or DATA_ENGINEER_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    return json.loads(text)


def validate_migration_output(
    source_code: str,
    generated_code: str,
    source_db: str,
    target_db: str,
    output_format: str,
) -> ValidationResult:
    """Data manager review of data engineer migration output."""
    prompt = (
        f"Review the data engineer's migration output.\n\n"
        f"Source database: {source_db}\n"
        f"Target database: {target_db}\n"
        f"Output format: {output_format}\n\n"
        f"--- SOURCE CODE ---\n{source_code}\n--- END SOURCE ---\n\n"
        f"--- GENERATED CODE ---\n{generated_code}\n--- END GENERATED ---\n\n"
        "Check:\n"
        "1. Semantic equivalence (same business logic and query results)\n"
        "2. Correct target dialect syntax and functions\n"
        "3. Output format rules followed (e.g. plain SQL only when required)\n"
        "4. No missing filters, joins, columns, window specs, or transformations\n"
    )

    if output_format == "target_sql":
        prompt += (
            "\nSTRICT RULE for target_sql format:\n"
            "- FAIL if output contains CREATE PROCEDURE, CREATE FUNCTION, "
            "BEGIN/END blocks, DECLARE, or any procedural code.\n"
            "- PASS only if output is plain declarative SQL (SELECT, INSERT, UPDATE, CTEs).\n"
        )

    prompt += (
        "\nRespond with JSON only:\n"
        '{"passed": true|false, "feedback": "brief summary", "issues": ["issue1", ...]}'
    )

    raw = ask_claude(prompt=prompt, system=DATA_MANAGER_SYSTEM, max_tokens=2048)

    try:
        data = _parse_json_response(raw)
        return ValidationResult(
            passed=bool(data.get("passed", False)),
            feedback=str(data.get("feedback", "")),
            issues=[str(i) for i in data.get("issues", [])],
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return ValidationResult(
            passed=False,
            feedback="Validation response could not be parsed",
            issues=[raw[:500] if raw else "Empty validation response"],
        )
