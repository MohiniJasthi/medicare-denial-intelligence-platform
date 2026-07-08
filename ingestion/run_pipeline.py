#!/usr/bin/env python3
"""
CLI entry point for the Medicare Denial Intelligence pipeline.

Usage (from project root, venv active):
  python ingestion/run_pipeline.py
  python ingestion/run_pipeline.py --download --load
  python ingestion/run_pipeline.py --skip-load
  python ingestion/run_pipeline.py --ml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.pipeline_runner import PipelineConfig, run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Medicare denial platform pipeline")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download CMS CSVs before load (default: skip download)",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Load raw CSVs to Postgres (default: skip if --skip-load)",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Skip load step (dbt-only refresh)",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip data_quality/validate_raw.py",
    )
    parser.add_argument(
        "--ml",
        action="store_true",
        help="Run ML training after dbt tests",
    )
    parser.add_argument(
        "--dbt-select",
        default="staging intermediate marts analytics",
        help="dbt --select argument",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="dbt threads (default 1)",
    )
    args = parser.parse_args()

    skip_load = args.skip_load or not (args.load or args.download)

    config = PipelineConfig(
        skip_download=not args.download,
        skip_load=skip_load,
        skip_ml=not args.ml,
        skip_validate=args.skip_validate,
        dbt_select=args.dbt_select,
        dbt_threads=args.threads,
        triggered_by="cli",
    )

    return run_pipeline(config)


if __name__ == "__main__":
    sys.exit(main())
