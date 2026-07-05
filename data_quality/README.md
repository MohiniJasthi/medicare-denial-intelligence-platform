# Data Quality — Raw CMS Tables

Validates `raw.*` tables after ingestion (column contracts, nulls, value rules).

Uses a **lightweight pandas validator** — no Great Expectations install required.

## Run validation

```powershell
cd E:\projects\healthcare\denial-platform
.\.venv\Scripts\Activate.ps1

Get-Content .\.env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
    Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
  }
}
$env:POSTGRES_HOST = "localhost"

python data_quality/validate_raw.py
```

Single table:

```powershell
python data_quality/validate_raw.py --table cms_provider_utilization
```

## What it checks

| Table | Checks |
|-------|--------|
| `cms_part_d_spending` | Required columns, NPI/year not null, years 2023–2024 |
| `cms_provider_utilization` | Required columns, NPI format, payment/allowed ratio (WARN), years |
| `nppes_providers` | NPI not null |

Uses a **10k row sample** per table; row counts from Postgres statistics.

## When to run

- After `load_to_postgres.py`
- Before `dbt run`

## Exit codes

- `0` — all checks passed
- `1` — one or more checks failed
