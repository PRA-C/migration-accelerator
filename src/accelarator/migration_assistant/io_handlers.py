"""
SQL Migration Assistant - Input/Output Handlers
File 1 of 2: Data structures and models
Place this at: src/accelerator/migration_assistant/io_handlers.py
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime
from pathlib import Path
import glob
import json
import os


SOURCE_MIGRATION_DIR = "src/source_files_for_migration"
TARGET_MIGRATION_DIR = "src/target_files_migration"
SUPPORTED_SOURCE_EXTENSIONS = (".sql", ".proc", ".txt")


# ============ ENUMS ============
class MigrationPattern(Enum):
    """Realistic migration patterns"""
    LEGACY_TO_DW = "legacy_to_dw"
    BATCH_TO_SPARK = "batch_to_spark"
    ONPREM_TO_CLOUD = "onprem_to_cloud"
    MONOLITHIC_TO_MODERN = "monolithic_to_modern"


class SourceDatabase(Enum):
    """Source databases - what we're migrating FROM"""
    DUCKDB = "duckdb"
    TERADATA = "teradata"
    ORACLE = "oracle"
    SQL_SERVER = "mssql"
    NETEZZA = "netezza"
    POSTGRESQL = "postgres"
    MYSQL = "mysql"


class TargetDatabase(Enum):
    """Target databases - what we're migrating TO"""
    SNOWFLAKE = "snowflake"
    REDSHIFT = "redshift"
    BIGQUERY = "bigquery"
    AZURE_SYNAPSE = "azure_synapse"
    SPARK = "spark"
    POSTGRESQL = "postgres"


class OutputFormat(Enum):
    """Output format types"""
    TARGET_SQL_ONLY = "target_sql"
    PYTHON_CONNECTOR = "python_connector"
    PYSPARK = "pyspark"
    DBT = "dbt"
    EXECUTE_DIRECT = "execute_direct"


class CodeType(Enum):
    """Type of input code"""
    SQL_QUERY = "sql"
    STORED_PROCEDURE = "procedure"
    BATCH_SCRIPT = "script"
    UNKNOWN = "unknown"


class ExecutionStatus(Enum):
    """Execution status"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"


# ============ INPUT DATA STRUCTURES ============

@dataclass
class MigrationRequest:
    """User input for migration request"""
    
    source: SourceDatabase
    target: TargetDatabase
    output_format: OutputFormat
    code: str
    
    # Optional
    code_type: CodeType = CodeType.UNKNOWN
    table_name: Optional[str] = None
    schema_name: Optional[str] = None
    source_filename: Optional[str] = None
    request_id: str = field(default_factory=lambda: f"req_{datetime.now().timestamp()}")
    timestamp: datetime = field(default_factory=datetime.now)
    
    def validate(self) -> tuple[bool, List[str]]:
        """Validate request"""
        errors = []
        
        if not self.code or not self.code.strip():
            errors.append("Code cannot be empty")
        
        if len(self.code) > 1_000_000:
            errors.append("Code exceeds 1MB limit")
        
        if not self.source:
            errors.append("Source database is required")
        
        if not self.target:
            errors.append("Target database is required")
        
        if self.source and self.target:
            if self.source.value == self.target.value:
                errors.append("Source and target cannot be the same database")
        
        return len(errors) == 0, errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "source": self.source.value,
            "target": self.target.value,
            "output_format": self.output_format.value,
            "code_type": self.code_type.value,
            "code_length": len(self.code),
            "table_name": self.table_name,
            "schema_name": self.schema_name,
            "source_filename": self.source_filename,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ExecutionConfig:
    """Configuration for code execution on target"""
    
    execute: bool = False
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    
    use_iam_role: bool = False
    iam_role_arn: Optional[str] = None
    aws_region: Optional[str] = None
    
    timeout_seconds: int = 300
    commit_transaction: bool = True
    create_temp_table: bool = False
    temp_table_name: Optional[str] = None


# ============ OUTPUT DATA STRUCTURES ============

@dataclass
class TranspilationResult:
    """Result of code transpilation"""
    
    success: bool
    generated_code: Optional[str] = None
    code_type: CodeType = CodeType.UNKNOWN
    
    source_db: Optional[str] = None
    target_db: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    code_length_original: int = 0
    code_length_generated: int = 0
    
    validation_passed: bool = False
    validation_feedback: Optional[str] = None
    
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "code_type": self.code_type.value,
            "source_db": self.source_db,
            "target_db": self.target_db,
            "code_length_original": self.code_length_original,
            "code_length_generated": self.code_length_generated,
            "validation_passed": self.validation_passed,
            "validation_feedback": self.validation_feedback,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ExecutionResult:
    """Result of executing code on target database"""
    
    status: ExecutionStatus
    query_id: Optional[str] = None
    
    rows_affected: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_deleted: int = 0
    
    execution_time_ms: float = 0.0
    
    data_quality_passed: bool = False
    row_count_before: Optional[int] = None
    row_count_after: Optional[int] = None
    
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    
    target_table: Optional[str] = None
    target_schema: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "status": self.status.value,
            "query_id": self.query_id,
            "rows_affected": self.rows_affected,
            "rows_inserted": self.rows_inserted,
            "rows_updated": self.rows_updated,
            "rows_deleted": self.rows_deleted,
            "execution_time_ms": self.execution_time_ms,
            "data_quality_passed": self.data_quality_passed,
            "row_count_before": self.row_count_before,
            "row_count_after": self.row_count_after,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "target_table": self.target_table,
            "target_schema": self.target_schema,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class MigrationResponse:
    """Complete response to user"""
    
    request_id: str
    status: ExecutionStatus
    
    transpilation: TranspilationResult
    
    execution: Optional[ExecutionResult] = None
    
    generated_files: Dict[str, str] = field(default_factory=dict)
    
    timestamp: datetime = field(default_factory=datetime.now)
    processing_time_ms: float = 0.0
    
    messages: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def add_message(self, message: str):
        """Add info message"""
        self.messages.append(message)
    
    def add_warning(self, warning: str):
        """Add warning"""
        self.warnings.append(warning)
    
    def add_error(self, error: str):
        """Add error"""
        self.errors.append(error)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "transpilation": self.transpilation.to_dict(),
            "execution": self.execution.to_dict() if self.execution else None,
            "generated_files": self.generated_files,
            "messages": self.messages,
            "warnings": self.warnings,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat(),
            "processing_time_ms": self.processing_time_ms
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


# ============ FILE I/O ============

def ensure_migration_dirs(
    source_dir: str = SOURCE_MIGRATION_DIR,
    target_dir: str = TARGET_MIGRATION_DIR,
) -> None:
    """Create source and target migration directories if missing."""
    Path(source_dir).mkdir(parents=True, exist_ok=True)
    Path(target_dir).mkdir(parents=True, exist_ok=True)


def read_source_migration_files(
    source_dir: str = SOURCE_MIGRATION_DIR,
) -> Dict[str, str]:
    """Read migration source files from the source directory."""
    ensure_migration_dirs(source_dir=source_dir)

    if not os.path.exists(source_dir):
        return {}

    files: Dict[str, str] = {}
    patterns = [os.path.join(source_dir, f"*{ext}") for ext in SUPPORTED_SOURCE_EXTENSIONS]

    for pattern in patterns:
        for file_path in sorted(glob.glob(pattern)):
            filename = os.path.basename(file_path)
            try:
                content = Path(file_path).read_text(encoding="utf-8").strip()
                if content:
                    files[filename] = content
            except OSError:
                continue

    return files


def target_migration_filename(
    source_filename: Optional[str],
    output_format: OutputFormat,
) -> str:
    """Build output filename using the source stem and format-specific extension."""
    stem = Path(source_filename).stem if source_filename else "migration"
    extension_map = {
        OutputFormat.TARGET_SQL_ONLY: ".sql",
        OutputFormat.PYTHON_CONNECTOR: ".py",
        OutputFormat.PYSPARK: ".py",
        OutputFormat.DBT: ".sql",
        OutputFormat.EXECUTE_DIRECT: ".sql",
    }
    return f"{stem}{extension_map.get(output_format, '.sql')}"


def derive_target_name_from_source(source_filename: Optional[str]) -> Optional[str]:
    """Derive target artifact name from the source filename."""
    if source_filename:
        return Path(source_filename).stem
    return None


def write_target_migration_file(
    filename: str,
    content: str,
    target_dir: str = TARGET_MIGRATION_DIR,
) -> str:
    """Write migrated output to the target directory."""
    ensure_migration_dirs(target_dir=target_dir)
    output_path = os.path.join(target_dir, filename)
    Path(output_path).write_text(content, encoding="utf-8")
    return output_path


# ============ HELPER FUNCTIONS ============

def create_success_response(
    request_id: str,
    generated_code: str,
    source_db: str,
    target_db: str
) -> MigrationResponse:
    """Create a successful migration response"""
    
    transpilation = TranspilationResult(
        success=True,
        generated_code=generated_code,
        source_db=source_db,
        target_db=target_db,
        code_length_generated=len(generated_code),
        validation_passed=True
    )
    
    response = MigrationResponse(
        request_id=request_id,
        status=ExecutionStatus.SUCCESS,
        transpilation=transpilation
    )
    
    response.add_message(f"Successfully transpiled {source_db} to {target_db}")
    return response


def create_error_response(
    request_id: str,
    error_message: str,
    error_type: str = "TranspilationError"
) -> MigrationResponse:
    """Create an error response"""
    
    transpilation = TranspilationResult(
        success=False,
        error_message=error_message,
        error_type=error_type
    )
    
    response = MigrationResponse(
        request_id=request_id,
        status=ExecutionStatus.FAILED,
        transpilation=transpilation
    )
    
    response.add_error(error_message)
    return response


def create_execution_response(
    request_id: str,
    transpilation_result: TranspilationResult,
    execution_result: ExecutionResult
) -> MigrationResponse:
    """Create a response with both transpilation and execution"""
    
    if transpilation_result.success and execution_result.status == ExecutionStatus.SUCCESS:
        overall_status = ExecutionStatus.SUCCESS
    elif execution_result.status == ExecutionStatus.PARTIAL:
        overall_status = ExecutionStatus.PARTIAL
    else:
        overall_status = ExecutionStatus.FAILED
    
    response = MigrationResponse(
        request_id=request_id,
        status=overall_status,
        transpilation=transpilation_result,
        execution=execution_result
    )
    
    return response