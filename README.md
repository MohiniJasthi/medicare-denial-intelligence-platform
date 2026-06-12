# Medicare Claim Denial Intelligence Platform

> **End-to-end Data Engineering portfolio project** — healthcare analytics pipeline
> ingesting, transforming, modeling, and predicting Medicare claim denials using
> public CMS datasets, Apache Airflow, dbt, PostgreSQL, XGBoost, and HuggingFace.

---

## Problem Statement

The U.S. healthcare system loses an estimated **$260 billion annually** to claim denials,
administrative waste, and improper payments. Providers spend $8–$12 per claim to manage
denials, yet 60%+ of initial denials are never appealed — leaving revenue on the table.

This platform demonstrates how modern data engineering principles — robust ingestion
pipelines, dimensional modeling, ML-powered denial prediction, and LLM-assisted appeal
reasoning — can be applied to public Medicare data to surface actionable insights that
translate directly to portfolio value for Data Engineering and Analytics roles.

---

## Tech Stack

| Component           | Technology                          | Purpose                                   |
|---------------------|-------------------------------------|-------------------------------------------|
| Containerization    | Docker + Docker Compose             | Reproducible local environment            |
| Data Warehouse      | PostgreSQL 16                       | Primary OLAP store                        |
| Workflow Orchestration | Apache Airflow 2.9 (LocalExecutor) | Pipeline scheduling and observability     |
| DB Admin UI         | pgAdmin 4                           | SQL exploration and schema browsing       |
| Transformation      | dbt Core 1.8 + dbt-postgres         | Staged → Intermediate → Mart modeling     |
| Data Ingestion      | Python + pandas + requests          | CMS bulk data download and loading        |
| Data Quality        | Great Expectations                  | Schema validation and data contracts      |
| ML – Denial Prediction | XGBoost + LightGBM + scikit-learn | Binary denial classifier                  |
| ML Experiment Tracking | MLflow                           | Model versioning and metric tracking      |
| Explainability      | SHAP                                | Feature importance for denial drivers     |
| AI / NLP            | HuggingFace Transformers + PyTorch  | Appeal letter generation, ICD-10 parsing  |
| Dashboard           | Streamlit + Plotly                  | Interactive denial analytics UI           |
| Notebook IDE        | Jupyter + ipykernel                 | EDA and model development                 |

---

## Project Layers

| Layer                    | Description                                                           |
|--------------------------|-----------------------------------------------------------------------|
| **DE — Ingestion**       | Downloads CMS datasets via REST API; loads to PostgreSQL raw schema   |
| **DE — Transformation**  | dbt staging → intermediate → marts with surrogate keys and tests      |
| **DA — Analytics**       | Denial rate dashboards, provider scorecards, specialty benchmarks     |
| **DS — ML**              | XGBoost denial classifier; SHAP waterfall plots for explainability    |
| **AI — NLP**             | LLM-generated appeal letters; ICD-10 code description extraction      |

---

## Data Sources

| Dataset                                        | Source                          | Table                         | ~Size    |
|------------------------------------------------|---------------------------------|-------------------------------|----------|
| Medicare Part D Prescribers by Provider & Drug | CMS data.cms.gov                | `raw.cms_part_d_spending`     | ~24 M rows/yr |
| Medicare Physician Utilization & Payment       | CMS data.cms.gov                | `raw.cms_provider_utilization`| ~10 M rows/yr |
| Open Payments (Sunshine Act)                   | CMS data.cms.gov                | `raw.cms_open_payments`       | ~15 M rows/yr |
| NPPES NPI Registry (bulk)                      | download.cms.gov/nppes          | `raw.nppes_providers`         | ~8 M rows |

---

## Setup Instructions

### Prerequisites
- Docker Desktop (≥ 4.x) with Docker Compose v2
- Python 3.11+
- Git

### 1 — Clone the repository
```bash
git clone https://github.com/<your-username>/medicare-denial-intelligence-platform.git
cd medicare-denial-intelligence-platform
```

### 2 — Configure environment variables
```bash
cp .env.example .env
```
Open `.env` and fill in secure values for all passwords and the Fernet key.

To generate a Fernet key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3 — Start the Docker stack
```bash
docker-compose up -d
```

This starts PostgreSQL, pgAdmin, Airflow init, Airflow webserver, and Airflow scheduler.
Wait ~60 seconds for Airflow to initialize on first boot.

### 4 — Access the UIs

| Service      | URL                       | Default Credentials               |
|--------------|---------------------------|-----------------------------------|
| Airflow      | http://localhost:8080     | From `AIRFLOW_ADMIN_USER/PASSWORD` in `.env` |
| pgAdmin      | http://localhost:5050     | From `PGADMIN_DEFAULT_EMAIL/PASSWORD` in `.env` |
| PostgreSQL   | localhost:5432            | From `POSTGRES_USER/PASSWORD` in `.env`        |

### 5 — Trigger the ingestion DAG
In the Airflow UI at http://localhost:8080:
1. Navigate to **DAGs** → `cms_daily_ingest`
2. Toggle the DAG **on** (blue toggle)
3. Click **Trigger DAG ▶** to run immediately

Or from the CLI:
```bash
docker exec denial_airflow_scheduler airflow dags trigger cms_daily_ingest
```

### 6 — Run dbt transformations
```bash
# From your local machine (requires dbt installed in your Python env):
cd dbt
dbt run
dbt test

# Or via Make:
make dbt-run
make dbt-test
```

### 7 — Launch the dashboard
```bash
pip install -r requirements.txt
streamlit run streamlit/app.py
```
Access the dashboard at http://localhost:8501

---

## Project Structure

```
denial-platform/
├── docker-compose.yml              # Full stack: PG + Airflow + pgAdmin
├── .env.example                    # Environment variable template
├── requirements.txt                # Python dependencies
├── Makefile                        # Common dev commands
│
├── dbt/                            # dbt transformation project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── staging/                # Raw → cleaned views (type-cast, renamed)
│   │   │   ├── sources.yml
│   │   │   ├── schema.yml
│   │   │   ├── stg_cms_part_d_spending.sql
│   │   │   ├── stg_cms_provider_utilization.sql
│   │   │   └── stg_nppes_providers.sql
│   │   ├── intermediate/           # Business logic joins (coming soon)
│   │   └── marts/                  # Analytical fact/dim tables (coming soon)
│   ├── tests/                      # Custom singular tests
│   ├── seeds/                      # Static reference data (ICD-10, taxonomy)
│   └── macros/                     # Reusable SQL macros
│
├── ingestion/
│   ├── scripts/
│   │   ├── download_cms_data.py    # Downloads CMS CSVs with retry logic
│   │   ├── load_to_postgres.py     # Chunked CSV → PostgreSQL loader
│   │   └── init_schemas.sql        # Bootstrap SQL (raw/staging/marts schemas)
│   └── flows/
│       └── ingest_flow.py          # Airflow DAG: cms_daily_ingest
│
├── data/
│   └── raw/                        # Downloaded CMS CSV files (gitignored)
│
├── notebooks/                      # EDA and model development
├── ml/                             # ML pipeline: denial classifier + SHAP
├── streamlit/                      # Interactive analytics dashboard
│   └── app.py
└── .gitignore
```

---

## SQL Skills Showcased

This project demonstrates the following SQL and dbt techniques:

- **Window functions** — `ROW_NUMBER()` for deduplication; `LAG()` / `LEAD()` for trend analysis
- **CTEs** — multi-step transformations with readable intermediate steps
- **Surrogate key generation** — `md5(col1 || '-' || col2)` as stable join keys
- **Type casting** — safely casting CMS string columns to `integer`, `numeric(18,2)`, `varchar`
- **Null handling** — `COALESCE`, `NULLIF`, and CMS suppression-aware nullable counts
- **Schema-level organization** — raw → staging → intermediate → marts layering
- **dbt source freshness** — `loaded_at_field` for staleness detection
- **dbt tests** — `unique`, `not_null`, `accepted_values`, `relationships` out of the box
- **Derived metrics** — implied denial/withhold rate from payment vs. allowed amounts
- **Partitioned aggregations** — spending by specialty, state, and drug class
- **Dimensional modeling** — provider dimension (NPPES) × multiple fact grains
- **Incremental loading** — append-mode SQL for multi-year CMS datasets

---

## Roadmap

- [ ] Intermediate models: provider dimension, HCPCS lookup, specialty benchmarks
- [ ] Marts: `fct_provider_spending`, `fct_utilization_by_specialty`, `dim_providers`
- [ ] Great Expectations data quality suite
- [ ] XGBoost denial prediction model + MLflow tracking
- [ ] SHAP feature importance dashboard
- [ ] HuggingFace appeal letter generator
- [ ] Streamlit multi-page dashboard

---

*Built for healthcare data engineering portfolio demonstration.
Public CMS data only — no PHI or PII.*
