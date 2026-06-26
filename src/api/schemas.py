"""Pydantic models for the REST API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineOptionsModel(BaseModel):
    use_llm: bool = True
    skip_synthetic: bool = False
    skip_provision: bool = False
    skip_migrate: bool = False
    skip_recon: bool = False
    skip_tests: bool = False
    skip_docs: bool = False
    integration_tests: bool = False
    preset: str = "full"
    source_database: str = "teradata"
    target_database: str = "bigquery"


class ChatMessageModel(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessageModel] = Field(default_factory=list)
    options: PipelineOptionsModel = Field(default_factory=PipelineOptionsModel)


class TranspileRequest(BaseModel):
    filename: str | None = None
    sql: str | None = None
    source_database: str = "teradata"
    target_database: str = "bigquery"
