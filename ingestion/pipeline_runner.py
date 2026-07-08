"""
Shared pipeline orchestration for the Medicare Denial Intelligence Platform.

Used by:
  - CLI: python ingestion/run_pipeline.py
  - Prefect: ingestion/flows/prefect_pipeline.py
  - Airflow: ingestion/flows/medicare_full_pipeline_dag.py

Steps:
  check_postgres → [download] → load_raw → validate_raw → dbt_run → dbt_test → [train_ml]
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).resolve().parent.parent)))
load_dotenv(PROJECT_ROOT / ".env")

log = logging.getLogger(__name__)

PYTHON = sys.executable


def _dbt_executable() -> str:
    """Resolve dbt CLI next to the active Python (venv Scripts/dbt.exe on Windows)."""
    name = "dbt.exe" if sys.platform == "win32" else "dbt"
    candidate = Path(sys.executable).parent / name
    if candidate.exists():
        return str(candidate)
    return "dbt"


@dataclass
class PipelineConfig:
    project_root: Path = PROJECT_ROOT
    skip_download: bool = True
    skip_load: bool = False
    skip_ml: bool = True
    skip_validate: bool = False
    dbt_select: str = "staging intermediate marts analytics"
    dbt_threads: int = 1
    pipeline_name: str = "medicare_denial_pipeline"
    triggered_by: str = "manual"
    download_years: list[int] = field(default_factory=lambda: [2023, 2024])


@dataclass
class StepResult:
    name: str
    status: str
    duration_sec: float
    detail: str = ""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _env() -> dict[str, str]:
    return {
        **os.environ,
        "POSTGRES_HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "POSTGRES_USER": os.getenv("POSTGRES_USER", "denial_user"),
        "POSTGRES_DB": os.getenv("POSTGRES_DB", "denial_db"),
    }


def _run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
    timeout_sec: int | None = None,
) -> None:
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        env=_env(),
        check=False,
        timeout=timeout_sec,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def _record_run_start(config: PipelineConfig) -> str:
    run_id = str(uuid.uuid4())
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ops.pipeline_runs (run_id, pipeline_name, status, triggered_by)
                    VALUES (:run_id, :name, 'running', :triggered_by)
                    """
                ),
                {
                    "run_id": run_id,
                    "name": config.pipeline_name,
                    "triggered_by": config.triggered_by,
                },
            )
    except Exception as exc:
        log.warning("Could not write ops.pipeline_runs (run ops_schema.sql): %s", exc)
    return run_id


def _record_run_finish(
    run_id: str,
    status: str,
    steps: list[StepResult],
    error: str | None = None,
) -> None:
    payload = [
        {
            "name": s.name,
            "status": s.status,
            "duration_sec": round(s.duration_sec, 2),
            "detail": s.detail,
        }
        for s in steps
    ]
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ops.pipeline_runs
                    SET status = :status,
                        finished_at = NOW(),
                        steps = CAST(:steps AS jsonb),
                        error_message = :error
                    WHERE run_id = CAST(:run_id AS uuid)
                    """
                ),
                {
                    "run_id": run_id,
                    "status": status,
                    "steps": json.dumps(payload),
                    "error": error,
                },
            )
    except Exception as exc:
        log.warning("Could not update ops.pipeline_runs: %s", exc)


def step_check_postgres(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1")).scalar()
        n = conn.execute(
            text(
                """
                SELECT COALESCE(c.reltuples::bigint, 0)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'raw' AND c.relname = 'cms_part_d_spending'
                """
            )
        ).scalar()
    detail = f"Postgres OK; raw.cms_part_d_spending ~{int(n or 0):,} rows"
    return StepResult("check_postgres", "success", (_utcnow() - t0).total_seconds(), detail)


def step_check_cms(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    url = "https://data.cms.gov/api/1/metastore/schemas/dataset/items?limit=1"
    r = requests.head(url, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"CMS API returned HTTP {r.status_code}")
    return StepResult(
        "check_cms",
        "success",
        (_utcnow() - t0).total_seconds(),
        f"HTTP {r.status_code}",
    )


def step_download(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    script = config.project_root / "ingestion" / "scripts" / "download_cms_data.py"
    years_arg = [str(y) for y in config.download_years]
    _run_cmd(
        [PYTHON, str(script), "--years", *years_arg],
        timeout_sec=7200,
    )
    return StepResult(
        "download_cms",
        "success",
        (_utcnow() - t0).total_seconds(),
        ", ".join(years_arg),
    )


def step_load_raw(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    script = config.project_root / "ingestion" / "scripts" / "load_to_postgres.py"
    _run_cmd([PYTHON, str(script)], timeout_sec=14400)
    return StepResult("load_raw", "success", (_utcnow() - t0).total_seconds())


def step_validate_raw(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    script = config.project_root / "data_quality" / "validate_raw.py"
    _run_cmd([PYTHON, str(script)], timeout_sec=600)
    return StepResult("validate_raw", "success", (_utcnow() - t0).total_seconds())


def step_dbt_run(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    dbt_dir = config.project_root / "dbt"
    _run_cmd(
        [
            _dbt_executable(),
            "run",
            "--select",
            config.dbt_select,
            "--threads",
            str(config.dbt_threads),
            "--profiles-dir",
            ".",
        ],
        cwd=dbt_dir,
        timeout_sec=14400,
    )
    return StepResult(
        "dbt_run",
        "success",
        (_utcnow() - t0).total_seconds(),
        config.dbt_select,
    )


def step_dbt_test(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    dbt_dir = config.project_root / "dbt"
    _run_cmd(
        [
            _dbt_executable(),
            "test",
            "--select",
            config.dbt_select,
            "--profiles-dir",
            ".",
        ],
        cwd=dbt_dir,
        timeout_sec=3600,
    )
    return StepResult("dbt_test", "success", (_utcnow() - t0).total_seconds())


def step_train_ml(config: PipelineConfig) -> StepResult:
    t0 = _utcnow()
    script = config.project_root / "ml" / "train_withhold_classifier.py"
    if _model_exists(config):
        _run_cmd([PYTHON, str(script), "--shap-only"], timeout_sec=7200)
    else:
        _run_cmd([PYTHON, str(script)], timeout_sec=7200)
    return StepResult("train_ml", "success", (_utcnow() - t0).total_seconds())


def _model_exists(config: PipelineConfig) -> bool:
    return (config.project_root / "ml" / "artifacts" / "withhold_classifier.joblib").exists()


def run_pipeline(config: PipelineConfig | None = None) -> int:
    """Execute the full pipeline. Returns 0 on success, 1 on failure."""
    config = config or PipelineConfig()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    run_id = _record_run_start(config)
    steps: list[StepResult] = []
    log.info("Pipeline run_id=%s name=%s", run_id, config.pipeline_name)

    try:
        steps.append(step_check_postgres(config))

        if not config.skip_download:
            steps.append(step_check_cms(config))
            steps.append(step_download(config))

        if not config.skip_load:
            steps.append(step_load_raw(config))

        if not config.skip_validate:
            steps.append(step_validate_raw(config))

        steps.append(step_dbt_run(config))
        steps.append(step_dbt_test(config))

        if not config.skip_ml:
            steps.append(step_train_ml(config))

        _record_run_finish(run_id, "success", steps)
        log.info("Pipeline completed successfully")
        for s in steps:
            log.info("  %-18s %s (%.1fs) %s", s.name, s.status, s.duration_sec, s.detail)
        return 0

    except Exception as exc:
        log.exception("Pipeline failed: %s", exc)
        steps.append(
            StepResult("error", "failed", 0.0, str(exc)[:500])
        )
        _record_run_finish(run_id, "failed", steps, str(exc))
        return 1


def get_last_run() -> dict[str, Any] | None:
    """Return most recent pipeline run from ops.pipeline_runs."""
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT run_id, pipeline_name, status, started_at, finished_at, steps
                    FROM ops.pipeline_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
        return dict(row) if row else None
    except Exception:
        return None
