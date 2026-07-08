# Orchestration

End-to-end pipeline scheduling for the Medicare Denial Intelligence Platform.

## Pipeline steps

```
check_postgres
    → [check_cms → download_cms]   (optional)
    → [load_raw]                   (optional)
    → [validate_raw]
    → dbt_run
    → dbt_test
    → [train_ml]                   (optional)
```

Run history is logged to **`ops.pipeline_runs`** in PostgreSQL.

---

## One-time setup — ops schema

```powershell
# Load password from .env first, then:
& "E:\PostgreSQL\16\bin\psql.exe" -U denial_user -d denial_db -f ingestion\sql\ops_schema.sql
```

---

## Option A — CLI (recommended on Windows + native Postgres)

**dbt refresh only** (default — data already loaded):

```powershell
cd E:\projects\healthcare\denial-platform
.\.venv\Scripts\Activate.ps1

Get-Content .\.env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
    Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
  }
}
$env:POSTGRES_HOST = "localhost"

python ingestion/run_pipeline.py
```

**Full re-ingestion** (download + load + dbt + validate):

```powershell
python ingestion/run_pipeline.py --download --load
```

**With ML retrain:**

```powershell
python ingestion/run_pipeline.py --ml
```

**dbt-only (fastest):**

```powershell
python ingestion/run_pipeline.py --skip-load --skip-validate
```

---

## Option B — Prefect (industry orchestrator, no Docker)

```powershell
pip install prefect

python ingestion/flows/prefect_pipeline.py
```

**Custom run from Python:**

```python
from ingestion.flows.prefect_pipeline import denial_platform_flow

denial_platform_flow(skip_download=False, skip_load=False, skip_ml=True)
```

**Prefect UI (optional):**

```powershell
prefect flow serve ingestion/flows/prefect_pipeline.py:denial_platform_flow
```

---

## Option C — Airflow (Docker)

Use when Docker is running and Postgres is on the **host** (`host.docker.internal`).

```powershell
cd E:\projects\healthcare\denial-platform
docker compose up -d postgres airflow-webserver airflow-scheduler
```

Wait for Airflow UI: http://localhost:8080

**DAGs:**

| DAG | Schedule | Purpose |
|-----|----------|---------|
| `medicare_dbt_refresh` | Daily | dbt + validate (no download/load/ML) |
| `medicare_full_pipeline` | Weekly | Full download + load + dbt |
| `cms_daily_ingest` | Daily | Legacy staging-only DAG |

Enable DAGs in the UI → **Trigger DAG**.

```powershell
docker exec denial_airflow_scheduler airflow dags trigger medicare_dbt_refresh
```

---

## Monitor pipeline runs

```powershell
& "E:\PostgreSQL\16\bin\psql.exe" -U denial_user -d denial_db -c "
SELECT pipeline_name, status, started_at, finished_at
FROM ops.pipeline_runs
ORDER BY started_at DESC
LIMIT 5;"
```

---

## Files

| File | Role |
|------|------|
| `ingestion/pipeline_runner.py` | Shared step logic + ops logging |
| `ingestion/run_pipeline.py` | CLI entry point |
| `ingestion/flows/prefect_pipeline.py` | Prefect flow |
| `ingestion/flows/medicare_full_pipeline_dag.py` | Airflow DAGs |
| `ingestion/sql/ops_schema.sql` | `ops.pipeline_runs` table |

---

## Suggested schedules (production)

| Job | Frequency | Command / DAG |
|-----|-----------|---------------|
| dbt refresh | Daily | `medicare_dbt_refresh` or CLI |
| Full CMS reload | Quarterly / annually | `medicare_full_pipeline` |
| Data quality | After every load | `validate_raw` (in pipeline) |
