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

years = run_query(
  f"""
  SELECT DISTINCT year
  FROM {table}
  WHERE year IS NOT NULL
  ORDER BY year
  """
)["year"].tolist()

year = st.selectbox("Year", years, index=len(years) - 1 if years else 0)
top_n = st.slider("Top N drugs", 10, 50, 20)

df = run_query(
  f"""
  SELECT
    drug_name,
    SUM(total_claim_count) AS total_claims,
    SUM(total_drug_cost) AS total_cost,
    COUNT(DISTINCT npi) AS prescriber_count
  FROM {table}
  WHERE year = :year
    AND drug_name IS NOT NULL
  GROUP BY drug_name
  ORDER BY total_cost DESC
  LIMIT :limit
  """,
  {"year": int(year), "limit": top_n},
)

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
