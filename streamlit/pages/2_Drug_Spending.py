"""Part D drug spending analytics."""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import marts_ready, run_query

st.set_page_config(page_title="Drug Spending", layout="wide")
st.title("Part D Drug Spending")
st.caption("Medicare Part D prescribing costs by drug and year")

table = "public_marts.fct_provider_spending" if marts_ready() else "public_intermediate.int_spending_enriched"

# Avoid DISTINCT on multi-million-row fact tables (very slow).
years = run_query(
  """
  SELECT DISTINCT year
  FROM public_marts.fct_utilization_by_specialty
  WHERE year IS NOT NULL
  ORDER BY year
  """
)["year"].tolist() if marts_ready() else [2023, 2024]

year = st.selectbox("Year", years, index=len(years) - 1 if years else 0)
top_n = st.slider("Top N drugs", 10, 50, 20)


@st.cache_data(ttl=600)
def load_top_drugs(table_name: str, year_value: int, limit: int):
  return run_query(
    f"""
    SELECT
      drug_name,
      SUM(total_claim_count) AS total_claims,
      SUM(total_drug_cost) AS total_cost,
      COUNT(DISTINCT npi) AS prescriber_count
    FROM {table_name}
    WHERE year = :year
      AND drug_name IS NOT NULL
    GROUP BY drug_name
    ORDER BY total_cost DESC
    LIMIT :limit
    """,
    {"year": year_value, "limit": limit},
  )


with st.spinner("Aggregating drug spending (may take 1–2 minutes)..."):
  df = load_top_drugs(table, int(year), top_n)

if df.empty:
  st.info("No spending data for this year.")
  st.stop()

col1, col2 = st.columns([2, 1])

with col1:
  fig = px.bar(
    df,
    x="total_cost",
    y="drug_name",
    orientation="h",
    title=f"Top drugs by total Medicare cost ({year})",
    labels={"total_cost": "Total cost ($)", "drug_name": "Drug"},
  )
  fig.update_layout(height=600, yaxis={"categoryorder": "total ascending"})
  st.plotly_chart(fig, use_container_width=True)

with col2:
  total = df["total_cost"].sum()
  st.metric("Top drugs combined cost", f"${total:,.0f}")
  st.metric("Drugs shown", len(df))
  st.dataframe(
    df.style.format(
      {
        "total_cost": "${:,.0f}",
        "total_claims": "{:,.0f}",
        "prescriber_count": "{:,.0f}",
      }
    ),
    use_container_width=True,
    height=500,
  )
