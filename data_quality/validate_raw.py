#!/usr/bin/env python3
"""
Validate raw CMS tables in PostgreSQL.

CMS-aware checks (handles empty strings, float years, suppressed values).

Usage (from project root, venv active):
  python data_quality/validate_raw.py
  python data_quality/validate_raw.py --table cms_part_d_spending
  python data_quality/validate_raw.py --strict   # tighter thresholds
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

SAMPLE_SIZE = 10_000

TABLE_CONFIG = {
    "cms_part_d_spending": {
        "required_columns": ["prscrbr_npi", "year", "tot_clms", "tot_drug_cst"],
        "not_null": ["prscrbr_npi", "year"],
    },
    "cms_provider_utilization": {
        "required_columns": [
            "rndrng_npi",
            "hcpcs_cd",
            "year",
            "avg_mdcr_pymt_amt",
            "avg_mdcr_alowd_amt",
        ],
        "not_null": ["rndrng_npi", "hcpcs_cd", "year"],
    },
    "nppes_providers": {
        "required_columns": ["npi"],
        "not_null": ["npi"],
    },
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"  # error | warn


def get_engine():
    user = os.getenv("POSTGRES_USER", "denial_user")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "denial_db")
    if not password:
        raise ValueError("POSTGRES_PASSWORD is not set in .env")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    )


def is_nullish(series: pd.Series) -> pd.Series:
    """Treat NaN, empty strings, and CMS-style blanks as null."""
    if series.dtype == object or pd.api.types.is_string_dtype(series):
        s = series.astype(str).str.strip()
        return series.isna() | s.eq("") | s.str.lower().isin({"nan", "none", "null", "<na>"})
    return series.isna()


def approx_row_count(engine, table: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COALESCE(c.reltuples::bigint, 0)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'raw' AND c.relname = :table
                """
            ),
            {"table": table},
        ).scalar()
    return int(row or 0)


def load_sample(engine, table: str, n: int) -> pd.DataFrame:
    sql = text(f"SELECT * FROM raw.{table} TABLESAMPLE BERNOULLI(1) LIMIT :n")
    with engine.connect() as conn:
        try:
            return pd.read_sql(sql, conn, params={"n": n})
        except Exception:
            sql = text(f"SELECT * FROM raw.{table} LIMIT :n")
            return pd.read_sql(sql, conn, params={"n": n})


def check_not_null(
    df: pd.DataFrame, col: str, mostly: float, strict: bool
) -> CheckResult:
    if col not in df.columns:
        return CheckResult(f"not_null:{col}", False, "column missing")
    nullish = is_nullish(df[col])
    rate = 1.0 - nullish.mean()
    threshold = mostly if strict else max(mostly - 0.04, 0.90)
    passed = rate >= threshold
    return CheckResult(
        f"not_null:{col}",
        passed,
        f"populated rate {rate:.2%} (need >={threshold:.0%})",
    )


def check_years(df: pd.DataFrame, col: str = "year", strict: bool = False) -> CheckResult:
    if col not in df.columns:
        return CheckResult("years_2023_2024", False, "year column missing")
    years = pd.to_numeric(df[col], errors="coerce")
    valid = years.isin([2023, 2024])
    rate = valid.mean()
    threshold = 0.99 if strict else 0.95
    invalid_examples = (
        df.loc[~valid, col].dropna().astype(str).unique()[:5].tolist()
    )
    detail = f"valid year rate {rate:.2%} (need >={threshold:.0%})"
    if invalid_examples:
        detail += f"; examples: {invalid_examples}"
    return CheckResult("years_2023_2024", rate >= threshold, detail)


def check_payment_amounts(df: pd.DataFrame, strict: bool = False) -> CheckResult:
    """
    CMS utilization: when allowed > 0, payment should usually be <= allowed.
    Some rows legitimately violate this (adjustments, rounding) — warn, don't hard-fail.
    """
    a = pd.to_numeric(df.get("avg_mdcr_alowd_amt"), errors="coerce")
    p = pd.to_numeric(df.get("avg_mdcr_pymt_amt"), errors="coerce")
    mask = a.notna() & p.notna() & (a > 0)
    if mask.sum() == 0:
        return CheckResult(
            "payment_amounts",
            False,
            "no rows with allowed > 0",
            severity="warn",
        )

    ratio = p[mask] / a[mask]
    # Typical Medicare: payment between 0 and allowed; allow small overflow
    valid = (ratio >= 0) & (ratio <= 1.10)
    rate = valid.mean()
    threshold = 0.95 if strict else 0.80

    return CheckResult(
        "payment_amounts",
        rate >= threshold,
        f"payment/allowed in [0, 1.10] for {rate:.2%} of rows with allowed>0 "
        f"(need >={threshold:.0%})",
        severity="warn" if not strict else "error",
    )


def check_npi_format(df: pd.DataFrame, col: str) -> CheckResult:
    if col not in df.columns:
        return CheckResult(f"npi_format:{col}", False, "column missing")
    values = df[col].astype(str).str.strip()
    populated = values[~is_nullish(df[col])]
    if populated.empty:
        return CheckResult(f"npi_format:{col}", False, "no populated NPIs")
    # NPI is 10 digits; allow numeric strings with optional .0 from float import
    cleaned = populated.str.replace(r"\.0$", "", regex=True)
    valid = cleaned.str.match(r"^\d{10}$")
    rate = valid.mean()
    return CheckResult(
        f"npi_format:{col}",
        rate >= 0.95,
        f"10-digit NPI rate {rate:.2%}",
        severity="warn",
    )


def validate_table(engine, table: str, strict: bool = False) -> bool:
    log.info("── Validating raw.%s ──", table)
    cfg = TABLE_CONFIG[table]
    results: list[CheckResult] = []

    row_count = approx_row_count(engine, table)
    log.info("Approx row count: %s", f"{row_count:,}")
    results.append(
        CheckResult("row_count", row_count > 0, f"approx {row_count:,} rows")
    )

    if row_count == 0:
        _log_results(results)
        return False

    df = load_sample(engine, table, SAMPLE_SIZE)
    log.info("Sample loaded: %s rows, %s columns", f"{len(df):,}", len(df.columns))
    results.append(
        CheckResult("sample_rows", len(df) > 0, f"{len(df):,} rows in sample")
    )

    missing = [c for c in cfg["required_columns"] if c not in df.columns]
    results.append(
        CheckResult(
            "required_columns",
            not missing,
            "missing: " + ", ".join(missing) if missing else "all present",
        )
    )
    if missing:
        _log_results(results)
        return False

    mostly = 0.99 if strict else 0.95
    for col in cfg["not_null"]:
        results.append(check_not_null(df, col, mostly, strict))

    if table == "cms_provider_utilization":
        results.append(check_payment_amounts(df, strict))
        results.append(check_npi_format(df, "rndrng_npi"))

    if table == "cms_part_d_spending":
        results.append(check_npi_format(df, "prscrbr_npi"))

    if table == "nppes_providers":
        results.append(check_npi_format(df, "npi"))

    if table in ("cms_part_d_spending", "cms_provider_utilization"):
        results.append(check_years(df, strict=strict))

    ok = _log_results(results)
    log.info("Table raw.%s: %s", table, "PASS" if ok else "FAIL")
    return ok


def _log_results(results: list[CheckResult]) -> bool:
    ok = True
    for r in results:
        if r.passed:
            status = "PASS"
        elif r.severity == "warn":
            status = "WARN"
        else:
            status = "FAIL"
            ok = False

        log.info("  %-28s %s %s", r.name, status, f"— {r.detail}" if r.detail else "")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate raw CMS tables")
    parser.add_argument(
        "--table",
        choices=list(TABLE_CONFIG.keys()),
        help="Validate one table only",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use tighter CMS thresholds (for CI / production)",
    )
    args = parser.parse_args()

    engine = get_engine()
    tables = [args.table] if args.table else list(TABLE_CONFIG.keys())

    results = [validate_table(engine, t, strict=args.strict) for t in tables]
    if all(results):
        log.info("All validations PASSED (WARN rows are informational)")
        return 0
    log.error("One or more validations FAILED — see FAIL lines above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
