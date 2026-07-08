"""
Prefect orchestration flow for the Medicare Denial Intelligence Platform.

Recommended on Windows with native PostgreSQL (no Docker required).

Usage:
  pip install prefect
  python ingestion/flows/prefect_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.pipeline_runner import PipelineConfig, run_pipeline  # noqa: E402

try:
    from prefect import flow
except ImportError as exc:
    raise SystemExit("Prefect is not installed. Run: pip install prefect") from exc


@flow(name="medicare-denial-platform", log_prints=True)
def denial_platform_flow(
    skip_download: bool = True,
    skip_load: bool = True,
    skip_validate: bool = False,
    skip_ml: bool = True,
    dbt_select: str = "staging intermediate marts analytics",
    dbt_threads: int = 1,
) -> int:
    """
    Orchestrate the full platform pipeline.

    Defaults: dbt refresh only (data already in Postgres).
    Full re-ingestion: skip_download=False, skip_load=False
    """
    config = PipelineConfig(
        skip_download=skip_download,
        skip_load=skip_load,
        skip_validate=skip_validate,
        skip_ml=skip_ml,
        dbt_select=dbt_select,
        dbt_threads=dbt_threads,
        triggered_by="prefect",
    )
    return run_pipeline(config)


if __name__ == "__main__":
    sys.exit(
        denial_platform_flow(
            skip_download=True,
            skip_load=True,
            skip_ml=True,
        )
    )
