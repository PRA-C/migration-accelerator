"""
SQL Migration Assistant - Interactive Translator (UPDATED)
File 2 of 2: Interactive UI and main flow
Place this at: src/accelerator/migration_assistant/translator.py
UPDATED: Direct source/target selection instead of preset patterns
"""

from typing import Optional, Tuple, List
import os
import io
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    from .io_handlers import (
        MigrationRequest, MigrationResponse, ExecutionStatus,
        SourceDatabase, TargetDatabase, OutputFormat, CodeType,
        SOURCE_MIGRATION_DIR, TARGET_MIGRATION_DIR,
        read_source_migration_files,
        target_migration_filename, derive_target_name_from_source, ensure_migration_dirs,
    )
    from .transpiler import transpile_request
    from accelarator.llm import MAX_MIGRATION_ATTEMPTS
    from accelarator.metadata import init_metadata_db, METADATA_DB_PATH
except Exception as exc:
    raise

def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f"🚀 {title}")
    print("=" * 80 + "\n")


def print_section(title: str):
    """Print section header"""
    print(f"\n📌 {title}:\n")


# ============ OUTPUT FORMATS ============

OUTPUT_FORMATS = {
    "1": {
        "name": "Target SQL Only",
        "key": OutputFormat.TARGET_SQL_ONLY,
        "description": "Just target SQL code"
    },
    "2": {
        "name": "Python + Connector",
        "key": OutputFormat.PYTHON_CONNECTOR,
        "description": "Python script with database connector"
    },
    "3": {
        "name": "PySpark",
        "key": OutputFormat.PYSPARK,
        "description": "PySpark DataFrame API code"
    },
    "4": {
        "name": "dbt Model",
        "key": OutputFormat.DBT,
        "description": "dbt SQL model with documentation"
    },
    "5": {
        "name": "Execute Directly",
        "key": OutputFormat.EXECUTE_DIRECT,
        "description": "Execute on target database immediately"
    },
}


# ============ INPUT HANDLERS ============

def select_source_database() -> SourceDatabase:
    """Let user select source database directly"""
    print_section("SELECT SOURCE DATABASE")
    
    source_options = {
        "1": SourceDatabase.TERADATA,
        "2": SourceDatabase.ORACLE,
        "3": SourceDatabase.SQL_SERVER,
        "4": SourceDatabase.NETEZZA,
        "5": SourceDatabase.POSTGRESQL,
        "6": SourceDatabase.MYSQL,
    }
    
    for key, db in source_options.items():
        print(f"{key}. {db.value.upper()}")
    
    while True:
        choice = input("\nSelect source (1-6): ").strip()
        if choice in source_options:
            return source_options[choice]
        print("❌ Invalid choice. Please select 1-6")


def select_target_database() -> TargetDatabase:
    """Let user select target database directly"""
    print_section("SELECT TARGET DATABASE")
    
    target_options = {
        "1": TargetDatabase.SNOWFLAKE,
        "2": TargetDatabase.REDSHIFT,
        "3": TargetDatabase.BIGQUERY,
        "4": TargetDatabase.AZURE_SYNAPSE,
        "5": TargetDatabase.SPARK,
        "6": TargetDatabase.POSTGRESQL,
    }
    
    for key, db in target_options.items():
        print(f"{key}. {db.value.upper()}")
    
    while True:
        choice = input("\nSelect target (1-6): ").strip()
        if choice in target_options:
            return target_options[choice]
        print("❌ Invalid choice. Please select 1-6")


def select_output_format() -> OutputFormat:
    """Let user select output format"""
    print_section("OUTPUT FORMAT")
    
    for key, fmt in OUTPUT_FORMATS.items():
        name = fmt["name"]
        desc = fmt["description"]
        print(f"{key}. {name:20} - {desc}")
    
    while True:
        choice = input("\nSelect format (1-5): ").strip()
        if choice in OUTPUT_FORMATS:
            break
        print("❌ Invalid choice. Please select 1-5")
    
    return OUTPUT_FORMATS[choice]["key"]


def select_code_input_method() -> str:
    """Choose whether to load SQL from a file or paste it manually."""
    print_section("SOURCE CODE INPUT")
    print(f"1. Load from folder: {SOURCE_MIGRATION_DIR}/")
    print("2. Paste SQL manually")
    
    while True:
        choice = input("\nSelect input method (1-2): ").strip()
        if choice in {"1", "2"}:
            return "file" if choice == "1" else "manual"
        print("❌ Invalid choice. Please select 1 or 2")


def _parse_file_selection(raw: str, max_index: int) -> List[int]:
    """Parse file selection: single (1), list (1,3,5), range (1-4), or all (A)."""
    raw = raw.strip().upper()
    if raw == "A":
        return list(range(1, max_index + 1))

    indices: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            if len(bounds) != 2 or not bounds[0].isdigit() or not bounds[1].isdigit():
                continue
            start, end = int(bounds[0]), int(bounds[1])
            if start > end:
                start, end = end, start
            for i in range(start, end + 1):
                if 1 <= i <= max_index:
                    indices.add(i)
        elif part.isdigit():
            i = int(part)
            if 1 <= i <= max_index:
                indices.add(i)

    return sorted(indices)


def select_source_files() -> List[Tuple[str, str]]:
    """Select one or more migration source files from the configured source folder."""
    source_files = read_source_migration_files()

    if not source_files:
        print(f"\n❌ No source files found in {SOURCE_MIGRATION_DIR}/")
        print("   Supported extensions: .sql, .proc, .txt")
        return []

    print_section(f"SELECT SOURCE FILE(S) ({SOURCE_MIGRATION_DIR}/)")
    filenames = list(source_files.keys())
    for index, filename in enumerate(filenames, start=1):
        print(f"{index}. {filename}")

    print(f"\n[A] All files")
    print("Examples: 1  |  1,3,5  |  1-4")

    while True:
        choice = input(
            f"\nSelect file(s) (1-{len(filenames)}, comma-separated, range, or A): "
        ).strip()
        selected_indices = _parse_file_selection(choice, len(filenames))

        if not selected_indices:
            print(f"❌ Invalid choice. Enter 1-{len(filenames)}, e.g. 1,3 or 1-4, or A")
            continue

        selected = [
            (filenames[i - 1], source_files[filenames[i - 1]])
            for i in selected_indices
        ]
        names = ", ".join(name for name, _ in selected)
        total_chars = sum(len(content) for _, content in selected)
        print(f"\n✓ Loaded {len(selected)} file(s): {names} ({total_chars} characters)")
        return selected


def get_sql_code() -> List[Tuple[Optional[str], str]]:
    """Get SQL/Procedure code from file(s) or manual input."""
    method = select_code_input_method()

    if method == "file":
        files = select_source_files()
        return [(name, content) for name, content in files]

    print_section("ENTER SQL OR STORED PROCEDURE")
    print("Type 'END' on a new line when done:\n")
    
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        except KeyboardInterrupt:
            print("\n❌ Input cancelled")
            return []
        except EOFError:
            break
    
    code = "\n".join(lines)
    
    if not code.strip():
        print("❌ No code provided")
        return []
    
    print(f"\n✓ Received {len(code)} characters")
    return [(None, code)]


def display_migration_requests(requests: List[MigrationRequest]):
    """Display migration request summary for one or more files."""
    
    print("\n" + "=" * 80)
    print("📋 MIGRATION REQUEST SUMMARY")
    print("=" * 80)
    
    first = requests[0]
    print(f"\n✓ Source: {first.source.value.upper()}")
    print(f"✓ Target: {first.target.value.upper()}")
    print(f"✓ Output Format: {first.output_format.value.upper()}")
    print(f"✓ Files to migrate: {len(requests)}")

    for request in requests:
        print(f"\n  • {request.source_filename or 'manual input'}")
        print(f"    Code length: {len(request.code)} characters")
        print(f"    Target name: {request.table_name}")
        output_name = target_migration_filename(request.source_filename, request.output_format)
        print(f"    Output: {TARGET_MIGRATION_DIR}/{output_name}")
    
    print("\n" + "=" * 80)


def display_migration_response(response: MigrationResponse):
    """Display migration response"""
    
    print("\n" + "=" * 80)
    print("📊 MIGRATION RESPONSE")
    print("=" * 80)
    
    status_emoji = "✓" if response.status == ExecutionStatus.SUCCESS else "✗"
    print(f"\n{status_emoji} Status: {response.status.value.upper()}")
    print(f"📌 Request ID: {response.request_id}")
    print(f"⏱️  Processing Time: {response.processing_time_ms:.2f}ms")
    
    print("\n📝 TRANSPILATION:")
    trans = response.transpilation
    print(f"  ├── Success: {'✓' if trans.success else '✗'}")
    print(f"  ├── Source: {trans.source_db}")
    print(f"  ├── Target: {trans.target_db}")
    print(f"  ├── Generated Code Length: {trans.code_length_generated} chars")
    print(f"  ├── Validation Passed: {'✓' if trans.validation_passed else '✗'}")
    
    if trans.error_message:
        print(f"  └── Error: {trans.error_message}")
    
    if trans.generated_code:
        print("\n🔧 GENERATED CODE PREVIEW:")
        print("─" * 80)
        code_preview = trans.generated_code[:500]
        if len(trans.generated_code) > 500:
            code_preview += "\n... [truncated]"
        print(code_preview)
        print("─" * 80)
    
    if response.execution:
        print("\n⚙️  EXECUTION:")
        exe = response.execution
        print(f"  ├── Status: {exe.status.value.upper()}")
        print(f"  ├── Query ID: {exe.query_id}")
        print(f"  ├── Rows Inserted: {exe.rows_inserted}")
        print(f"  ├── Rows Updated: {exe.rows_updated}")
        print(f"  ├── Execution Time: {exe.execution_time_ms:.2f}ms")
        print(f"  └── Data Quality: {'✓' if exe.data_quality_passed else '✗'}")
        
        if exe.error_message:
            print(f"  └── Error: {exe.error_message}")
    
    if response.messages:
        print("\n💬 MESSAGES:")
        for msg in response.messages:
            print(f"  ✓ {msg}")
    
    if response.warnings:
        print("\n⚠️  WARNINGS:")
        for warn in response.warnings:
            print(f"  ⚠️  {warn}")
    
    if response.errors:
        print("\n❌ ERRORS:")
        for err in response.errors:
            print(f"  ❌ {err}")
    
    if response.generated_files:
        print("\n📁 GENERATED FILES:")
        for filename, filepath in response.generated_files.items():
            print(f"  ├── {filename}: {filepath}")
    
    print("\n" + "=" * 80)


# ============ MAIN INTERACTIVE FUNCTION ============

def interactive_migration() -> List[MigrationRequest]:
    """Run interactive migration input flow."""
    
    try:
        clear_screen()
        print_header("SQL MIGRATION ASSISTANT - INTERACTIVE MODE")
        print("Select any source and target database combination\n")
        
        source_db = select_source_database()
        print(f"\n✓ Selected Source: {source_db.value.upper()}")
        
        target_db = select_target_database()
        print(f"\n✓ Selected Target: {target_db.value.upper()}")
        
        output_format = select_output_format()
        print(f"\n✓ Output Format: {output_format.value.upper()}")
        
        code_entries = get_sql_code()
        if not code_entries:
            return []
        
        requests: List[MigrationRequest] = []
        for source_filename, sql_code in code_entries:
            request = MigrationRequest(
                source=source_db,
                target=target_db,
                output_format=output_format,
                code=sql_code,
                code_type=CodeType.UNKNOWN,
                table_name=derive_target_name_from_source(source_filename),
                source_filename=source_filename,
            )
            is_valid, errors = request.validate()
            if not is_valid:
                label = source_filename or "manual input"
                print(f"\n❌ VALIDATION FAILED for {label}:")
                for error in errors:
                    print(f"  ❌ {error}")
                return []
            requests.append(request)
        
        display_migration_requests(requests)
        
        confirm = input("\nProceed with migration? (yes/no): ").strip().lower()
        if confirm not in ["yes", "y"]:
            print("❌ Migration cancelled")
            return []
        
        print(f"\n✓ {len(requests)} migration request(s) created successfully!")
        return requests
    
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
        return []
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return []


# ============ MIGRATION ============

def run_migrations(requests: List[MigrationRequest]) -> List[MigrationResponse]:
    """Transpile one or more requests via LLM with data manager validation."""
    responses: List[MigrationResponse] = []
    total = len(requests)

    for index, request in enumerate(requests, start=1):
        label = request.source_filename or request.request_id
        print(f"\n{'=' * 80}")
        print(f"⏳ Migrating {index}/{total}: {label}")
        print(f"   (data manager will validate; up to {MAX_MIGRATION_ATTEMPTS} attempts)")
        print("=" * 80)
        response = transpile_request(request)
        display_migration_response(response)
        responses.append(response)

    succeeded = sum(1 for r in responses if r.status == ExecutionStatus.SUCCESS)
    print(f"\n{'=' * 80}")
    print(f"📊 BATCH COMPLETE: {succeeded}/{total} succeeded")
    print("=" * 80)
    return responses


# ============ MAIN ============

if __name__ == "__main__":
    ensure_migration_dirs()
    init_metadata_db()
    print("\nRunning Interactive Migration...\n")
    print(f"Source files: {SOURCE_MIGRATION_DIR}/")
    print(f"Target output: {TARGET_MIGRATION_DIR}/")
    print(f"Metadata DB:  {METADATA_DB_PATH}\n")
    
    requests = interactive_migration()
    
    if requests:
        run_migrations(requests)
    
    else:
        print("\n❌ No migration request created")