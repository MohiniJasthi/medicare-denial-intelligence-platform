"""Database helpers for the Streamlit dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def _from_streamlit_secrets() -> dict[str, str]:
    """Read Postgres settings from st.secrets (Streamlit Cloud / local secrets.toml)."""
    out: dict[str, str] = {}
    try:
        if not hasattr(st, "secrets"):
            return out

        flat_keys = (
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "DATABASE_URL",
        )
        for key in flat_keys:
            if key in st.secrets:
                out[key] = str(st.secrets[key])

        if "postgres" in st.secrets:
            pg = st.secrets["postgres"]
            nested = {
                "user": "POSTGRES_USER",
                "password": "POSTGRES_PASSWORD",
                "host": "POSTGRES_HOST",
                "port": "POSTGRES_PORT",
                "database": "POSTGRES_DB",
                "db": "POSTGRES_DB",
            }
            for secret_key, env_key in nested.items():
                if secret_key in pg:
                    out[env_key] = str(pg[secret_key])
    except Exception:
        return out
    return out


def get_postgres_config() -> dict[str, str]:
    """
    Resolve Postgres connection settings.

    Priority: st.secrets → environment variables (.env locally) → defaults.
    """
    secrets = _from_streamlit_secrets()
    config = {
        "user": secrets.get("POSTGRES_USER")
        or os.getenv("POSTGRES_USER", "denial_user"),
        "password": secrets.get("POSTGRES_PASSWORD")
        or os.getenv("POSTGRES_PASSWORD", ""),
        "host": secrets.get("POSTGRES_HOST")
        or os.getenv("POSTGRES_HOST", "localhost"),
        "port": secrets.get("POSTGRES_PORT")
        or os.getenv("POSTGRES_PORT", "5432"),
        "database": secrets.get("POSTGRES_DB")
        or os.getenv("POSTGRES_DB", "denial_db"),
    }

    database_url = secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if database_url:
        parsed = urlparse(database_url)
        if parsed.username:
            config["user"] = parsed.username
        if parsed.password:
            config["password"] = parsed.password
        if parsed.hostname:
            config["host"] = parsed.hostname
        if parsed.port:
            config["port"] = str(parsed.port)
        if parsed.path and len(parsed.path) > 1:
            config["database"] = parsed.path.lstrip("/")

    return config


def postgres_configured() -> bool:
    return bool(get_postgres_config().get("password"))


@st.cache_resource
def get_engine() -> Engine:
    cfg = get_postgres_config()

    if not cfg["password"]:
        raise ValueError(
            "POSTGRES_PASSWORD is not set.\n\n"
            "Local: copy .env.example to .env and set credentials.\n"
            "Streamlit Cloud: open app Settings → Secrets and add postgres "
            "credentials (see streamlit/DEPLOY.md)."
        )

    # NullPool: fresh connection per query — avoids stale pooled connections on reruns
    connect_args: dict = {
        "connect_timeout": 10,
        "options": "-c statement_timeout=120000",  # 2 minutes per query
    }
    if "neon.tech" in cfg["host"] or os.getenv("POSTGRES_SSLMODE") == "require":
        connect_args["sslmode"] = "require"

    return create_engine(
        (
            f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}"
            f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
        ),
        poolclass=NullPool,
        connect_args=connect_args,
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


@st.cache_data(ttl=300)
def marts_ready() -> bool:
    return table_exists("public_marts", "fct_utilization_by_specialty")


@st.cache_data(ttl=300)
def analytics_ready() -> bool:
    return table_exists("public_analytics", "anl_drug_spending")


@st.cache_data(ttl=300)
def intermediate_ready() -> bool:
    return table_exists("public_intermediate", "int_utilization_enriched")
