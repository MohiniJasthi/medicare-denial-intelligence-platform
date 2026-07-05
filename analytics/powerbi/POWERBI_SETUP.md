# Power BI Dashboard — Setup Guide

Build a **Medicare Denial Intelligence** dashboard connected to your local PostgreSQL analytics tables.

---

## Prerequisites

1. **Power BI Desktop** installed (free): https://powerbi.microsoft.com/desktop/
2. **PostgreSQL analytics tables built** (`dbt run --select analytics`)
3. **Npgsql** may be required — Power BI usually prompts to install the PostgreSQL connector on first connect

---

## Step 1 — Build analytics tables

```powershell
cd E:\projects\healthcare\denial-platform\dbt
$env:POSTGRES_HOST = "localhost"
$env:POSTGRES_PASSWORD = "MyDenialPass123!"

dbt run --select analytics --threads 1
dbt test --select analytics
```

Grant read access (once):

```powershell
& "E:\PostgreSQL\16\bin\psql.exe" -U postgres -d denial_db -f analytics\grant_analytics_schema.sql
```

---

## Step 2 — Connect Power BI to PostgreSQL

1. Open **Power BI Desktop**
2. **Home → Get data → Database → PostgreSQL database**
3. Enter:

| Field | Value |
|-------|-------|
| Server | `localhost` |
| Database | `denial_db` |

4. **Data Connectivity mode:**
   - **Import** (recommended) — faster visuals; refresh manually or on schedule
   - **DirectQuery** — always live; slower on large tables

5. Click **OK** → enter credentials:

| Field | Value |
|-------|-------|
| User name | `denial_user` |
| Password | (from your `.env`) |

6. In Navigator, select schema **`public_analytics`** and check these tables:

- [x] `anl_kpi_overview`
- [x] `anl_withhold_national`
- [x] `anl_withhold_by_state`
- [x] `anl_withhold_yoy`
- [x] `anl_drug_spending`
- [x] `anl_provider_withhold_risk`

Optional (drill-through detail):

- [ ] `public_marts.dim_providers`
- [ ] `public_marts.fct_utilization_by_specialty`

7. Click **Load** (or **Transform Data** if you want Power Query cleanup first)

---

## Step 3 — Data model relationships

In **Model view**, create relationships:

```
anl_withhold_national[specialty]  →  anl_withhold_yoy[specialty]     (1:1)
anl_withhold_national[year]       →  (use as slicer dimension)

anl_provider_withhold_risk[npi]   →  dim_providers[npi]              (many:1, optional)
anl_provider_withhold_risk[cms_specialty] → anl_withhold_national[specialty] (many:1, optional)
```

Most analytics tables are **standalone stars** — relationships are optional for cross-filtering.

---

## Step 4 — Recommended report pages (5 pages)

### Page 1 — Executive Overview

**Visuals:**
- **Card** × 4 from `anl_kpi_overview`:
  - `provider_count`
  - `total_part_d_cost` (format as currency)
  - `national_avg_withhold_rate` (format as %)
  - `distinct_drugs`
- **Slicer:** `year` from `anl_withhold_national`

**Title:** Medicare Denial Intelligence — Executive Summary

---

### Page 2 — Withhold by Specialty

**Visuals:**
- **Clustered bar chart:** `specialty` (Y) × `weighted_avg_withhold_rate` (X), legend = `year`
- **Table:** specialty, year, provider_count, total_services, weighted_avg_withhold_rate
- **Slicer:** `year`

**Insight question:** Which specialties have the highest implied payment withhold?

---

### Page 3 — Geographic Analysis

**Visuals:**
- **Filled map** (US states): `state` × `weighted_avg_withhold_rate`
- **Slicer:** `year`
- **Table:** Top 10 states by withhold rate

**Note:** Map needs state abbreviations (2-letter) — `anl_withhold_by_state.state` is already state codes.

---

### Page 4 — Year-over-Year Change

**Data:** `anl_withhold_yoy`

**Visuals:**
- **Scatter chart:** X = `withhold_rate_2023`, Y = `withhold_rate_2024`, details = `specialty`
- **Bar chart:** `specialty` × `withhold_rate_change` (sorted descending)
- **Card:** Count of specialties where withhold increased

**Insight question:** Which specialties got worse from 2023 to 2024?

---

### Page 5 — Part D Drug Spending

**Data:** `anl_drug_spending`

**Visuals:**
- **Bar chart:** Top 20 `drug_name` by `total_medicare_cost` (filter year)
- **Line chart:** Total cost by `year` (aggregate in visual)
- **Pareto:** Use `total_medicare_cost` with running total quick measure

**Slicer:** `year`

---

### Page 6 (optional) — Provider Risk Outliers

**Data:** `anl_provider_withhold_risk`

**Visuals:**
- **Donut chart:** `withhold_risk_band` (High / Low / At Median)
- **Table:** npi, provider_name, cms_specialty, avg_withhold_rate, specialty_median_withhold, withhold_vs_median
- **Slicers:** `year`, `cms_specialty`, `provider_state`
- **Filter:** `withhold_risk_band = High`

**Warning:** This table is large — use **Top N** filters in visuals (e.g. top 100 by `withhold_vs_median`).

---

## Step 5 — DAX measures (recommended)

Create these in the **anl_kpi_overview** or a dedicated measures table. See `DAX_MEASURES.md` for copy-paste formulas.

| Measure | Purpose |
|---------|---------|
| `Avg Withhold %` | Weighted average withhold across visuals |
| `YoY Withhold Change` | Avg change from yoy table |
| `High Risk Providers` | COUNT rows where risk band = High |
| `Top 10 Drug Share %` | Pareto concentration |

---

## Step 6 — Formatting tips

- **Withhold rates:** Format as **Percentage** with 2 decimal places
- **Currency:** `total_medicare_cost`, `total_part_d_cost` → **$ English (United States)**
- **Theme:** Use a clean light theme; red gradient for high withhold
- **Page size:** 16:9 for presentations

---

## Step 7 — Refresh data

After reloading Postgres or re-running dbt:

1. **Home → Refresh** in Power BI Desktop
2. Or **Transform data → Refresh** in Power Query

For production: publish to **Power BI Service** and configure scheduled refresh (requires on-premises data gateway for local PostgreSQL).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Cannot connect to PostgreSQL | Check `Get-Service postgresql*`; verify port 5432 |
| Tables not listed | Run `dbt run --select analytics`; check schema `public_analytics` |
| Permission denied | Run `analytics/grant_analytics_schema.sql` |
| Import very slow | Use Import only `anl_*` tables, not raw 54M row tables |
| Map not working | Ensure `state` is 2-letter US code, not full name |

---

## Verify tables exist (psql)

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public_analytics'
ORDER BY table_name;
```

---

## Portfolio tip

Export report pages as **PDF** or screenshots for README alongside Streamlit.

Save the `.pbix` file in `analytics/powerbi/` (add `*.pbix` to `.gitignore` if it contains credentials — it shouldn't if using local refresh only).
