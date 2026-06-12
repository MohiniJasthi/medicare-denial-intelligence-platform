"""
load_to_postgres.py
====================
Loads raw CMS CSV files from data/raw/ into the PostgreSQL `raw` schema.

Each CSV is loaded into a table named after the file stem. For example:
  data/raw/cms_part_d_spending_2022.csv  →  raw.cms_part_d_spending_2022

A `_loaded_at` timestamp column is appended automatically.

For multi-year loads, all yearly files for the same dataset are unioned
into a single canonical table (e.g., raw.cms_part_d_spending) that includes
a `year` column if not already present.

Usage:
  python ingestion/scripts/load_to_postgres.py

Environment variables (reads from .env if python-dotenv is installed):
  POSTGRES_USER     — database user
  POSTGRES_PASSWORD — database password
  POSTGRES_HOST     — host (default: localhost)
  POSTGRES_PORT     — port (default: 5432)
  POSTGRES_DB       — database name (default: denial_db)
  DATA_DIR          — directory with raw CSV files (default: data/raw)
"""

import os
import sys
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Optional: load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
    _dotenv_loaded = True
except ImportError:
    _dotenv_loaded = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
DATA_DIR = Path(os.environ.get("DATA_DIR", "data/raw"))
RAW_SCHEMA = "raw"
CHUNK_SIZE = 50_000  # rows per chunk for large files

# PostgreSQL connection from environment
PG_USER = os.environ.get("POSTGRES_USER", "denial_user")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
PG_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_DB = os.environ.get("POSTGRES_DB", "denial_db")

# Dataset-to-canonical-table mapping
# Files matching these patterns are consolidated into one table
CANONICAL_TABLE_MAP = {
    r"cms_part_d_spending_\d{4}": "cms_part_d_spending",
    r"cms_provider_utilization_\d{4}": "cms_provider_utilization",
    r"nppes_providers": "nppes_providers",
}


# ── Database helpers ──────────────────────────────────────────────────────────

def get_engine() -> Engine:
    """Build a SQLAlchemy engine from environment variables."""
    if not PG_PASSWORD:
        log.error(
            "POSTGRES_PASSWORD is not set. "
            "Copy .env.example to .env and fill in your credentials."
        )
        sys.exit(1)

    conn_str = (
        f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}"
        f"@{PG_HOST}:{PG_PORT}/{PG_DB}"
    )
    engine = create_engine(
        conn_str,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    log.info(f"Connected to PostgreSQL at {PG_HOST}:{PG_PORT}/{PG_DB} as {PG_USER}")
    return engine


def ensure_raw_schema(engine: Engine) -> None:
    """Create the `raw` schema if it doesn't already exist."""
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}"))
        conn.commit()
    log.info(f"Schema '{RAW_SCHEMA}' is ready.")


def resolve_canonical_table(file_stem: str) -> str:
    """
    Map a file stem to its canonical table name.
    E.g., 'cms_part_d_spending_2022' → 'cms_part_d_spending'.
    Falls back to the file stem itself.
    """
    for pattern, canonical in CANONICAL_TABLE_MAP.items():
        if re.fullmatch(pattern, file_stem):
            return canonical
    return file_stem


def extract_year_from_stem(file_stem: str) -> Optional[int]:
    """Extract a 4-digit year from a filename stem, if present."""
    match = re.search(r"(\d{4})", file_stem)
    return int(match.group(1)) if match else None


# ── Load helpers ──────────────────────────────────────────────────────────────

def load_csv_to_postgres(
    csv_path: Path,
    engine: Engine,
    if_exists: str = "replace",
) -> int:
    """
    Load a CSV into PostgreSQL using chunked pandas read + to_sql.

    Args:
        csv_path:  Path to the CSV file
        engine:    SQLAlchemy engine
        if_exists: 'replace' for initial load, 'append' for incremental

    Returns:
        Total rows loaded.
    """
    file_stem = csv_path.stem
    table_name = resolve_canonical_table(file_stem)
    year = extract_year_from_stem(file_stem)
    loaded_at = datetime.now(timezone.utc)

    log.info(f"Loading: {csv_path.name}  →  {RAW_SCHEMA}.{table_name}  (if_exists='{if_exists}')")

    total_rows = 0
    first_chunk = True

    for chunk_df in pd.read_csv(
        csv_path,
        chunksize=CHUNK_SIZE,
        low_memory=False,
        dtype=str,          # load everything as string; dbt handles casting
        na_values=["", "NA", "N/A", "NULL", "null", "None"],
        keep_default_na=True,
    ):
        # Normalize column names: lowercase, spaces → underscores
        chunk_df.columns = [
            re.sub(r"\s+", "_", col.strip().lower()) for col in chunk_df.columns
        ]

        # Inject metadata columns
        chunk_df["_loaded_at"] = loaded_at
        if year and "year" not in chunk_df.columns:
            chunk_df["year"] = str(year)

        write_mode = if_exists if first_chunk else "append"

        chunk_df.to_sql(
            name=table_name,
            con=engine,
            schema=RAW_SCHEMA,
            if_exists=write_mode,
            index=False,
            method="multi",     # faster batch insert
        )

        total_rows += len(chunk_df)
        first_chunk = False

        log.info(f"  ... {total_rows:,} rows loaded so far")

    log.info(f"✓ {RAW_SCHEMA}.{table_name} — {total_rows:,} total rows")
    return total_rows


def get_row_count(engine: Engine, schema: str, table: str) -> int:
    """Return the row count of a table."""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {schema}.{table}"))
        return result.scalar()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=" * 60)
    log.info("Medicare Denial Platform — Load Raw CSVs to PostgreSQL")
    log.info(f"Data directory : {DATA_DIR.resolve()}")
    log.info(f"Target schema  : {RAW_SCHEMA}")
    if not _dotenv_loaded:
        log.warning("python-dotenv not installed — reading env vars from shell only.")
    log.info("=" * 60)

    if not DATA_DIR.exists():
        log.error(f"Data directory not found: {DATA_DIR.resolve()}")
        log.error("Run ingestion/scripts/download_cms_data.py first.")
        sys.exit(1)

    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        log.error(f"No CSV files found in {DATA_DIR.resolve()}")
        sys.exit(1)

    log.info(f"Found {len(csv_files)} CSV file(s) to load:")
    for f in csv_files:
        size_mb = f.stat().st_size / (1024 * 1024)
        log.info(f"  {f.name}  ({size_mb:.1f} MB)")

    engine = get_engine()
    ensure_raw_schema(engine)

    summary = {}

    for csv_path in csv_files:
        try:
            # For multi-year datasets: first year replaces, subsequent years append
            table_name = resolve_canonical_table(csv_path.stem)
            if_exists = "replace" if table_name not in summary else "append"

            rows = load_csv_to_postgres(csv_path, engine, if_exists=if_exists)
            summary[table_name] = summary.get(table_name, 0) + rows

        except Exception as e:
            log.error(f"Failed to load {csv_path.name}: {e}", exc_info=True)

    # Final row count verification
    log.info("\n── Row Count Verification ───────────────────────────────────")
    for table_name in summary:
        try:
            db_count = get_row_count(engine, RAW_SCHEMA, table_name)
            log.info(f"  {RAW_SCHEMA}.{table_name:40s} {db_count:>12,} rows")
        except Exception as e:
            log.warning(f"  Could not verify {table_name}: {e}")

    log.info("\n" + "=" * 60)
    log.info("Load complete. Next step: cd dbt && dbt run --select staging")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
