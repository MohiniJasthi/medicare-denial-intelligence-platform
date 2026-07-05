# Power BI — Click-by-Click Build Walkthrough

Use this guide **after** your 6 `public_analytics` tables are loaded in Power BI.

**Stuck on connection?** Run `export_for_powerbi.py` (see bottom) and use **Get data → Text/CSV** instead.

---

## Before you start (2 minutes)

1. Open Power BI Desktop with your data loaded.
2. Left sidebar: click **Report** view (bar chart icon).
3. Right side: **Visualizations** pane (icons for chart types).
4. Right side below that: **Data** pane (field list).
5. Bottom: tabs for pages — double-click **Page 1** → rename pages as you go.

**Tip:** If you don't see Data / Visualizations panes: **View → Show panes**.

---

## Format fields once (saves time later)

In **Data** pane, click a table name → **Column tools** ribbon:

| Table | Column | Format |
|-------|--------|--------|
| `anl_kpi_overview` | `national_avg_withhold_rate` | **Percentage** (2 decimals) |
| `anl_kpi_overview` | `total_part_d_cost` | **Currency** $ |
| `anl_withhold_national` | `weighted_avg_withhold_rate` | **Percentage** |
| `anl_withhold_by_state` | `weighted_avg_withhold_rate` | **Percentage** |
| `anl_withhold_yoy` | `withhold_rate_2023`, `withhold_rate_2024`, `withhold_rate_change` | **Percentage** |
| `anl_drug_spending` | `total_medicare_cost` | **Currency** $ |

---

# PAGE 1 — Executive Overview

### Rename page
Double-click **Page 1** tab → type: `Executive Overview`

### Add title
1. **Insert → Text box**
2. Type: `Medicare Denial Intelligence — Executive Summary`
3. Font size **18**, bold.

### Card 1 — Providers
1. Click blank canvas.
2. **Visualizations → Card** (number icon).
3. From **anl_kpi_overview**, drag **`provider_count`** into the **Fields** well (or "Add data fields here").
4. Click the card → **Format visual** (paint roller) → **Category label** → rename to `Providers`.

### Card 2 — Part D cost
1. Click empty space → add another **Card**.
2. Drag **`total_part_d_cost`** from `anl_kpi_overview`.
3. Label: `Total Part D Cost`.

### Card 3 — Avg withhold
1. New **Card** → drag **`national_avg_withhold_rate`**.
2. Label: `National Avg Withhold Rate`.
3. Confirm it shows as **%** (e.g. 12.34%).

### Card 4 — Distinct drugs
1. New **Card** → drag **`distinct_drugs`**.
2. Label: `Distinct Part D Drugs`.

### Arrange cards
Select all 4 cards → drag into one row at top. Use **View → Snap to grid**.

### Optional slicer (year)
1. **Visualizations → Slicer**.
2. Drag **`year`** from **`anl_withhold_national`** into the slicer field.
3. Resize at bottom of page.

**Page 1 done.**

---

# PAGE 2 — Withhold by Specialty

### New page
**Home → Insert → New page** → rename: `Specialty Benchmarks`

### Slicer — Year
1. Add **Slicer** → field **`year`** from `anl_withhold_national`.
2. Select **2024** (or use dropdown style: Format → Slicer settings → Style → Dropdown).

### Bar chart — Top specialties
1. Click canvas → **Clustered bar chart** (horizontal bars).
2. Drag fields into wells:

| Well | Field |
|------|-------|
| **Y-axis** | `specialty` |
| **X-axis** | `weighted_avg_withhold_rate` |
| **Legend** | `year` (optional — remove if too busy) |

3. **Filters on this visual** (pane with funnel icon):
   - Drag **`year`** → filter to **2024** only.
4. **Top N filter** (important — specialties are many):
   - In visual filters, **`specialty`** → **Filter type: Top N**
   - **Show items: Top 15**
   - **By value:** drag `weighted_avg_withhold_rate` into "By value" area.
5. **Format visual → General → title** → `Top 15 Specialties by Withhold Rate`.

### Table — detail
1. Add **Table** visual below chart.
2. Drag columns from `anl_withhold_national`:
   - `specialty`, `year`, `provider_count`, `total_services`, `weighted_avg_withhold_rate`
3. Sort by `weighted_avg_withhold_rate` descending (click column header in visual).

**Page 2 done.**

---

# PAGE 3 — Geographic (State Map)

### New page → rename: `Geographic Analysis`

### Slicer
**Slicer** → `year` from **`anl_withhold_by_state`** → select **2024**.

### Filled map
1. **Visualizations → Map** (or **Filled map** if available).
2. If you see **Map** with latitude/longitude only, use **Filled map** (globe with regions).

**For Filled map:**

| Well | Field |
|------|-------|
| **Location** | `state` |
| **Legend** | (leave empty) |
| **Values** | `weighted_avg_withhold_rate` |

3. **Format → Data colors** → gradient (light = low, dark red = high).

**If map doesn't recognize states:**
1. Select `state` column in **Data** pane.
2. **Column tools → Data category → State or Province**.

**Alternative if map fails:** use **Clustered bar chart**:
- Y-axis: `state`, X-axis: `weighted_avg_withhold_rate`, Top 15 filter.

### Table — top states
**Table** with `state`, `year`, `weighted_avg_withhold_rate`, `provider_count` — sort by withhold rate desc, filter Top 10 states.

**Page 3 done.**

---

# PAGE 4 — Year over Year (2023 vs 2024)

### New page → rename: `YoY Change`

Data table: **`anl_withhold_yoy`** only.

### Scatter chart
1. **Scatter chart** visual.
2. Wells:

| Well | Field |
|------|-------|
| **X-axis** | `withhold_rate_2023` |
| **Y-axis** | `withhold_rate_2024` |
| **Details** | `specialty` |

3. Title: `Specialty Withhold: 2023 vs 2024`
4. Add **reference line** (optional): Format → Analytics → X-axis constant line at 0, Y constant line — or draw diagonal manually with line chart alternative.

**Interpretation:** Points **above** the diagonal = higher withhold in 2024.

### Bar chart — biggest increases
1. **Clustered bar chart**.
2. Y-axis: `specialty`, X-axis: `withhold_rate_change`.
3. Filter **Top 15** by `withhold_rate_change` descending.
4. Title: `Largest Withhold Rate Increases (2023→2024)`.

### Card — specialties worsening
1. **Modeling → New measure** (or right-click `anl_withhold_yoy` → New measure):

```dax
Specialties Worsening =
COUNTROWS(
    FILTER(
        anl_withhold_yoy,
        anl_withhold_yoy[withhold_rate_change] > 0
    )
)
```

2. Add **Card** → drag measure **`Specialties Worsening`**.
3. Label: `Specialties with higher withhold in 2024`.

**Page 4 done.**

---

# PAGE 5 — Part D Drug Spending

### New page → rename: `Drug Spending`

### Slicer
**Slicer** → `year` from **`anl_drug_spending`** → **2024**.

### Bar chart — top drugs
1. **Clustered bar chart**.
2. Y-axis: `drug_name`, X-axis: `total_medicare_cost`.
3. Visual filter: `year` = 2024.
4. **Top N:** Top **20** by `total_medicare_cost`.
5. Title: `Top 20 Drugs by Medicare Cost`.

### Card — total cost
**New measure** on `anl_drug_spending`:

```dax
Total Part D Cost =
SUM(anl_drug_spending[total_medicare_cost])
```

**Card** with that measure (respects year slicer).

### Table
Columns: `drug_name`, `total_medicare_cost`, `total_claims`, `prescriber_count` — Top 20 filter.

**Page 5 done.**

---

# PAGE 6 — Provider Risk (optional)

### New page → rename: `Provider Risk`

**Warning:** Large table — always use filters.

### Slicer row
1. Slicer: `year` from `anl_provider_withhold_risk` → **2024**
2. Slicer: `withhold_risk_band` → select **High** only

### Donut chart
1. **Donut chart**.
2. **Legend:** `withhold_risk_band`
3. **Values:** drag `npi` → change aggregation to **Count (Distinct)**.
   - Click `npi` in Values well → **Count (Distinct)**.

### Table — top outliers
1. **Table** visual.
2. Columns: `npi`, `provider_name`, `cms_specialty`, `provider_state`, `avg_withhold_rate`, `specialty_median_withhold`, `withhold_vs_median`
3. **Filters on visual:**
   - `withhold_risk_band` = High
   - `year` = 2024
   - **Top 100** by `withhold_vs_median` descending

**Page 6 done.**

---

## Final polish

1. **View → Mobile layout** (optional).
2. **View → Themes** → pick a clean theme.
3. **File → Save as** → `Medicare_Denial_Intelligence.pbix` in `analytics/powerbi/`.
4. **File → Export → PDF** for portfolio screenshots.

---

## Common problems

| Problem | Fix |
|---------|-----|
| Field won't drag to axis | Check data type (numbers on Values, text on Axis). |
| Chart shows "blank" | Remove conflicting filters; check slicer year matches data. |
| Too many bars | Use **Top N** visual filter. |
| Percent shows as 0.12 not 12% | Column tools → Format → Percentage. |
| Map empty | Set `state` Data category to **State**; use bar chart fallback. |
| `anl_provider_withhold_risk` slow | Filter `year` first; never load full table unfiltered. |

---

## Fallback: CSV import (no PostgreSQL connector)

```powershell
cd E:\projects\healthcare\denial-platform
.\.venv\Scripts\Activate.ps1
$env:POSTGRES_HOST = "localhost"
python analytics/powerbi/export_for_powerbi.py
```

Then in Power BI: **Get data → Text/CSV** → select all files in `analytics/powerbi/csv/` → **Load**.

Build the same pages using identical column names.

---

## Minimum viable dashboard (30 minutes)

If short on time, build only:

1. **Executive** — 4 cards from `anl_kpi_overview`
2. **Specialty** — 1 bar chart Top 15
3. **Drugs** — 1 bar chart Top 20

That's enough for a portfolio screenshot set.

---

## Need help?

Tell me which **page number** you're on and what you see (blank visual, error message, or missing field) — we can debug that exact step.
