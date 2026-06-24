"""Specialty-level withhold rate benchmarks."""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import marts_ready, run_query

st.set_page_config(page_title="Specialty Benchmarks", layout="wide")
st.title("Specialty Benchmarks")
st.caption("Implied withhold rate by medical specialty, state, and year")

if not marts_ready():
  st.warning("Build marts first: `cd dbt && dbt run --select marts`")
  st.stop()

years = run_query(
  """
  SELECT DISTINCT year
  FROM public_marts.fct_utilization_by_specialty
  WHERE year IS NOT NULL
  ORDER BY year
  """
)["year"].tolist()

states = run_query(
  """
  SELECT DISTINCT state
  FROM public_marts.fct_utilization_by_specialty
  ORDER BY state
  """
)["state"].tolist()

col1, col2, col3 = st.columns(3)
with col1:
  year = st.selectbox("Year", years, index=len(years) - 1 if years else 0)
with col2:
  state = st.selectbox("State", ["All"] + states)
with col3:
  top_n = st.slider("Top N specialties", 5, 25, 15)


@st.cache_data(ttl=600)
def load_specialty_benchmarks(year_value: int, state_value: str | None, limit: int):
  params = {"year": year_value, "limit": limit}
  state_filter = ""
  if state_value:
    state_filter = "AND state = :state"
    params["state"] = state_value

  return run_query(
    f"""
    SELECT
      specialty,
      state,
      year,
      provider_count,
      total_services,
      avg_withhold_rate,
      median_withhold_rate
    FROM public_marts.fct_utilization_by_specialty
    WHERE year = :year
      {state_filter}
    ORDER BY avg_withhold_rate DESC
    LIMIT :limit
    """,
    params,
  )


params_state = None if state == "All" else state
df = load_specialty_benchmarks(int(year), params_state, top_n)

if df.empty:
  st.info("No data for the selected filters.")
  st.stop()

fig = px.bar(
  df,
  x="avg_withhold_rate",
  y="specialty",
  orientation="h",
  color="avg_withhold_rate",
  color_continuous_scale="Reds",
  labels={"avg_withhold_rate": "Avg withhold rate", "specialty": "Specialty"},
  title=f"Top specialties by withhold rate ({year}{', ' + state if state != 'All' else ''})",
)
fig.update_layout(height=500, yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig, use_container_width=True)

st.subheader("Detail table")
st.dataframe(
  df.style.format(
    {
      "avg_withhold_rate": "{:.2%}",
      "median_withhold_rate": "{:.2%}",
      "provider_count": "{:,.0f}",
      "total_services": "{:,.0f}",
    }
  ),
  use_container_width=True,
)
