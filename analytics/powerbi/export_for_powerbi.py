#!/usr/bin/env python3
"""
Export public_analytics tables to CSV for easy Power BI import.

Usage (from project root):
  python analytics/powerbi/export_for_powerbi.py

Then in Power BI: Get data → Text/CSV → load files from analytics/powerbi/csv/
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent / "csv"
load_dotenv(PROJECT_ROOT / ".env")

TABLES = [
    "anl_kpi_overview",
    "anl_withhold_national",
    "anl_withhold_by_state",
    "anl_withhold_yoy",
    "anl_drug_spending",
    "anl_provider_withhold_risk",
]


def main() -> None:
    user = os.getenv("POSTGRES_USER", "denial_user")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "denial_db")

    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in .env")

    engine = create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for table in TABLES:
        print(f"Exporting {table}...")
        sql = text(f"SELECT * FROM public_analytics.{table}")
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)

        # Large table: optional sample for Power BI Desktop on low RAM
        if table == "anl_provider_withhold_risk" and len(df) > 500_000:
            high = df[df["withhold_risk_band"] == "High"].head(100_000)
            low = df[df["withhold_risk_band"] == "Low"].sample(
                n=min(100_000, len(df[df["withhold_risk_band"] == "Low"])),
                random_state=42,
            )
            df = pd.concat([high, low], ignore_index=True)
            print(f"  Sampled to {len(df):,} rows for Power BI performance")

        out = OUTPUT_DIR / f"{table}.csv"
        df.to_csv(out, index=False)
        print(f"  → {out} ({len(df):,} rows)")

    print(f"\nDone. Import CSVs from:\n  {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
