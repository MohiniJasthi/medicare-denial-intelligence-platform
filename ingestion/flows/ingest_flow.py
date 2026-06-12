"""
ingest_flow.py
===============
Apache Airflow DAG: cms_daily_ingest
======================================
Orchestrates the end-to-end ingestion pipeline for the
Medicare Claim Denial Intelligence Platform.

Pipeline:
  1. check_cms_availability       — HEAD request to CMS API
  2. download_part_d_data         — Download Part D spending CSVs
     download_provider_utilization — Download provider utilization CSVs (parallel with 2)
  3. load_raw_to_postgres         — Load CSVs into PostgreSQL raw schema
  4. trigger_dbt_staging          — dbt run --select staging
  5. run_dbt_tests                — dbt test --select staging

Schedule: @daily (runs once per day, no catchup)
Tags: cms, ingestion, healthcare
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# ── DAG-level defaults ─────────────────────────────────────────────────────────
default_args = {
    "owner": "denial_platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "depends_on_past": False,
}

# Airflow runs inside Docker; these paths reflect the container mount points
AIRFLOW_BASE = Path("/opt/airflow")
INGESTION_DIR = AIRFLOW_BASE / "ingestion"
DBT_DIR = AIRFLOW_BASE / "dbt"
DATA_DIR = AIRFLOW_BASE / "data" / "raw"

# ── Python callables ───────────────────────────────────────────────────────────

def check_cms_availability_fn(**context) -> None:
    """
    Verify that the CMS data portal is reachable before starting downloads.
    Logs HTTP status and response time. Fails the task if unreachable.
    """
    probe_url = "https://data.cms.gov/api/1/metastore/schemas/dataset/items?limit=1"
    log = logging.getLogger(__name__)

    try:
        response = requests.head(probe_url, timeout=20)
        log.info(f"CMS API status: HTTP {response.status_code}")
        log.info(f"Response time : {response.elapsed.total_seconds():.2f}s")

        if response.status_code >= 400:
            raise RuntimeError(
                f"CMS API returned HTTP {response.status_code}. "
                "Check https://data.cms.gov for maintenance windows."
            )

        log.info("CMS API is reachable. Proceeding with downloads.")
        context["ti"].xcom_push(key="cms_status", value=response.status_code)

    except requests.exceptions.Timeout:
        raise RuntimeError("CMS API probe timed out (>20s). Network issue?")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot reach CMS API: {e}")


def _run_python_script(script_path: Path, env_overrides: dict | None = None) -> None:
    """
    Execute a Python script in a subprocess, streaming logs to Airflow.
    Raises RuntimeError if the script exits non-zero.
    """
    log = logging.getLogger(__name__)
    env = {**os.environ, **(env_overrides or {})}

    log.info(f"Running: {sys.executable} {script_path}")

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False,   # stream directly to Airflow task log
        text=True,
        env=env,
        cwd=str(AIRFLOW_BASE),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Script {script_path.name} failed with exit code {result.returncode}"
        )


def download_part_d_fn(**context) -> None:
    """Download Medicare Part D prescriber data from CMS."""
    log = logging.getLogger(__name__)
    script = INGESTION_DIR / "scripts" / "download_cms_data.py"

    if not script.exists():
        raise FileNotFoundError(f"Download script not found: {script}")

    _run_python_script(
        script,
        env_overrides={
            "DATA_DIR": str(DATA_DIR),
            "CMS_DATASET": "part_d",   # custom env flag read inside the script
        },
    )
    log.info("Part D data download complete.")


def download_provider_utilization_fn(**context) -> None:
    """Download Medicare Provider Utilization and Payment data from CMS."""
    log = logging.getLogger(__name__)
    script = INGESTION_DIR / "scripts" / "download_cms_data.py"

    if not script.exists():
        raise FileNotFoundError(f"Download script not found: {script}")

    _run_python_script(
        script,
        env_overrides={
            "DATA_DIR": str(DATA_DIR),
            "CMS_DATASET": "provider_utilization",
        },
    )
    log.info("Provider utilization data download complete.")


def load_raw_to_postgres_fn(**context) -> None:
    """Load downloaded CSVs from data/raw into PostgreSQL raw schema."""
    log = logging.getLogger(__name__)
    script = INGESTION_DIR / "scripts" / "load_to_postgres.py"

    if not script.exists():
        raise FileNotFoundError(f"Load script not found: {script}")

    _run_python_script(
        script,
        env_overrides={"DATA_DIR": str(DATA_DIR)},
    )
    log.info("Raw data load to PostgreSQL complete.")


# ── DAG definition ─────────────────────────────────────────────────────────────
with DAG(
    dag_id="cms_daily_ingest",
    description=(
        "End-to-end ingestion: download CMS datasets → load to PostgreSQL → "
        "run dbt staging models and tests."
    ),
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["cms", "ingestion", "healthcare"],
    doc_md=__doc__,
    max_active_runs=1,  # prevent concurrent runs from overlapping on shared data dir
) as dag:

    # ── Task 1: Availability check ─────────────────────────────────────────────
    check_cms = PythonOperator(
        task_id="check_cms_availability",
        python_callable=check_cms_availability_fn,
        doc_md="HEAD request to CMS API. Fails fast if portal is down.",
    )

    # ── Task 2a: Download Part D data ──────────────────────────────────────────
    download_part_d = PythonOperator(
        task_id="download_part_d_data",
        python_callable=download_part_d_fn,
        doc_md="Downloads Medicare Part D Prescribers by Provider and Drug CSV(s).",
        execution_timeout=timedelta(hours=2),
    )

    # ── Task 2b: Download provider utilization (runs in parallel with 2a) ──────
    download_util = PythonOperator(
        task_id="download_provider_utilization",
        python_callable=download_provider_utilization_fn,
        doc_md="Downloads Medicare Physician/Other Practitioners utilization CSV(s).",
        execution_timeout=timedelta(hours=2),
    )

    # ── Task 3: Load raw CSVs to PostgreSQL ────────────────────────────────────
    load_postgres = PythonOperator(
        task_id="load_raw_to_postgres",
        python_callable=load_raw_to_postgres_fn,
        doc_md=(
            "Loads all CSVs in data/raw/ into PostgreSQL raw schema "
            "using chunked pandas to_sql."
        ),
        execution_timeout=timedelta(hours=3),
    )

    # ── Task 4: Run dbt staging models ────────────────────────────────────────
    dbt_staging = BashOperator(
        task_id="trigger_dbt_staging",
        bash_command=(
            f"cd {DBT_DIR} && "
            "dbt run --select staging --profiles-dir . "
            "--no-partial-parse"
        ),
        doc_md="Runs all dbt models in the staging layer.",
        execution_timeout=timedelta(minutes=30),
    )

    # ── Task 5: Run dbt tests ─────────────────────────────────────────────────
    dbt_tests = BashOperator(
        task_id="run_dbt_tests",
        bash_command=(
            f"cd {DBT_DIR} && "
            "dbt test --select staging --profiles-dir . "
            "--no-partial-parse"
        ),
        doc_md="Runs dbt data quality tests against all staging models.",
        execution_timeout=timedelta(minutes=15),
    )

    # ── Task dependencies ─────────────────────────────────────────────────────
    # check → [download_part_d, download_util] → load → dbt_staging → dbt_tests
    check_cms >> [download_part_d, download_util] >> load_postgres >> dbt_staging >> dbt_tests
