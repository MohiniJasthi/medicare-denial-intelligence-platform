"""
Apache Airflow DAG — full Medicare Denial Intelligence pipeline.

Requires Docker Compose stack with:
  - ./ingestion/flows mounted to /opt/airflow/dags
  - ./ingestion, ./dbt, ./data mounted (see docker-compose.yml)
  - POSTGRES_HOST=host.docker.internal when Postgres runs on the Windows host

DAG id: medicare_full_pipeline
Schedule: @weekly (Sunday 2am UTC) — CMS data is annual; weekly dbt refresh is typical for dev.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/opt/airflow/project"))
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.pipeline_runner import (  # noqa: E402
    PipelineConfig,
    run_pipeline,
)

default_args = {
    "owner": "denial_platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}


def _run_full_pipeline(**context) -> None:
    """Execute pipeline via shared runner (download + load + dbt + validate)."""
    import os

    root = Path(os.getenv("PROJECT_ROOT", "/opt/airflow/project"))
    config = PipelineConfig(
        project_root=root,
        skip_download=False,
        skip_load=False,
        skip_ml=True,
        skip_validate=False,
        triggered_by="airflow",
    )
    code = run_pipeline(config)
    if code != 0:
        raise RuntimeError("Pipeline returned exit code 1")


def _run_dbt_refresh(**context) -> None:
    """Lightweight refresh: dbt + validate + ML (no download/load)."""
    import os

    root = Path(os.getenv("PROJECT_ROOT", "/opt/airflow/project"))
    config = PipelineConfig(
        project_root=root,
        skip_download=True,
        skip_load=True,
        skip_ml=True,
        skip_validate=False,
        triggered_by="airflow_dbt_refresh",
    )
    code = run_pipeline(config)
    if code != 0:
        raise RuntimeError("dbt refresh returned exit code 1")


with DAG(
    dag_id="medicare_full_pipeline",
    description="Full CMS download → load → validate → dbt → optional ML",
    schedule_interval="0 2 * * 0",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["cms", "healthcare", "dbt"],
    max_active_runs=1,
) as dag:

    full_pipeline = PythonOperator(
        task_id="run_full_pipeline",
        python_callable=_run_full_pipeline,
        execution_timeout=timedelta(hours=12),
    )

with DAG(
    dag_id="medicare_dbt_refresh",
    description="dbt run + test + validate + ML (skip download/load)",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["dbt", "healthcare"],
    max_active_runs=1,
) as dag_refresh:

    dbt_refresh = PythonOperator(
        task_id="run_dbt_refresh",
        python_callable=_run_dbt_refresh,
        execution_timeout=timedelta(hours=6),
    )
