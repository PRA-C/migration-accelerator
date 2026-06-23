"""Teradata connection configuration from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

INPUT_DDL_DIALECT = os.getenv("INPUT_DDL_DIALECT", "teradata").strip().lower()
DEFAULT_SOURCE_DATABASE = os.getenv("DEFAULT_SOURCE_DATABASE", "teradata").strip().lower()


@dataclass(frozen=True)
class TeradataConfig:
    host: str
    user: str
    password: str
    database: str
    port: str
    encryptdata: bool

    def connect_kwargs(self) -> dict:
        kwargs: dict = {
            "host": self.host,
            "user": self.user,
            "password": self.password,
            "dbs_port": self.port,
            "database": self.database,
        }
        if self.encryptdata:
            kwargs["encryptdata"] = True
        return kwargs


def _env(primary: str, fallback: str | None = None, default: str = "") -> str:
    value = os.getenv(primary, "").strip()
    if not value and fallback:
        value = os.getenv(fallback, "").strip()
    return value or default


def load_teradata_config() -> TeradataConfig:
    host = _env("TD_HOST", "TERADATA_HOST")
    user = _env("TD_USER", "TERADATA_USER")
    password = _env("TD_PASSWORD", "TERADATA_PASSWORD")
    database = _env("TD_DATABASE", "TERADATA_DATABASE") or user
    port = _env("TD_PORT", "TERADATA_PORT", "1025")
    sslmode = _env("TD_SSLMODE", "TERADATA_SSLMODE", "require").lower()

    if not host or not user or not password:
        raise ValueError(
            "Teradata connection settings are required. Set TD_HOST, TD_USER, and TD_PASSWORD "
            "(or TERADATA_HOST, TERADATA_USER, TERADATA_PASSWORD) in .env — see .env.example."
        )

    return TeradataConfig(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        encryptdata=sslmode in ("require", "true", "1", "yes"),
    )
