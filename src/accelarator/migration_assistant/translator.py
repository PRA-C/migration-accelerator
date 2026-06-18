"""
SQL Migration Assistant - Interactive Translator (UPDATED)
File 2 of 2: Interactive UI and main flow
Place this at: src/accelerator/migration_assistant/translator.py
UPDATED: Direct source/target selection instead of preset patterns
"""

from typing import Optional, Tuple
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
except Exception as exc:
    raise


# ============ HELPER FUNCTIONS ============

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


def select_source_file() -> Tuple[Optional[str], str]:
    """Select a migration source file from the configured source folder."""
    source_files = read_source_migration_files()

    if not source_files:
        print(f"\n❌ No source files found in {SOURCE_MIGRATION_DIR}/")
        print(f"   Supported extensions: .sql, .proc, .txt")
        return None, ""

    print_section(f"SELECT SOURCE FILE ({SOURCE_MIGRATION_DIR}/)")
    filenames = list(source_files.keys())
    for index, filename in enumerate(filenames, start=1):
        print(f"{index}. {filename}")

    while True:
        choice = input(f"\nSelect file (1-{len(filenames)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(filenames):
            filename = filenames[int(choice) - 1]
            content = source_files[filename]
            print(f"\n✓ Loaded {filename} ({len(content)} characters)")
            return filename, content
        print(f"❌ Invalid choice. Please select 1-{len(filenames)}")


def get_sql_code() -> Tuple[Optional[str], str]:
    """Get SQL/Procedure code from file or manual input."""
    method = select_code_input_method()

    if method == "file":
        return select_source_file()

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
            return None, ""
        except EOFError:
            break
    
    code = "\n".join(lines)
    
    if not code.strip():
        print("❌ No code provided")
        return None, ""
    
    print(f"\n✓ Received {len(code)} characters")
    return None, code


def display_migration_request(request: MigrationRequest):
    """Display migration request details"""
    
    print("\n" + "=" * 80)
    print("📋 MIGRATION REQUEST SUMMARY")
    print("=" * 80)
    
    print(f"\n✓ Request ID: {request.request_id}")
    print(f"✓ Source: {request.source.value.upper()}")
    print(f"✓ Target: {request.target.value.upper()}")
    print(f"✓ Output Format: {request.output_format.value.upper()}")
    print(f"✓ Code Type: {request.code_type.value.upper()}")
    print(f"✓ Code Length: {len(request.code)} characters")
    
    if request.source_filename:
        print(f"✓ Source File: {SOURCE_MIGRATION_DIR}/{request.source_filename}")
    if request.table_name:
        print(f"✓ Target Name: {request.table_name}")
    output_name = target_migration_filename(request.source_filename, request.output_format)
    print(f"✓ Output File: {TARGET_MIGRATION_DIR}/{output_name}")
    
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

def interactive_migration() -> Optional[MigrationRequest]:
    """Run interactive migration input flow"""
    
    try:
        clear_screen()
        print_header("SQL MIGRATION ASSISTANT - INTERACTIVE MODE")
        print("Select any source and target database combination\n")
        
        # Step 1: Select source database
        source_db = select_source_database()
        print(f"\n✓ Selected Source: {source_db.value.upper()}")
        
        # Step 2: Select target database
        target_db = select_target_database()
        print(f"\n✓ Selected Target: {target_db.value.upper()}")
        
        # Step 3: Select output format
        output_format = select_output_format()
        print(f"\n✓ Output Format: {output_format.value.upper()}")
        
        # Step 4: Get SQL code
        source_filename, sql_code = get_sql_code()
        if not sql_code:
            return None
        
        # Step 5: Create migration request (target name derived from source file)
        request = MigrationRequest(
            source=source_db,
            target=target_db,
            output_format=output_format,
            code=sql_code,
            code_type=CodeType.UNKNOWN,
            table_name=derive_target_name_from_source(source_filename),
            source_filename=source_filename,
        )
        
        # Validate request
        is_valid, errors = request.validate()
        
        if not is_valid:
            print("\n❌ VALIDATION FAILED:")
            for error in errors:
                print(f"  ❌ {error}")
            return None
        
        # Display summary
        display_migration_request(request)
        
        # Ask for confirmation
        confirm = input("\nProceed with migration? (yes/no): ").strip().lower()
        if confirm not in ["yes", "y"]:
            print("❌ Migration cancelled")
            return None
        
        print("\n✓ Migration request created successfully!")
        return request
    
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
        return None
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return None


# ============ MIGRATION ============

def run_migration(request: MigrationRequest) -> MigrationResponse:
    """Transpile source code via LLM with data manager validation and display the result."""
    print("\n⏳ Data engineer generating migration...")
    print(f"   (data manager will validate; up to {MAX_MIGRATION_ATTEMPTS} attempts)\n")
    response = transpile_request(request)
    display_migration_response(response)
    return response


# ============ MAIN ============

if __name__ == "__main__":
    ensure_migration_dirs()
    print("\nRunning Interactive Migration...\n")
    print(f"Source files: {SOURCE_MIGRATION_DIR}/")
    print(f"Target output: {TARGET_MIGRATION_DIR}/\n")
    
    request = interactive_migration()
    
    if request:
        print(f"\n✓ Request created: {request.request_id}")
        run_migration(request)
    
    else:
        print("\n❌ No migration request created")