#!/usr/bin/env python3
"""
Push Streamlit-ready tables from local Postgres to Neon (or any cloud Postgres).

Usage (from project root, venv active):
  # 1. Create a Neon project at https://neon.tech and copy the connection string
  # 2. Run:
  $env:NEON_DATABASE_URL = "postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require"
  python streamlit/push_to_neon.py

Optional:
  python streamlit/push_to_neon.py --full   # include large tables (slow)
  python streamlit/push_to_neon.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# Tables required for each Streamlit page
ANALYTICS_TABLES = [
    "anl_kpi_overview",
    "anl_withhold_national",
    "anl_withhold_by_state",
    "anl_withhold_yoy",
    "anl_drug_spending",
    "anl_provider_withhold_risk",
]

MARTS_TABLES = [
    "fct_utilization_by_specialty",
    "dim_providers",
]

INTERMEDIATE_TABLES = [
    "int_utilization_enriched",
]

# Default row caps for cloud demo (keeps Neon free tier happy)
DEFAULT_CAPS = {
    "public_analytics.anl_provider_withhold_risk": 200_000,
    "public_marts.dim_providers": 500_000,
    "public_intermediate.int_utilization_enriched": 1_000_000,
}

CHUNK_SIZE = 50_000


def _engine_from_env(prefix: str = "") -> str | None:
    """Build SQLAlchemy URL from POSTGRES_* env vars."""
    user = os.getenv(f"{prefix}POSTGRES_USER", os.getenv("POSTGRES_USER", "denial_user"))
    password = os.getenv(f"{prefix}POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
    host = os.getenv(f"{prefix}POSTGRES_HOST", os.getenv("POSTGRES_HOST", "localhost"))
    port = os.getenv(f"{prefix}POSTGRES_PORT", os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv(f"{prefix}POSTGRES_DB", os.getenv("POSTGRES_DB", "denial_db"))
    if not password:
        return None
    ssl = os.getenv("POSTGRES_SSLMODE", "")
    qs = f"?sslmode={ssl}" if ssl else ""
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}{qs}"


def get_source_url() -> str:
    url = _engine_from_env()
    if not url:
        raise ValueError("Set POSTGRES_PASSWORD in .env for local source database")
    return url


def get_target_url() -> str:
    url = os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if not url:
        raise ValueError(
            "Set NEON_DATABASE_URL to your Neon connection string.\n"
            "Get it from https://console.neon.tech → your project → Connect → Connection string"
        )
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    parsed = urlparse(url.replace("postgresql+psycopg2://", "postgresql://", 1))
    host = parsed.hostname or ""
    placeholder_hosts = ("xxxx", "xxx", "your", "example", "cool-name")
    if not host or any(p in host.lower() for p in placeholder_hosts):
        raise ValueError(
            f"NEON_DATABASE_URL still has a placeholder host ({host!r}).\n"
            "Open https://console.neon.tech → your project → Connect\n"
            "Copy the real connection string (host looks like ep-abc12345.us-east-2.aws.neon.tech)"
        )
    if not parsed.password or parsed.password.lower() in ("password", "xxxxx", "your_password"):
        raise ValueError(
            "NEON_DATABASE_URL still has a placeholder password.\n"
            "Copy the full connection string from the Neon dashboard (includes the real password)."
        )

    if "sslmode" not in url and "neon.tech" in host:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def ensure_schemas(engine, schemas: list[str]) -> None:
    # Use one short autocommit connection per statement to avoid
    # long-lived transaction state on transient network hiccups.
    for schema in schemas:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        print(f"  schema {schema} OK")


def row_count(engine, schema: str, table: str) -> int:
    with engine.connect() as conn:
        n = conn.execute(
            text(f"SELECT COUNT(*) FROM {schema}.{table}")
        ).scalar()
    return int(n or 0)


def copy_table(
    source,
    target,
    schema: str,
    table: str,
    max_rows: int | None,
    dry_run: bool,
) -> None:
    qualified = f"{schema}.{table}"
    src_n = row_count(source, schema, table)
    print(f"\n{qualified}: {src_n:,} rows locally", end="")

    if max_rows and src_n > max_rows:
        print(f" → capping at {max_rows:,} for cloud demo")
        sql = text(f"SELECT * FROM {qualified} LIMIT :limit")
        with source.connect() as conn:
            df = pd.read_sql(sql, conn, params={"limit": max_rows})
    else:
        print()
        chunks: list[pd.DataFrame] = []
        offset = 0
        while True:
            sql = text(
                f"SELECT * FROM {qualified} ORDER BY 1 LIMIT :limit OFFSET :offset"
            )
            with source.connect() as conn:
                chunk = pd.read_sql(
                    sql, conn, params={"limit": CHUNK_SIZE, "offset": offset}
                )
            if chunk.empty:
                break
            chunks.append(chunk)
            offset += len(chunk)
            print(f"  read {offset:,} / {src_n:,}", end="\r")
            if max_rows and offset >= max_rows:
                break
        print()
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

    if df.empty:
        print("  SKIP (empty)")
        return

    if dry_run:
        print(f"  DRY RUN — would write {len(df):,} rows to Neon")
        return

    df.to_sql(
        table,
        target,
        schema=schema,
        if_exists="replace",
        index=False,
        method="multi",
        chunksize=5_000,
    )
    print(f"  wrote {len(df):,} rows to Neon")


def main() -> int:
    parser = argparse.ArgumentParser(description="Push dashboard tables to Neon")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Copy large tables without row caps (slow, may exceed Neon free tier)",
    )
    parser.add_argument(
        "--skip-intermediate",
        action="store_true",
        help="Skip int_utilization_enriched (Provider detail tab won't work)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_url = get_source_url()
    target_url = get_target_url()

    print("Source: local Postgres (.env)")
    print("Target: Neon / cloud Postgres")
    if args.dry_run:
        print("Mode: DRY RUN")

    source = create_engine(
        source_url,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    target = create_engine(
        target_url,
        pool_pre_ping=True,
        poolclass=NullPool,
    )

    # Test connections
    with source.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Source connection OK")
    with target.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Target connection OK")

    schemas = ["public_analytics", "public_marts"]
    if not args.skip_intermediate:
        schemas.append("public_intermediate")

    print("\nCreating schemas on Neon...")
    if not args.dry_run:
        ensure_schemas(target, schemas)

    caps = {} if args.full else DEFAULT_CAPS

    for table in ANALYTICS_TABLES:
        key = f"public_analytics.{table}"
        copy_table(
            source,
            target,
            "public_analytics",
            table,
            caps.get(key),
            args.dry_run,
        )

    for table in MARTS_TABLES:
        key = f"public_marts.{table}"
        copy_table(
            source,
            target,
            "public_marts",
            table,
            caps.get(key),
            args.dry_run,
        )

    if not args.skip_intermediate:
        for table in INTERMEDIATE_TABLES:
            key = f"public_intermediate.{table}"
            copy_table(
                source,
                target,
                "public_intermediate",
                table,
                caps.get(key),
                args.dry_run,
            )

    print("\nDone! Add these to Streamlit Community Cloud → Settings → Secrets:")
    print("  (Use the same host/user/password/db from your NEON_DATABASE_URL)")
    print()
    print("  POSTGRES_HOST = \"ep-xxxx.neon.tech\"")
    print("  POSTGRES_USER = \"...\"")
    print("  POSTGRES_PASSWORD = \"...\"")
    print("  POSTGRES_DB = \"neondb\"")
    print("  POSTGRES_PORT = \"5432\"")
    print()
    print("  Or paste DATABASE_URL = \"<your full Neon connection string>\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
