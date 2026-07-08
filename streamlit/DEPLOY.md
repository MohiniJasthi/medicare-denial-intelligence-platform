# Streamlit Community Cloud — deployment guide

Your app runs on **Streamlit's servers** at [share.streamlit.io](https://share.streamlit.io).  
It **cannot** connect to Postgres on your PC (`localhost` / `E:\PostgreSQL`).

You need:
1. **Neon** (free cloud Postgres) with dashboard tables copied up
2. **Secrets** in Streamlit Cloud with Neon credentials

---

## Part A — Create Neon (5 minutes)

1. Go to [neon.tech](https://neon.tech) → sign up → **New project**
2. Name it e.g. `denial-platform`
3. Open **Dashboard → Connection details**
4. Copy the **connection string** (looks like):
   ```
   postgresql://neondb_owner:xxxxx@ep-cool-name-12345678.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

---

## Part B — Push your data from your PC (10–20 minutes)

On your Windows machine:

```powershell
cd E:\projects\healthcare\denial-platform
.\.venv\Scripts\Activate.ps1

# Load local .env (source database)
Get-Content .\.env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
    Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
  }
}
$env:POSTGRES_HOST = "localhost"

# Paste YOUR Neon connection string here
$env:NEON_DATABASE_URL = "postgresql://USER:PASSWORD@ep-xxxx.neon.tech/neondb?sslmode=require"

# Push analytics + marts tables (sampled for free tier)
python streamlit/push_to_neon.py
```

**What gets copied:**

| Schema | Tables | Streamlit pages |
|--------|--------|-----------------|
| `public_analytics` | 6 `anl_*` tables | Home KPIs, Drug Spending |
| `public_marts` | `fct_utilization_by_specialty`, `dim_providers` (sampled) | Specialty Benchmarks, Provider Lookup |
| `public_intermediate` | `int_utilization_enriched` (sampled) | Provider detail lines |

Large tables are **capped by default** for Neon free tier. Use `--full` only if you upgraded storage.

```powershell
python streamlit/push_to_neon.py --skip-intermediate   # faster; provider detail won't work
python streamlit/push_to_neon.py --dry-run               # preview only
```

---

## Part B2 — Load the *full* dataset into Neon (advanced)

You *can* load everything (raw + marts + analytics) into Neon, but be aware:

- **Size**: the project contains **84M+ raw rows**. This usually exceeds free-tier storage.
- **Cost / performance**: full loads take hours and can be expensive depending on your Neon plan.
- **Recommendation**: for Streamlit Community Cloud, the best “portfolio deployment” is:
  - **`public_analytics`** (all 6 `anl_*` tables) + **`public_marts.fct_utilization_by_specialty`**
  - optional: sampled `dim_providers` + sampled `int_utilization_enriched`

If you *still* want a full load, prefer **Postgres-native backups** over pandas `to_sql`.

### Option 1 — `pg_dump` / `pg_restore` (recommended for full load)

1. Install Postgres client tools (you already have `E:\PostgreSQL\16\bin\pg_dump.exe`).
2. Set your Neon password in the shell when prompted (do not paste it into git).

**Dump locally (custom format):**

```powershell
cd E:\projects\healthcare\denial-platform

# dump everything you want (raw can be huge)
& "E:\PostgreSQL\16\bin\pg_dump.exe" -h localhost -U denial_user -d denial_db -F c -f denial_db.dump
```

**Restore to Neon:**

```powershell
$env:PGPASSWORD = "YOUR_NEON_PASSWORD"
$neonHost = "ep-xxxx.us-east-2.aws.neon.tech"
$neonDb = "neondb"
$neonUser = "neondb_owner"

& "E:\PostgreSQL\16\bin\pg_restore.exe" -h $neonHost -U $neonUser -d $neonDb -Fc -c --if-exists denial_db.dump
```

Notes:
- `-c --if-exists` drops existing objects before restoring.
- If you only want the **analytics** layer (fast), dump just that schema:

```powershell
& "E:\PostgreSQL\16\bin\pg_dump.exe" -h localhost -U denial_user -d denial_db -n public_analytics -F c -f analytics.dump
& "E:\PostgreSQL\16\bin\pg_restore.exe" -h $neonHost -U $neonUser -d $neonDb -Fc -c --if-exists analytics.dump
```

---

## Part C — Deploy on Streamlit Community Cloud

1. Push latest code to GitHub (`.env` must **not** be in the repo)
2. [share.streamlit.io](https://share.streamlit.io) → **Create app**
3. Select repo: `medicare-denial-intelligence-platform`
4. **Main file path:** `streamlit/app.py`
5. **Branch:** `main`
6. **App URL:** pick a name e.g. `medicare-denial-intelligence`
7. Click **Deploy**

---

## Part D — Add Secrets (fixes `POSTGRES_PASSWORD is not set`)

After deploy (or if app shows the password error):

1. Open your app → **⚙️ Manage app** (bottom right)
2. **Settings** → **Secrets**
3. Paste **one** of these formats:

**Option 1 — separate fields** (from Neon connection details):

```toml
POSTGRES_USER = "neondb_owner"
POSTGRES_PASSWORD = "your_neon_password"
POSTGRES_HOST = "ep-xxxx.us-east-2.aws.neon.tech"
POSTGRES_PORT = "5432"
POSTGRES_DB = "neondb"
```

**Option 2 — single URL** (easiest — copy from Neon):

```toml
DATABASE_URL = "postgresql://neondb_owner:password@ep-xxxx.neon.tech/neondb?sslmode=require"
```

4. Click **Save** → app reboots (~1 min)

---

## Part E — Verify pages

| Page | Needs |
|------|-------|
| Home | `public_marts` + `public_intermediate` tables |
| Specialty Benchmarks | `public_marts.fct_utilization_by_specialty` |
| Drug Spending | `public_analytics.anl_drug_spending` |
| Provider Lookup | `public_marts.dim_providers` + `public_intermediate.int_utilization_enriched` |
| ML Insights | Local `ml/artifacts/` only — shows training instructions on Cloud unless you commit sample metrics |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `POSTGRES_PASSWORD is not set` | Add Secrets (Part D) — `.env` is not uploaded to Cloud |
| Connection timeout | `POSTGRES_HOST` must be Neon hostname, **not** `localhost` |
| SSL error | Use `?sslmode=require` in `DATABASE_URL` |
| Relation does not exist | Re-run `python streamlit/push_to_neon.py` |
| App reboot loop | Check Secrets TOML syntax — no extra quotes inside strings |
| Slow / timeout | Re-run push script (uses sampled data by default) |

---

## Quick reference

```powershell
# Local dev
streamlit run streamlit/app.py

# Sync to Neon
$env:NEON_DATABASE_URL = "postgresql://..."
python streamlit/push_to_neon.py

# Streamlit Cloud secrets → same Neon host/user/password as above
```
