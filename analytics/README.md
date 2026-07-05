# Analytics Extension

Curated **analytics tables** for deeper analysis and **Power BI** dashboards.

## dbt analytics layer

Models live in `dbt/models/analytics/`. Postgres schema: **`public_analytics`**

| Table | Purpose |
|-------|---------|
| `anl_kpi_overview` | Executive KPI cards (1 row) |
| `anl_withhold_national` | Specialty × year withhold benchmarks |
| `anl_withhold_by_state` | State × year for maps |
| `anl_withhold_yoy` | 2023 vs 2024 specialty change |
| `anl_drug_spending` | Drug × year spending (Pareto analysis) |
| `anl_provider_withhold_risk` | Provider outlier / risk bands |

## Build analytics tables

```powershell
cd E:\projects\healthcare\denial-platform\dbt
$env:POSTGRES_HOST = "localhost"
$env:POSTGRES_PASSWORD = "your_password"

dbt run --select analytics --threads 1
dbt test --select analytics
```

`anl_provider_withhold_risk` can take **15–45 minutes** (scans utilization data once, then cached as a table).

## Grant schema (first time only)

```powershell
$env:PGPASSWORD = "postgres_password"
& "E:\PostgreSQL\16\bin\psql.exe" -U postgres -d denial_db -f analytics\grant_analytics_schema.sql
```

## Notebooks

| Notebook | Focus |
|----------|--------|
| `notebooks/01_marts_eda.ipynb` | Intro EDA on marts |
| `notebooks/02_analytics_deep_dive.ipynb` | YoY, Pareto, outliers, insights |

## Power BI

See **`analytics/powerbi/POWERBI_SETUP.md`** for connection steps, report page design, and DAX measures.

## Streamlit vs Power BI

| Tool | Best for |
|------|----------|
| Streamlit | Interactive demo, portfolio link, quick filters |
| Power BI | Executive dashboards, drill-through, publishing to Power BI Service |

Both read the same `public_analytics` tables.
