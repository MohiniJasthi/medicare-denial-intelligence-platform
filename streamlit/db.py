"""Database helpers for the Streamlit dashboard."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
  user = os.getenv("POSTGRES_USER", "denial_user")
  password = os.getenv("POSTGRES_PASSWORD", "")
  host = os.getenv("POSTGRES_HOST", "localhost")
  port = os.getenv("POSTGRES_PORT", "5432")
  database = os.getenv("POSTGRES_DB", "denial_db")

  if not password:
    raise ValueError(
      "POSTGRES_PASSWORD is not set. Copy .env.example to .env and set credentials."
    )

  return create_engine(
    f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=0,
    connect_args={
      "connect_timeout": 10,
      "options": "-c statement_timeout=120000",  # 2 minutes per query
    },
  )


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
  with get_engine().connect() as conn:
    return pd.read_sql(text(sql), conn, params=params or {})


def approx_row_count(schema: str, table: str) -> int:
  """Fast row estimate from Postgres statistics (good for large tables)."""
  df = run_query(
    """
    SELECT COALESCE(c.reltuples::bigint, 0) AS row_count
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relname = :table
    """,
    {"schema": schema, "table": table},
  )
  if df.empty:
    return 0
  return int(df.iloc[0, 0])


def table_exists(schema: str, table: str) -> bool:
  df = run_query(
    """
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = :schema AND table_name = :table
    LIMIT 1
    """,
    {"schema": schema, "table": table},
  )
  return not df.empty


def marts_ready() -> bool:
  return table_exists("public_marts", "fct_utilization_by_specialty")


def intermediate_ready() -> bool:
  return table_exists("public_intermediate", "int_utilization_enriched")
