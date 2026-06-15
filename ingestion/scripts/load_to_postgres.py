"""
load_to_postgres.py
====================
Loads raw CMS CSV files from data/raw/ into the PostgreSQL `raw` schema.

Each CSV is loaded into a canonical table. Multi-year files for the same
dataset are merged into one table (e.g. raw.cms_part_d_spending).

Usage:
  # Full load (first time — replaces tables)
  python ingestion/scripts/load_to_postgres.py

  # Resume partial loads (skips complete files/years, continues the rest)
  python ingestion/scripts/load_to_postgres.py --resume

  # Show what is loaded vs what is still in CSV files
  python ingestion/scripts/load_to_postgres.py --status

  # Append a new year file to an existing table
  python ingestion/scripts/load_to_postgres.py --append-year data/raw/cms_part_d_spending_2025.csv

  # Load only specific file(s)
  python ingestion/scripts/load_to_postgres.py --only nppes_providers.csv
  python ingestion/scripts/load_to_postgres.py --resume --only cms_part_d_spending_2024.csv

Environment variables (reads from .env if python-dotenv is installed):
  POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
  DATA_DIR — directory with raw CSV files (default: data/raw)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

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
CHUNK_SIZE = 50_000

PG_USER = os.environ.get("POSTGRES_USER", "denial_user")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
PG_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_DB = os.environ.get("POSTGRES_DB", "denial_db")

CANONICAL_TABLE_MAP = {
    r"cms_part_d_spending_\d{4}": "cms_part_d_spending",
    r"cms_provider_utilization_\d{4}": "cms_provider_utilization",
    r"nppes_providers": "nppes_providers",
}

# Treat counts within this ratio as "complete" (line-count vs DB can differ slightly)
COMPLETE_RATIO = 0.98


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


def table_exists(engine: Engine, table_name: str) -> bool:
    """Return True if the table exists in the raw schema."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names(schema=RAW_SCHEMA)


def resolve_canonical_table(file_stem: str) -> str:
    """Map a file stem to its canonical table name."""
    for pattern, canonical in CANONICAL_TABLE_MAP.items():
        if re.fullmatch(pattern, file_stem):
            return canonical
    return file_stem


def extract_year_from_stem(file_stem: str) -> Optional[int]:
    """Extract a 4-digit year from a filename stem, if present."""
    match = re.search(r"(\d{4})", file_stem)
    return int(match.group(1)) if match else None


def get_row_count(engine: Engine, schema: str, table: str) -> int:
    """Return the row count of a table."""
    if not table_exists(engine, table):
        return 0
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {schema}.{table}"))
        return int(result.scalar() or 0)


def get_row_count_for_year(engine: Engine, table: str, year: int) -> int:
    """Return rows for a specific year when the table has a year column."""
    if not table_exists(engine, table):
        return 0
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT COUNT(*) FROM {RAW_SCHEMA}.{table} WHERE year = :year"),
            {"year": str(year)},
        )
        return int(result.scalar() or 0)


def delete_year_from_table(engine: Engine, table: str, year: int) -> int:
    """Delete rows for one year (used before reloading a partial year)."""
    with engine.connect() as conn:
        result = conn.execute(
            text(f"DELETE FROM {RAW_SCHEMA}.{table} WHERE year = :year"),
            {"year": str(year)},
        )
        conn.commit()
        return result.rowcount


# ── CSV helpers ───────────────────────────────────────────────────────────────

def count_csv_data_rows(csv_path: Path) -> int:
    """
    Fast approximate data-row count (total lines minus header).
    Good enough for progress checks on large CMS files.
    """
    line_count = 0
    with open(csv_path, "rb") as handle:
        for buffer in iter(lambda: handle.read(1024 * 1024), b""):
            line_count += buffer.count(b"\n")
    # Last line may or may not end with newline; subtract header row.
    return max(line_count - 1, 0)


def resolve_csv_files(
    data_dir: Path,
    only_files: Optional[list[str]] = None,
) -> list[Path]:
    """Return sorted CSV paths, optionally filtered by filename."""
    if not data_dir.exists():
        return []

    csv_files = sorted(data_dir.glob("*.csv"))
    if not only_files:
        return csv_files

    wanted = {name.lower() for name in only_files}
    selected = [path for path in csv_files if path.name.lower() in wanted]
    missing = wanted - {path.name.lower() for path in selected}
    for name in sorted(missing):
        log.warning(f"Requested file not found in {data_dir}: {name}")
    return selected


# ── Load helpers ──────────────────────────────────────────────────────────────

def load_csv_to_postgres(
    csv_path: Path,
    engine: Engine,
    if_exists: str = "replace",
    skip_rows: int = 0,
) -> int:
    """
    Load a CSV into PostgreSQL using chunked pandas read + to_sql.

    Args:
        csv_path:   Path to the CSV file
        engine:     SQLAlchemy engine
        if_exists:  'replace' for initial load, 'append' for incremental
        skip_rows:  Number of data rows already loaded (resume mid-file)

    Returns:
        Total rows written in this run.
    """
    file_stem = csv_path.stem
    table_name = resolve_canonical_table(file_stem)
    year = extract_year_from_stem(file_stem)
    loaded_at = datetime.now(timezone.utc)

    log.info(
        f"Loading: {csv_path.name}  →  {RAW_SCHEMA}.{table_name}  "
        f"(if_exists='{if_exists}', skip_rows={skip_rows:,})"
    )

    rows_written = 0
    rows_remaining_to_skip = skip_rows
    first_chunk = True

    for chunk_df in pd.read_csv(
        csv_path,
        chunksize=CHUNK_SIZE,
        low_memory=False,
        dtype=str,
        na_values=["", "NA", "N/A", "NULL", "null", "None"],
        keep_default_na=True,
    ):
        if rows_remaining_to_skip > 0:
            if rows_remaining_to_skip >= len(chunk_df):
                rows_remaining_to_skip -= len(chunk_df)
                log.info(
                    f"  ... skipping {len(chunk_df):,} already-loaded rows "
                    f"({skip_rows - rows_remaining_to_skip:,}/{skip_rows:,})"
                )
                continue
            chunk_df = chunk_df.iloc[rows_remaining_to_skip:]
            rows_remaining_to_skip = 0

        chunk_df.columns = [
            re.sub(r"\s+", "_", col.strip().lower()) for col in chunk_df.columns
        ]
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
            method="multi",
        )

        rows_written += len(chunk_df)
        first_chunk = False
        log.info(f"  ... {rows_written:,} rows written this run")

    log.info(f"✓ {RAW_SCHEMA}.{table_name} — {rows_written:,} rows written this run")
    return rows_written


def get_loaded_rows_for_file(engine: Engine, csv_path: Path) -> int:
    """Return how many rows from this file are already in the database."""
    table_name = resolve_canonical_table(csv_path.stem)
    year = extract_year_from_stem(csv_path.stem)

    if not table_exists(engine, table_name):
        return 0
    if year is not None:
        return get_row_count_for_year(engine, table_name, year)
    return get_row_count(engine, RAW_SCHEMA, table_name)


def is_file_fully_loaded(engine: Engine, csv_path: Path) -> bool:
    """Return True when DB rows for this file meet the CSV row estimate."""
    csv_rows = count_csv_data_rows(csv_path)
    loaded_rows = get_loaded_rows_for_file(engine, csv_path)
    if csv_rows == 0:
        return loaded_rows > 0
    return loaded_rows >= int(csv_rows * COMPLETE_RATIO)


def choose_if_exists(
    engine: Engine,
    csv_path: Path,
    mode: str,
    tables_touched_this_run: set[str],
) -> str:
    """Pick replace vs append for the first chunk of a file."""
    table_name = resolve_canonical_table(csv_path.stem)
    year = extract_year_from_stem(csv_path.stem)

    if mode == "append-year":
        return "append"

    if mode == "resume":
        if is_file_fully_loaded(engine, csv_path):
            return "append"  # won't be used; caller should skip
        if get_loaded_rows_for_file(engine, csv_path) > 0:
            return "append"
        if table_exists(engine, table_name):
            return "append"
        return "replace"

    # Full load (default): first file per table in this run replaces.
    if table_name in tables_touched_this_run:
        return "append"
    return "replace"


def append_new_year_file(
    csv_path: Path,
    engine: Engine,
    *,
    replace_existing_year: bool = False,
) -> int:
    """
    Append a new yearly CMS file into an existing canonical table.

    Example:
        append_new_year_file(Path("data/raw/cms_part_d_spending_2025.csv"), engine)

    If that year is already present:
      - replace_existing_year=False  → skip (no-op)
      - replace_existing_year=True   → delete that year, then reload
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    table_name = resolve_canonical_table(csv_path.stem)
    year = extract_year_from_stem(csv_path.stem)
    if year is None:
        raise ValueError(
            f"Cannot append by year for '{csv_path.name}'. "
            "Filename must include a 4-digit year, e.g. cms_part_d_spending_2025.csv"
        )

    ensure_raw_schema(engine)
    existing_for_year = get_row_count_for_year(engine, table_name, year)
    csv_rows = count_csv_data_rows(csv_path)

    if existing_for_year > 0:
        if existing_for_year >= int(csv_rows * COMPLETE_RATIO) and not replace_existing_year:
            log.info(
                f"Year {year} already loaded in {RAW_SCHEMA}.{table_name} "
                f"({existing_for_year:,} rows) — skipping."
            )
            return 0
        if replace_existing_year or existing_for_year < int(csv_rows * COMPLETE_RATIO):
            deleted = delete_year_from_table(engine, table_name, year)
            log.info(
                f"Removed {deleted:,} existing rows for year {year} "
                f"from {RAW_SCHEMA}.{table_name} before reload."
            )

    if_exists = "append" if table_exists(engine, table_name) else "replace"
    return load_csv_to_postgres(csv_path, engine, if_exists=if_exists, skip_rows=0)


def resume_file_load(csv_path: Path, engine: Engine) -> int:
    """
    Resume loading a single CSV:
      - skip if already complete
      - skip already-loaded rows and append the remainder
    """
    if is_file_fully_loaded(engine, csv_path):
        loaded = get_loaded_rows_for_file(engine, csv_path)
        log.info(
            f"Skipping {csv_path.name} — already loaded "
            f"({loaded:,} rows in database)."
        )
        return 0

    table_name = resolve_canonical_table(csv_path.stem)
    skip_rows = get_loaded_rows_for_file(engine, csv_path)
    if_exists = "append" if (skip_rows > 0 or table_exists(engine, table_name)) else "replace"

    if skip_rows > 0:
        log.info(
            f"Resuming {csv_path.name} from row {skip_rows + 1:,} "
            f"into {RAW_SCHEMA}.{table_name}"
        )

    return load_csv_to_postgres(
        csv_path,
        engine,
        if_exists=if_exists,
        skip_rows=skip_rows,
    )


def resume_remaining_loads(
    engine: Engine,
    data_dir: Path = DATA_DIR,
    only_files: Optional[list[str]] = None,
) -> dict[str, int]:
    """
    Resume all incomplete CSV loads in data_dir.
    Skips files that are already fully loaded.
    """
    csv_files = resolve_csv_files(data_dir, only_files)
    if not csv_files:
        log.error(f"No CSV files found in {data_dir.resolve()}")
        sys.exit(1)

    ensure_raw_schema(engine)
    summary: dict[str, int] = {}

    for csv_path in csv_files:
        try:
            rows = resume_file_load(csv_path, engine)
            table_name = resolve_canonical_table(csv_path.stem)
            summary[table_name] = summary.get(table_name, 0) + rows
        except Exception as exc:
            log.error(f"Failed to resume {csv_path.name}: {exc}", exc_info=True)

    return summary


def print_ingestion_status(
    engine: Engine,
    data_dir: Path = DATA_DIR,
    only_files: Optional[list[str]] = None,
) -> None:
    """Print CSV vs database row counts for each file."""
    csv_files = resolve_csv_files(data_dir, only_files)
    if not csv_files:
        log.warning(f"No CSV files found in {data_dir.resolve()}")
        return

    log.info("\n── Ingestion Status ─────────────────────────────────────────")
    log.info(f"{'File':<42} {'CSV~Rows':>12} {'DB Rows':>12} {'Status':>12}")
    log.info("-" * 82)

    for csv_path in csv_files:
        table_name = resolve_canonical_table(csv_path.stem)
        csv_rows = count_csv_data_rows(csv_path)
        db_rows = get_loaded_rows_for_file(engine, csv_path)

        if is_file_fully_loaded(engine, csv_path):
            status = "COMPLETE"
        elif db_rows > 0:
            pct = (db_rows / csv_rows * 100) if csv_rows else 0
            status = f"{pct:.0f}% DONE"
        else:
            status = "NOT STARTED"

        log.info(
            f"{csv_path.name:<42} {csv_rows:>12,} {db_rows:>12,} {status:>12}"
        )

    log.info("-" * 82)


def run_full_load(
    engine: Engine,
    data_dir: Path = DATA_DIR,
    only_files: Optional[list[str]] = None,
) -> dict[str, int]:
    """Original behaviour: load all files; first file per table replaces."""
    csv_files = resolve_csv_files(data_dir, only_files)
    if not csv_files:
        log.error(f"No CSV files found in {data_dir.resolve()}")
        sys.exit(1)

    ensure_raw_schema(engine)
    summary: dict[str, int] = {}
    tables_touched_this_run: set[str] = set()

    for csv_path in csv_files:
        try:
            table_name = resolve_canonical_table(csv_path.stem)
            if_exists = choose_if_exists(
                engine, csv_path, mode="full", tables_touched_this_run=tables_touched_this_run
            )
            rows = load_csv_to_postgres(csv_path, engine, if_exists=if_exists)
            summary[table_name] = summary.get(table_name, 0) + rows
            tables_touched_this_run.add(table_name)
        except Exception as exc:
            log.error(f"Failed to load {csv_path.name}: {exc}", exc_info=True)

    return summary


def verify_summary(engine: Engine, summary: dict[str, int]) -> None:
    """Log final row counts for tables touched in this run."""
    if not summary:
        log.info("No rows were written in this run.")
        return

    log.info("\n── Row Count Verification ───────────────────────────────────")
    for table_name in summary:
        try:
            db_count = get_row_count(engine, RAW_SCHEMA, table_name)
            log.info(f"  {RAW_SCHEMA}.{table_name:40s} {db_count:>12,} rows")
        except Exception as exc:
            log.warning(f"  Could not verify {table_name}: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load raw CMS CSV files into PostgreSQL raw schema.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume incomplete loads (skip finished files, continue partial ones).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show CSV vs database row counts and exit.",
    )
    parser.add_argument(
        "--append-year",
        metavar="CSV_PATH",
        help="Append one new yearly file, e.g. data/raw/cms_part_d_spending_2025.csv",
    )
    parser.add_argument(
        "--replace-year",
        action="store_true",
        help="With --append-year, delete and reload that year if it already exists.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="FILE",
        help="Process only these CSV filenames, e.g. --only nppes_providers.csv",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=f"Directory containing CSV files (default: {DATA_DIR})",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR

    log.info("=" * 60)
    log.info("Medicare Denial Platform — Load Raw CSVs to PostgreSQL")
    log.info(f"Data directory : {data_dir.resolve()}")
    log.info(f"Target schema  : {RAW_SCHEMA}")
    if not _dotenv_loaded:
        log.warning("python-dotenv not installed — reading env vars from shell only.")
    log.info("=" * 60)

    if not data_dir.exists():
        log.error(f"Data directory not found: {data_dir.resolve()}")
        sys.exit(1)

    engine = get_engine()

    if args.status:
        print_ingestion_status(engine, data_dir, args.only)
        return

    if args.append_year:
        csv_path = Path(args.append_year)
        if not csv_path.is_absolute():
            csv_path = Path.cwd() / csv_path
        summary = {
            resolve_canonical_table(csv_path.stem): append_new_year_file(
                csv_path,
                engine,
                replace_existing_year=args.replace_year,
            )
        }
        verify_summary(engine, summary)
        log.info("\nAppend complete.")
        return

    csv_files = resolve_csv_files(data_dir, args.only)
    if not csv_files:
        log.error(f"No CSV files found in {data_dir.resolve()}")
        sys.exit(1)

    log.info(f"Found {len(csv_files)} CSV file(s) to process:")
    for csv_path in csv_files:
        size_mb = csv_path.stat().st_size / (1024 * 1024)
        log.info(f"  {csv_path.name}  ({size_mb:.1f} MB)")

    if args.resume:
        log.info("Mode: RESUME (skip complete files, continue partial loads)")
        summary = resume_remaining_loads(engine, data_dir, args.only)
    else:
        log.info("Mode: FULL LOAD (first file per table uses replace)")
        summary = run_full_load(engine, data_dir, args.only)

    verify_summary(engine, summary)
    log.info("\n" + "=" * 60)
    log.info("Done. Next step: cd dbt && dbt run --select staging")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
