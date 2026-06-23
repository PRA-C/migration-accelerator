"""
Synthetic Data Engine (v2.0)
Generates realistic, statistically faithful synthetic data from SQL DDL schemas.

Supported Features:
  - Multiple database dialects (PostgreSQL, MySQL, BigQuery, Snowflake, etc.)
  - Scalar types (INT, VARCHAR, DATE, DECIMAL, etc.)
  - STRUCT types (nested objects)
  - ARRAY types (lists)
  - MAP types (key-value pairs)
  - Nested combinations (ARRAY<STRUCT>, MAP<STRING, ARRAY>, etc.)
  - Custom column mappings via YAML
  - Reproducible data generation (seed)
  - NULL handling with configurable rates
  - Dynamic faker hints based on column names
  - Batch processing of multiple DDL files
  - Interactive table, dialect, and row count selection
  - Full logging and error handling

Usage:
  python -m src.accelarator.synthetic.engine
"""

import os
import sys
import glob
import json
import pandas as pd
import numpy as np
from faker import Faker
import sqlglot
from sqlglot import expressions as exp
from pathlib import Path
from typing import Dict, List, Callable, Optional, Union, Tuple
import logging
import yaml
from datetime import datetime
import io

from accelarator.metadata import init_metadata_db, log_synthetic_data_result

# ============================================================================
# SETUP
# ============================================================================

# Force UTF-8 encoding on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('synthetic_data_gen.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

fake = Faker()

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_FAKER_HINTS = {
    "email": fake.email,
    "name": fake.name,
    "first_name": fake.first_name,
    "last_name": fake.last_name,
    "address": fake.address,
    "city": fake.city,
    "country": fake.country,
    "phone": fake.phone_number,
    "mobile": fake.phone_number,
    "company": fake.company,
    "uuid": fake.uuid4,
    "url": fake.url,
    "website": fake.url,
    "username": fake.user_name,
    "password": fake.password,
}

DEFAULT_NULL_RATE = 0.05

ORDER_STATUS_VALUES = ("COMPLETED", "SHIPPED", "DELIVERED", "PENDING", "CANCELLED", "REFUNDED")
ORDER_STATUS_WEIGHTS = (0.55, 0.20, 0.15, 0.05, 0.03, 0.02)

RECON_COUNTRY_POOL = (
    "United States",
    "United Kingdom",
    "Canada",
    "Germany",
    "France",
    "Australia",
    "India",
    "Japan",
    "Brazil",
    "Mexico",
)


def _random_order_status() -> str:
    return str(np.random.choice(ORDER_STATUS_VALUES, p=ORDER_STATUS_WEIGHTS))


def _short_phone() -> str:
    return fake.numerify("###-###-####")


def _random_recon_country() -> str:
    return str(np.random.choice(RECON_COUNTRY_POOL))

# Supported SQL dialects
SUPPORTED_DIALECTS = {
    "1": ("teradata", "Teradata (default)"),
    "2": ("postgres", "PostgreSQL"),
    "3": ("mysql", "MySQL"),
    "4": ("sqlite", "SQLite"),
    "5": ("snowflake", "Snowflake"),
    "6": ("bigquery", "Google BigQuery"),
    "7": ("redshift", "AWS Redshift"),
    "8": ("tsql", "SQL Server (T-SQL)"),
    "9": ("oracle", "Oracle"),
    "10": ("hive", "Apache Hive"),
    "11": ("spark", "Apache Spark"),
}

# ============================================================================
# TYPE DETECTION
# ============================================================================

def is_struct_type(dtype: str) -> bool:
    """Check if data type is a STRUCT."""
    dtype_lower = dtype.lower().strip()
    return dtype_lower.startswith("struct<") or dtype_lower.startswith("struct(")

def is_array_type(dtype: str) -> bool:
    """Check if data type is an ARRAY."""
    dtype_lower = dtype.lower().strip()
    return dtype_lower.startswith("array<") or dtype_lower.startswith("array(")

def is_map_type(dtype: str) -> bool:
    """Check if data type is a MAP."""
    dtype_lower = dtype.lower().strip()
    return dtype_lower.startswith("map<") or dtype_lower.startswith("map(")

# ============================================================================
# PARSING UTILITIES
# ============================================================================

def extract_bracketed_content(dtype: str, open_char: str = '<', close_char: str = '>') -> str:
    """Extract content between brackets, handling nested brackets."""
    dtype = dtype.strip()
    start_idx = dtype.find(open_char)
    if start_idx == -1:
        return ""
    
    bracket_count = 0
    for i, char in enumerate(dtype[start_idx:]):
        if char == open_char:
            bracket_count += 1
        elif char == close_char:
            bracket_count -= 1
            if bracket_count == 0:
                return dtype[start_idx + 1:start_idx + i]
    
    return ""

def parse_struct_definition(struct_sql: str) -> Dict[str, str]:
    """Parse STRUCT definition into {field_name: field_type}."""
    
    content = extract_bracketed_content(struct_sql)
    fields = {}
    
    current_field = ""
    bracket_depth = 0
    
    for char in content:
        if char in "<(":
            bracket_depth += 1
            current_field += char
        elif char in ">)":
            bracket_depth -= 1
            current_field += char
        elif char == "," and bracket_depth == 0:
            if current_field.strip():
                parts = current_field.strip().rsplit(None, 1)
                if len(parts) == 2:
                    field_name, field_type = parts
                    fields[field_name] = field_type.strip()
            current_field = ""
        else:
            current_field += char
    
    if current_field.strip():
        parts = current_field.strip().rsplit(None, 1)
        if len(parts) == 2:
            field_name, field_type = parts
            fields[field_name] = field_type.strip()
    
    return fields

def parse_array_definition(array_sql: str) -> str:
    """Extract element type from ARRAY definition."""
    return extract_bracketed_content(array_sql).strip()

def parse_map_definition(map_sql: str) -> Tuple[str, str]:
    """Extract key and value types from MAP definition."""
    content = extract_bracketed_content(map_sql)
    
    bracket_depth = 0
    for i, char in enumerate(content):
        if char in "<(":
            bracket_depth += 1
        elif char in ">)":
            bracket_depth -= 1
        elif char == "," and bracket_depth == 0:
            key_type = content[:i].strip()
            value_type = content[i+1:].strip()
            return key_type, value_type
    
    return "", ""

# ============================================================================
# DDL PARSING
# ============================================================================

def parse_ddl(ddl: str, dialect: str = "teradata") -> Dict[str, Dict]:
    """
    Parse SQL CREATE TABLE statement and extract column information.
    
    Supported dialects:
      - duckdb, postgres, mysql, sqlite, snowflake, bigquery, redshift,
      - tsql, oracle, hive, spark, teradata
    """
    try:
        # Validate dialect
        valid_dialects = [
            "duckdb", "postgres", "mysql", "sqlite", "snowflake",
            "bigquery", "redshift", "tsql", "oracle", "hive",
            "spark", "presto", "trino", "mariadb", "starrocks",
            "clickhouse", "teradata", "netezza", "dialect"
        ]
        
        if dialect.lower() not in valid_dialects:
            logger.warning(f"Unknown dialect '{dialect}', using 'teradata' instead")
            dialect = "teradata"
        
        parsed = sqlglot.parse_one(ddl, read=dialect)
        cols = {}
        
        for col in parsed.find_all(exp.ColumnDef):
            col_name = col.name
            col_type = col.args["kind"].sql().lower()
            
            constraints = col.args.get("constraints", [])
            is_nullable = not any("NOT NULL" in str(c).upper() for c in constraints)
            
            cols[col_name] = {
                "name": col_name,
                "dtype": col_type,
                "nullable": is_nullable,
            }
        
        logger.debug(f"Parsed DDL using dialect '{dialect}': found {len(cols)} columns")
        return cols
    
    except Exception as e:
        logger.error(f"Error parsing DDL with dialect '{dialect}': {str(e)}")
        raise

# ============================================================================
# DYNAMIC FAKER HINTS
# ============================================================================

def build_dynamic_faker_hints(columns: Dict[str, Dict]) -> Dict[str, Callable]:
    """Dynamically build faker hints based on column names."""
    faker_map = {}
    
    for col_name, col_info in columns.items():
        col_name_lower = col_name.lower()
        
        for hint_key, provider in BASE_FAKER_HINTS.items():
            if col_name_lower == hint_key or col_name_lower == f"{hint_key}_id":
                faker_map[col_name] = provider
                break
        
        if col_name not in faker_map:
            if "email" in col_name_lower:
                faker_map[col_name] = fake.email
            elif col_name_lower == "phone":
                faker_map[col_name] = _short_phone
            elif "phone" in col_name_lower or "mobile" in col_name_lower:
                faker_map[col_name] = fake.phone_number
            elif "first_name" in col_name_lower or "fname" in col_name_lower:
                faker_map[col_name] = fake.first_name
            elif "last_name" in col_name_lower or "lname" in col_name_lower:
                faker_map[col_name] = fake.last_name
            elif "full_name" in col_name_lower or "name" in col_name_lower:
                faker_map[col_name] = fake.name
            elif "address" in col_name_lower:
                faker_map[col_name] = fake.address
            elif "city" in col_name_lower:
                faker_map[col_name] = fake.city
            elif col_name_lower == "country":
                faker_map[col_name] = _random_recon_country
            elif "company" in col_name_lower:
                faker_map[col_name] = fake.company
            elif "url" in col_name_lower or "website" in col_name_lower:
                faker_map[col_name] = fake.url
            elif "username" in col_name_lower:
                faker_map[col_name] = fake.user_name
            elif col_name_lower == "status":
                faker_map[col_name] = _random_order_status
            elif "uuid" in col_name_lower or "guid" in col_name_lower:
                faker_map[col_name] = fake.uuid4
    
    return faker_map

# ============================================================================
# CUSTOM MAPPINGS
# ============================================================================

def load_column_mappings(config_file: str) -> Dict:
    """Load custom column mappings from YAML."""
    
    if not os.path.exists(config_file):
        logger.debug(f"Mappings file not found: {config_file}")
        return {}
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        mappings = config.get("column_mappings", {})
        logger.info(f"Loaded custom mappings for {len(mappings)} columns")
        return mappings
    
    except Exception as e:
        logger.error(f"Error loading custom mappings: {str(e)}")
        return {}

# ============================================================================
# SCALAR VALUE GENERATION
# ============================================================================

def _generate_scalar_value(
    field_name: str,
    field_type: str,
    faker_map: Dict,
    custom_config: Optional[Dict] = None
) -> Union[str, int, float, bool]:
    """Generate a single scalar value for a field."""
    
    field_type_lower = field_type.lower()
    
    if custom_config:
        if custom_config.get("faker_provider") and hasattr(fake, custom_config["faker_provider"]):
            try:
                provider_func = getattr(fake, custom_config["faker_provider"])
                return provider_func()
            except:
                pass
    
    if field_name in faker_map:
        try:
            return faker_map[field_name]()
        except:
            pass
    
    if any(t in field_type_lower for t in ("int", "bigint", "smallint", "number", "integer")):
        return int(np.random.randint(0, 10_000))
    
    elif any(t in field_type_lower for t in ("decimal", "numeric", "float", "double")):
        return float(np.round(np.random.uniform(0, 1000), 2))
    
    elif "date" in field_type_lower or "timestamp" in field_type_lower:
        start = pd.Timestamp("2023-01-01").value // 10**9
        end = pd.Timestamp("2026-01-01").value // 10**9
        ts = np.random.randint(start, end)
        return pd.Timestamp(ts, unit="s").isoformat()
    
    elif "bool" in field_type_lower:
        return bool(np.random.choice([True, False]))
    
    else:
        return fake.word()

# ============================================================================
# STRUCT GENERATION
# ============================================================================

def generate_struct_data(
    struct_def: str,
    n_rows: int,
    faker_map: Dict[str, Callable],
    output_format: str = "json"
) -> List:
    """Generate data for a STRUCT column."""
    
    logger.debug(f"Generating STRUCT: {struct_def[:50]}...")
    
    fields = parse_struct_definition(struct_def)
    
    if output_format == "json":
        struct_data = []
        for _ in range(n_rows):
            row_struct = {}
            for field_name, field_type in fields.items():
                value = _generate_scalar_value(field_name, field_type, faker_map)
                row_struct[field_name] = value
            struct_data.append(json.dumps(row_struct))
        return struct_data
    
    else:
        struct_data = []
        for _ in range(n_rows):
            row_struct = {}
            for field_name, field_type in fields.items():
                value = _generate_scalar_value(field_name, field_type, faker_map)
                row_struct[field_name] = value
            struct_data.append(row_struct)
        return struct_data

# ============================================================================
# ARRAY GENERATION
# ============================================================================

def generate_array_data(
    array_def: str,
    n_rows: int,
    faker_map: Dict[str, Callable],
    array_length_range: Tuple[int, int] = (1, 5),
    output_format: str = "json"
) -> List:
    """Generate data for an ARRAY column."""
    
    logger.debug(f"Generating ARRAY: {array_def[:50]}...")
    
    element_type = parse_array_definition(array_def)
    min_len, max_len = array_length_range
    
    array_data = []
    
    for _ in range(n_rows):
        arr_len = np.random.randint(min_len, max_len + 1)
        
        if is_struct_type(element_type):
            arr = []
            for _ in range(arr_len):
                struct_json = generate_struct_data(
                    element_type, 
                    1, 
                    faker_map, 
                    "json"
                )[0]
                struct_obj = json.loads(struct_json)
                arr.append(struct_obj)
        
        else:
            arr = [
                _generate_scalar_value(f"element_{i}", element_type, faker_map)
                for i in range(arr_len)
            ]
        
        if output_format == "json":
            array_data.append(json.dumps(arr))
        else:
            array_data.append(arr)
    
    return array_data

# ============================================================================
# MAP GENERATION
# ============================================================================

def generate_map_data(
    map_def: str,
    n_rows: int,
    faker_map: Dict[str, Callable],
    map_size_range: Tuple[int, int] = (1, 5),
    output_format: str = "json"
) -> List:
    """Generate data for a MAP column."""
    
    logger.debug(f"Generating MAP: {map_def[:50]}...")
    
    key_type, value_type = parse_map_definition(map_def)
    min_size, max_size = map_size_range
    
    map_data = []
    for _ in range(n_rows):
        map_size = np.random.randint(min_size, max_size + 1)
        
        map_obj = {}
        for i in range(map_size):
            key = _generate_scalar_value(f"key_{i}", key_type, faker_map)
            
            if is_struct_type(value_type):
                value = json.loads(generate_struct_data(value_type, 1, faker_map, "json")[0])
            else:
                value = _generate_scalar_value(f"value_{i}", value_type, faker_map)
            
            map_obj[str(key)] = value
        
        if output_format == "json":
            map_data.append(json.dumps(map_obj))
        else:
            map_data.append(map_obj)
    
    return map_data

# ============================================================================
# COLUMN DATA GENERATION
# ============================================================================

def generate_column_data(
    col_name: str,
    col_info: Dict,
    faker_map: Dict[str, Callable],
    n_rows: int,
    custom_mappings: Optional[Dict] = None,
    complex_output_format: str = "json"
) -> List:
    """Generate synthetic data for a single column."""
    
    dtype = col_info["dtype"]
    is_nullable = col_info["nullable"]
    
    null_rate = DEFAULT_NULL_RATE if is_nullable else 0.0
    
    if custom_mappings and col_name in custom_mappings:
        null_rate = custom_mappings[col_name].get("null_rate", null_rate)
    
    null_mask = np.random.binomial(1, null_rate, n_rows).astype(bool)
    
    # Handle complex types
    if is_struct_type(dtype):
        values = generate_struct_data(dtype, n_rows, faker_map, complex_output_format)
    
    elif is_array_type(dtype):
        array_config = {}
        if custom_mappings and col_name in custom_mappings:
            array_config = custom_mappings[col_name].get("array", {})
        
        array_range = array_config.get("length_range", (1, 5))
        values = generate_array_data(dtype, n_rows, faker_map, array_range, complex_output_format)
    
    elif is_map_type(dtype):
        map_config = {}
        if custom_mappings and col_name in custom_mappings:
            map_config = custom_mappings[col_name].get("map", {})
        
        map_range = map_config.get("size_range", (1, 5))
        values = generate_map_data(dtype, n_rows, faker_map, map_range, complex_output_format)
    
    # Handle scalar types
    else:
        values = None
        
        # Custom mapping
        if custom_mappings and col_name in custom_mappings:
            custom = custom_mappings[col_name]
            faker_provider = custom.get("faker_provider")
            
            if faker_provider and hasattr(fake, faker_provider):
                try:
                    provider_func = getattr(fake, faker_provider)
                    values = [provider_func() for _ in range(n_rows)]
                    logger.debug(f"  {col_name}: custom faker '{faker_provider}'")
                except Exception as e:
                    logger.warning(f"  {col_name}: faker error: {e}")
            
            elif custom.get("type"):
                custom_type = custom.get("type", "text").lower()
                
                if custom_type in ("numeric", "number", "int", "integer"):
                    min_val = custom.get("min", 0)
                    max_val = custom.get("max", 10_000)
                    values = np.random.randint(min_val, max_val, n_rows).tolist()
                
                elif custom_type in ("decimal", "float"):
                    min_val = custom.get("min", 0.0)
                    max_val = custom.get("max", 1000.0)
                    values = np.round(np.random.uniform(min_val, max_val, n_rows), 2).tolist()
                
                elif custom_type == "date":
                    start_date = custom.get("start_date", "2023-01-01")
                    end_date = custom.get("end_date", "2026-01-01")
                    start = pd.Timestamp(start_date).value // 10**9
                    end = pd.Timestamp(end_date).value // 10**9
                    values = pd.to_datetime(
                        np.random.randint(start, end, n_rows), unit="s"
                    ).tolist()
                
                elif custom_type == "text":
                    values = [fake.word() for _ in range(n_rows)]
        
        # Dynamic faker hints
        if values is None and col_name in faker_map:
            try:
                provider = faker_map[col_name]
                values = [provider() for _ in range(n_rows)]
                logger.debug(f"  {col_name}: dynamic faker hint")
            except Exception as e:
                logger.warning(f"  {col_name}: faker error: {e}")
        
        # Type-based generation
        if values is None:
            dtype_lower = dtype.lower()
            
            if any(t in dtype_lower for t in ("int", "bigint", "smallint", "number", "integer")):
                values = np.random.randint(0, 10_000, n_rows).tolist()
                logger.debug(f"  {col_name}: integer")
            
            elif any(t in dtype_lower for t in ("decimal", "numeric", "float", "double")):
                values = np.round(np.random.normal(500, 150, n_rows), 2).tolist()
                logger.debug(f"  {col_name}: decimal")
            
            elif "date" in dtype_lower or "timestamp" in dtype_lower:
                start = pd.Timestamp("2023-01-01").value // 10**9
                end = pd.Timestamp("2026-01-01").value // 10**9
                values = pd.to_datetime(
                    np.random.randint(start, end, n_rows), unit="s"
                ).tolist()
                logger.debug(f"  {col_name}: datetime")
            
            elif "bool" in dtype_lower:
                values = np.random.choice([True, False], n_rows).tolist()
                logger.debug(f"  {col_name}: boolean")
            
            else:
                values = [fake.word() for _ in range(n_rows)]
                logger.debug(f"  {col_name}: text fallback")
    
    # Apply NULLs
    values_array = np.array(values, dtype=object)
    values_array[null_mask] = None
    
    return values_array.tolist()

# ============================================================================
# TABLE GENERATION
# ============================================================================

def generate(
    ddl: str,
    table_name: str,
    n_rows: int = 1000,
    dialect: str = "teradata",
    custom_mappings: Optional[Dict] = None,
    seed: Optional[int] = None,
    complex_output_format: str = "json"
) -> pd.DataFrame:
    """Generate synthetic rows for a table."""
    
    if seed is not None:
        np.random.seed(seed)
    
    logger.info(f"Parsing DDL for table: {table_name} (dialect: {dialect})")
    columns = parse_ddl(ddl, dialect)
    
    if not columns:
        logger.error(f"No columns found in {table_name}")
        return pd.DataFrame()
    
    faker_map = build_dynamic_faker_hints(columns)
    
    logger.info(f"Generating {n_rows} rows for {table_name}")
    logger.info(f"Columns: {list(columns.keys())}")
    
    data = {}
    for col_name, col_info in columns.items():
        data[col_name] = generate_column_data(
            col_name,
            col_info,
            faker_map,
            n_rows,
            custom_mappings,
            complex_output_format
        )
    
    df = pd.DataFrame(data)
    logger.info(f"[SUCCESS] Generated {len(df)} rows for {table_name}")
    
    return df

# ============================================================================
# FILE I/O
# ============================================================================

def read_ddl_files(input_dir: str) -> Dict[str, str]:
    """Read all SQL files from input directory."""
    
    if not os.path.exists(input_dir):
        logger.error(f"Input directory not found: {input_dir}")
        return {}
    
    ddl_files = glob.glob(os.path.join(input_dir, "*.sql"))
    
    if not ddl_files:
        logger.warning(f"No .sql files found in {input_dir}")
        return {}
    
    ddl_dict = {}
    for file_path in sorted(ddl_files):
        table_name = Path(file_path).stem
        
        try:
            with open(file_path, 'r') as f:
                ddl_content = f.read().strip()
            
            if ddl_content:
                ddl_dict[table_name] = ddl_content
                logger.info(f"Read DDL for table: {table_name}")
        
        except Exception as e:
            logger.error(f"Error reading {file_path}: {str(e)}")
    
    return ddl_dict

# ============================================================================
# BATCH PROCESSING
# ============================================================================

def process_all_tables(
    input_dir: str = "src/input_schema",
    output_dir: str = "src/synthetic_data_gen",
    tables_to_process: Optional[List[str]] = None,
    row_config: Optional[Dict[str, int]] = None,
    dialect: str = "teradata",
    seed: int = 42,
    mappings_file: Optional[str] = None,
    complex_output_format: str = "json"
) -> Dict[str, pd.DataFrame]:
    """Process DDL files and generate synthetic data."""
    
    np.random.seed(seed)
    logger.info(f"Random seed: {seed}")
    logger.info(f"Database dialect: {dialect}")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")
    
    custom_mappings = {}
    if mappings_file and os.path.exists(mappings_file):
        custom_mappings = load_column_mappings(mappings_file)
    
    logger.info(f"Reading DDL files from: {input_dir}")
    ddl_dict = read_ddl_files(input_dir)
    
    if not ddl_dict:
        logger.error("No DDL files to process")
        return {}
    
    # Filter to selected tables
    if tables_to_process:
        ddl_dict = {k: v for k, v in ddl_dict.items() if k in tables_to_process}
    
    if not ddl_dict:
        logger.error("No matching tables found")
        return {}
    
    results = {}
    successful = 0
    failed = 0
    
    logger.info(f"Processing {len(ddl_dict)} table(s)...")
    logger.info("=" * 80)
    
    for table_name, ddl in ddl_dict.items():
        input_path = os.path.join(input_dir, f"{table_name}.sql")
        try:
            n_rows = row_config.get(table_name, 1000) if row_config else 1000
            
            df = generate(
                ddl,
                table_name,
                n_rows=n_rows,
                dialect=dialect,
                custom_mappings=custom_mappings,
                seed=seed,
                complex_output_format=complex_output_format
            )
            
            output_path = os.path.join(output_dir, f"{table_name}.csv")
            df.to_csv(output_path, index=False)
            
            logger.info(f"[SUCCESS] Saved to: {output_path}")
            logger.info(f"   Shape: {df.shape}")
            
            results[table_name] = df
            successful += 1
            log_synthetic_data_result(
                table_name=table_name,
                dialect=dialect,
                input_schema_path=input_path,
                output_file_path=output_path,
                row_count=len(df),
                column_count=len(df.columns),
                seed=seed,
                success=True,
            )
        
        except Exception as e:
            logger.error(f"[ERROR] Error processing {table_name}: {str(e)}")
            failed += 1
            log_synthetic_data_result(
                table_name=table_name,
                dialect=dialect,
                input_schema_path=input_path,
                seed=seed,
                success=False,
                error_message=str(e),
            )
        
        logger.info("-" * 80)
    
    logger.info("=" * 80)
    logger.info(f"SYNTHETIC DATA GENERATION COMPLETE")
    logger.info(f"[SUCCESS] Successful: {successful}")
    logger.info(f"[ERROR] Failed: {failed}")
    logger.info(f"[INFO] Output directory: {output_dir}")
    logger.info(f"[INFO] Database dialect: {dialect}")
    logger.info("=" * 80)
    
    return results

# ============================================================================
# UTILITIES
# ============================================================================

def print_summary(results: Dict[str, pd.DataFrame], output_dir: str, dialect: str):
    """Print summary of generated data."""
    
    print("\n" + "=" * 80)
    print("SYNTHETIC DATA GENERATION SUMMARY")
    print("=" * 80)
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output directory: {output_dir}")
    print(f"Database dialect: {dialect}")
    print(f"Total tables: {len(results)}")
    print("=" * 80)
    
    for table_name, df in results.items():
        print(f"\n[TABLE] {table_name.upper()}")
        print(f"   Shape: {df.shape[0]} rows x {df.shape[1]} columns")
        print(f"   File: {output_dir}/{table_name}.csv")
        print(f"   Columns: {', '.join(df.columns)}")
        print(f"\n   Sample data (first 3 rows):")
        print(df.head(3).to_string(index=False).replace('\n', '\n   '))
    
    print("\n" + "=" * 80)

# ============================================================================
# INTERACTIVE MENU
# ============================================================================

def show_interactive_menu():
    """Show interactive menu for table, dialect, and row selection."""
    
    INPUT_DIR = "src/input_schema"
    OUTPUT_DIR = "src/synthetic_data_gen"
    MAPPINGS_FILE = "src/input_schema/column_mappings.yaml"
    SEED = 42
    COMPLEX_OUTPUT_FORMAT = "json"
    
    # Get available SQL files
    ddl_files = glob.glob(os.path.join(INPUT_DIR, "*.sql"))
    
    if not ddl_files:
        logger.error(f"No SQL files found in {INPUT_DIR}")
        return
    
    # ====== SELECT DIALECT ======
    print("\n" + "=" * 80)
    print("STEP 1: SELECT DATABASE DIALECT")
    print("=" * 80)
    
    for key, (dialect_code, dialect_name) in SUPPORTED_DIALECTS.items():
        print(f"[{key}] {dialect_name}")
    print("[Q] Quit")
    print("=" * 80)
    
    dialect_input = input("Enter dialect number (default: 1): ").strip().upper() or "1"
    
    if dialect_input == "Q":
        logger.info("Exiting...")
        return
    
    if dialect_input not in SUPPORTED_DIALECTS:
        logger.warning("Invalid dialect selection, using Teradata")
        selected_dialect = "teradata"
        dialect_display = "Teradata"
    else:
        selected_dialect, dialect_display = SUPPORTED_DIALECTS[dialect_input]
    
    logger.info(f"Selected dialect: {dialect_display} ({selected_dialect})")
    
    # ====== SELECT TABLES ======
    print("\n" + "=" * 80)
    print("STEP 2: SELECT TABLES TO PROCESS")
    print("=" * 80)
    
    tables = {}
    for idx, file_path in enumerate(sorted(ddl_files), 1):
        table_name = Path(file_path).stem
        tables[str(idx)] = table_name
        print(f"[{idx}] {table_name}")
    
    print(f"[A] All tables")
    print(f"[Q] Quit")
    print("=" * 80)
    
    table_input = input("Enter table number(s) to process (comma-separated, e.g., 1,3,5): ").strip().upper()
    
    if table_input == "Q":
        logger.info("Exiting...")
        return
    
    selected_tables = []
    
    if table_input == "A":
        selected_tables = list(tables.values())
        logger.info(f"Selected: All {len(selected_tables)} tables")
    
    else:
        try:
            indices = [s.strip() for s in table_input.split(",")]
            for idx in indices:
                if idx in tables:
                    selected_tables.append(tables[idx])
                else:
                    logger.warning(f"Invalid selection: {idx}")
            
            if not selected_tables:
                logger.error("No valid tables selected")
                return
            
            logger.info(f"Selected: {', '.join(selected_tables)}")
        
        except Exception as e:
            logger.error(f"Error parsing selection: {e}")
            return
    
    # ====== CONFIGURE ROW COUNTS ======
    print("\n" + "=" * 80)
    print("STEP 3: CONFIGURE ROW COUNTS")
    print("=" * 80)
    
    row_config = {}
    
    for table in selected_tables:
        try:
            n_rows_input = input(f"Number of rows for '{table}' (default: 1000): ").strip()
            n_rows = int(n_rows_input) if n_rows_input else 1000
            
            if n_rows <= 0:
                logger.warning(f"Invalid row count for {table}, using default 1000")
                n_rows = 1000
            
            row_config[table] = n_rows
            logger.info(f"  {table}: {n_rows} rows")
        
        except ValueError:
            logger.warning(f"Invalid input for {table}, using default 1000")
            row_config[table] = 1000
    
    # ====== PROCESS TABLES ======
    print("\n" + "=" * 80)
    print("PROCESSING TABLES...")
    print("=" * 80)
    
    results = process_all_tables(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        tables_to_process=selected_tables,
        row_config=row_config,
        dialect=selected_dialect,
        seed=SEED,
        mappings_file=MAPPINGS_FILE,
        complex_output_format=COMPLEX_OUTPUT_FORMAT
    )
    
    if results:
        print_summary(results, OUTPUT_DIR, dialect_display)
    else:
        logger.error("No tables generated")

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    init_metadata_db()
    logger.info("Starting Synthetic Data Engine v2.0...")
    show_interactive_menu()

if __name__ == "__main__":
    main()