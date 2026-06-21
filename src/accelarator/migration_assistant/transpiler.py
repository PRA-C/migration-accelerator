"""LLM-powered code transpilation for migration requests."""

import re
import time

from accelarator.llm import (
    DATA_ENGINEER_SYSTEM,
    MAX_MIGRATION_ATTEMPTS,
    ValidationResult,
    ask_claude,
    validate_migration_output,
)

from .io_handlers import (
    MigrationRequest,
    MigrationResponse,
    OutputFormat,
    TARGET_MIGRATION_DIR,
    create_error_response,
    create_success_response,
    target_migration_filename,
    write_target_migration_file,
)
from accelarator.metadata import log_migration_result

OUTPUT_FORMAT_INSTRUCTIONS = {
    OutputFormat.TARGET_SQL_ONLY: (
        "Return plain SQL statements only (SELECT, INSERT, UPDATE, DELETE, MERGE, CTEs). "
        "Do NOT output stored procedures, functions, triggers, or any procedural code "
        "(no CREATE PROCEDURE, no CREATE FUNCTION, no BEGIN/END blocks, no PL/pgSQL, no PL/SQL). "
        "If the source is a stored procedure or script, rewrite the equivalent business logic "
        "as declarative SQL that can run directly on the target platform."
    ),
    OutputFormat.PYTHON_CONNECTOR: (
        "Return a complete, runnable Python script using the appropriate "
        "connector library for the target database."
    ),
    OutputFormat.PYSPARK: (
        "Return complete PySpark code using pyspark.sql APIs. "
        "Include a SparkSession setup if needed."
    ),
    OutputFormat.DBT: (
        "Return a dbt model SQL file with a brief config/docs header block."
    ),
    OutputFormat.EXECUTE_DIRECT: (
        "Return SQL ready to execute directly on the target database."
    ),
}

PROCEDURAL_OUTPUT_MARKERS = (
    "CREATE PROCEDURE", "CREATE OR REPLACE PROCEDURE",
    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION",
    "REPLACE PROCEDURE", "LANGUAGE PLPGSQL", "AS $$",
)


def _is_procedural_output(code: str) -> bool:
    upper = code.upper()
    if any(marker in upper for marker in PROCEDURAL_OUTPUT_MARKERS):
        return True
    if "BEGIN" in upper and "DECLARE" in upper:
        return True
    return False


def _check_output_format(code: str, output_format: OutputFormat) -> ValidationResult | None:
    """Hard rule: target_sql must not contain procedural code."""
    if output_format != OutputFormat.TARGET_SQL_ONLY:
        return None
    if _is_procedural_output(code):
        return ValidationResult(
            passed=False,
            feedback="Output must be plain SQL only, not a stored procedure or function.",
            issues=[
                "Generated code contains CREATE PROCEDURE / BEGIN / DECLARE blocks.",
                "Rewrite as declarative SQL (SELECT, INSERT, CTEs) with no procedural wrapper.",
            ],
        )
    return None


def _extract_code(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
    text = text.strip()
    fence_match = re.match(r"^```[\w]*\n(.*)\n```$", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return text


def _build_system_prompt(request: MigrationRequest) -> str:
    format_instruction = OUTPUT_FORMAT_INSTRUCTIONS[request.output_format]
    return (
        f"{DATA_ENGINEER_SYSTEM} Convert source code faithfully to the target platform. "
        f"{format_instruction} "
        "Return only code with no markdown fences and no explanatory prose."
    )


def _is_procedural_source(code: str) -> bool:
    """Heuristic check for stored procedures / procedural SQL."""
    upper = code.upper()
    markers = (
        "PROCEDURE", "FUNCTION", "BEGIN", "END", "DECLARE",
        "EXIT HANDLER", "LANGUAGE PLPGSQL", "AS $$",
    )
    return any(marker in upper for marker in markers)


def _build_user_prompt(
    request: MigrationRequest,
    revision_feedback: str = "",
) -> str:
    artifact_name = request.table_name or "migration"
    lines = [
        f"Migrate the following code from {request.source.value} to {request.target.value}.",
        f"Output format: {request.output_format.value}",
        f"Target artifact name: {artifact_name}",
    ]

    if (
        request.output_format == OutputFormat.TARGET_SQL_ONLY
        and _is_procedural_source(request.code)
    ):
        lines.append(
            "IMPORTANT: The source is a stored procedure. Do NOT translate it to another procedure. "
            "Decompose the logic into plain declarative SQL only — use CTEs, INSERT...SELECT, "
            "and conditional expressions (CASE WHEN). No CREATE PROCEDURE, no BEGIN/END, no DECLARE."
        )

    if revision_feedback:
        lines.extend([
            "",
            "PREVIOUS ATTEMPT FAILED DATA MANAGER VALIDATION. Fix these issues:",
            revision_feedback,
        ])

    lines.extend(["", "--- SOURCE CODE ---", request.code, "--- END SOURCE CODE ---"])
    return "\n".join(lines)


def _format_validation_feedback(validation: ValidationResult) -> str:
    parts = [validation.feedback] if validation.feedback else []
    if validation.issues:
        parts.append("Issues:\n" + "\n".join(f"- {issue}" for issue in validation.issues))
    return "\n".join(parts)


def _generate_code(request: MigrationRequest, revision_feedback: str = "") -> str:
    generated = ask_claude(
        prompt=_build_user_prompt(request, revision_feedback),
        system=_build_system_prompt(request),
        max_tokens=8192,
    )
    return _extract_code(generated)


def transpile_request(request: MigrationRequest) -> MigrationResponse:
    """Transpile via data engineer, validate via data manager, retry if needed."""
    start = time.time()

    try:
        code = ""
        validation = None
        revision_feedback = ""

        for attempt in range(1, MAX_MIGRATION_ATTEMPTS + 1):
            code = _generate_code(request, revision_feedback)

            if not code.strip():
                response = create_error_response(
                    request.request_id,
                    "LLM returned empty output",
                    "EmptyResponse",
                )
                response.processing_time_ms = (time.time() - start) * 1000
                log_migration_result(request, response)
                return response

            format_check = _check_output_format(code, request.output_format)
            if format_check and not format_check.passed:
                validation = format_check
            else:
                validation = validate_migration_output(
                    source_code=request.code,
                    generated_code=code,
                    source_db=request.source.value,
                    target_db=request.target.value,
                    output_format=request.output_format.value,
                )

            if validation.passed:
                break

            revision_feedback = _format_validation_feedback(validation)
            if attempt < MAX_MIGRATION_ATTEMPTS:
                continue

        if not validation or not validation.passed:
            response = create_error_response(
                request.request_id,
                validation.feedback if validation else "Validation failed",
                "ValidationError",
            )
            response.transpilation.generated_code = code
            response.transpilation.code_length_original = len(request.code)
            response.transpilation.code_length_generated = len(code)
            response.transpilation.validation_passed = False
            response.transpilation.validation_feedback = validation.feedback if validation else None
            for issue in (validation.issues if validation else []):
                response.add_warning(issue)
            response.processing_time_ms = (time.time() - start) * 1000
            log_migration_result(request, response)
            return response

        response = create_success_response(
            request.request_id,
            code,
            request.source.value,
            request.target.value,
        )
        response.transpilation.code_length_original = len(request.code)
        response.transpilation.validation_passed = validation.passed if validation else False
        response.transpilation.validation_feedback = validation.feedback if validation else None

        if validation and validation.passed:
            response.add_message("Data manager validation passed")

        output_name = target_migration_filename(
            request.source_filename,
            request.output_format,
        )
        output_path = write_target_migration_file(output_name, code)
        response.generated_files[output_name] = output_path
        response.add_message(f"Saved migrated output to {TARGET_MIGRATION_DIR}/{output_name}")
        response.processing_time_ms = (time.time() - start) * 1000
        log_migration_result(request, response)
        return response

    except Exception as exc:
        response = create_error_response(
            request.request_id,
            str(exc),
            type(exc).__name__,
        )
        response.processing_time_ms = (time.time() - start) * 1000
        log_migration_result(request, response)
        return response
