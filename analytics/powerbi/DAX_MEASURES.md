# Power BI — DAX Measures Reference

Copy these into **Power BI Desktop → Modeling → New measure**.

---

## On `anl_withhold_national`

```dax
Avg Withhold % =
AVERAGEX(
    anl_withhold_national,
  anl_withhold_national[weighted_avg_withhold_rate]
)
```

```dax
Total Services =
SUM(anl_withhold_national[total_services])
```

```dax
Total Providers =
SUM(anl_withhold_national[provider_count])
```

---

## On `anl_withhold_yoy`

```dax
Specialties Worsening =
COUNTROWS(
    FILTER(
        anl_withhold_yoy,
        anl_withhold_yoy[withhold_rate_change] > 0
    )
)
```

```dax
Avg YoY Withhold Change =
AVERAGE(anl_withhold_yoy[withhold_rate_change])
```

```dax
Largest YoY Increase =
MAXX(anl_withhold_yoy, anl_withhold_yoy[withhold_rate_change])
```

---

## On `anl_provider_withhold_risk`

```dax
High Risk Provider Count =
CALCULATE(
    COUNTROWS(anl_provider_withhold_risk),
    anl_provider_withhold_risk[withhold_risk_band] = "High"
)
```

```dax
High Risk Provider % =
DIVIDE(
    [High Risk Provider Count],
    COUNTROWS(anl_provider_withhold_risk),
    0
)
```

```dax
Avg Withhold vs Median =
AVERAGE(anl_provider_withhold_risk[withhold_vs_median])
```

---

## On `anl_drug_spending`

```dax
Total Part D Cost =
SUM(anl_drug_spending[total_medicare_cost])
```

```dax
Total Claims =
SUM(anl_drug_spending[total_claims])
```

```dax
Top 10 Drug Cost Share % =
VAR Top10Cost =
    CALCULATE(
        SUM(anl_drug_spending[total_medicare_cost]),
        TOPN(
            10,
            ALL(anl_drug_spending[drug_name]),
            CALCULATE(SUM(anl_drug_spending[total_medicare_cost])),
            DESC
        )
    )
VAR TotalCost = SUM(anl_drug_spending[total_medicare_cost])
RETURN DIVIDE(Top10Cost, TotalCost, 0)
```

---

## On `anl_kpi_overview` (if loaded)

```dax
National Avg Withhold =
MAX(anl_kpi_overview[national_avg_withhold_rate])
```

```dax
Total Providers KPI =
MAX(anl_kpi_overview[provider_count])
```

---

## Format strings

After creating measures, set format:
- Rates → **Percentage** (e.g. `0.00%`)
- Costs → **Currency** `$ #,0`
