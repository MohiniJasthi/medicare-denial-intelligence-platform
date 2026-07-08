"""Part D drug spending analytics."""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import analytics_ready, marts_ready, run_query

st.set_page_config(page_title="Drug Spending", layout="wide")
st.title("Part D Drug Spending")
st.caption("Medicare Part D prescribing costs by drug and year")

if not analytics_ready():
  if marts_ready():
    st.warning(
      "Build the analytics layer for fast drug rankings: "
      "`cd dbt && dbt run --select anl_drug_spending`"
    )
  else:
    st.warning("Build marts first: `cd dbt && dbt run --select marts analytics`")
  st.stop()

years = run_query(
  """
  SELECT DISTINCT year
  FROM public_analytics.anl_drug_spending
  WHERE year IS NOT NULL
  ORDER BY year
  """
)["year"].tolist()

year = st.selectbox("Year", years, index=len(years) - 1 if years else 0)
top_n = st.slider("Top N drugs", 10, 50, 20)


@st.cache_data(ttl=600)
def load_top_drugs(year_value: int, limit: int):
  # anl_drug_spending is at drug × generic × year; roll up to drug for rankings
  return run_query(
    """
    SELECT
      drug_name,
      SUM(total_claims)::bigint AS total_claims,
      SUM(total_medicare_cost)::numeric AS total_cost,
      SUM(prescriber_count)::bigint AS prescriber_count
    FROM public_analytics.anl_drug_spending
    WHERE year = :year
      AND drug_name IS NOT NULL
    GROUP BY drug_name
    ORDER BY total_cost DESC
    LIMIT :limit
    """,
    {"year": int(year_value), "limit": int(limit)},
  )


with st.spinner("Loading top drugs..."):
  df = load_top_drugs(int(year), top_n)

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
  total = float(df["total_cost"].sum())
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
