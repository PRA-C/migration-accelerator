from pydantic import BaseModel, Field
from typing import Literal

class Column(BaseModel):
    name: str
    dtype: str                       # canonical type: int, float, string, date, ...
    nullable: bool = True
    is_pii: bool = False
    distinct_ratio: float | None = None   # cardinality / row_count

class TableSchema(BaseModel):
    name: str
    columns: list[Column]
    foreign_keys: dict[str, str] = Field(default_factory=dict)  # col -> table.col

class Transformation(BaseModel):
    source_tables: list[str]
    target_schema: TableSchema
    logic_summary: str
    edge_case_flags: list[str] = Field(default_factory=list)