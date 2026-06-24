"""
Medicare Claim Denial Intelligence Platform — Dashboard home page.

Run from project root:
  streamlit run streamlit/app.py
"""

import streamlit as st

from db import intermediate_ready, marts_ready, approx_row_count, run_query

st.set_page_config(
  page_title="Medicare Denial Intelligence",
  page_icon="🏥",
  layout="wide",
  initial_sidebar_state="expanded",
)


@st.cache_data(ttl=600)
def load_kpis() -> dict:
  """Load overview metrics with queries tuned for large tables."""
  if marts_ready():
    providers = approx_row_count("public_marts", "dim_providers")
    spending_rows = approx_row_count("public_marts", "fct_provider_spending")
    avg_withhold = run_query(
      """
      SELECT ROUND(AVG(avg_withhold_rate)::numeric, 4) AS rate
      FROM public_marts.fct_utilization_by_specialty
      """
    ).iloc[0, 0]
  else:
    providers = approx_row_count("public_intermediate", "int_providers")
    spending_rows = approx_row_count("raw", "cms_part_d_spending")
    avg_withhold = None

  utilization_rows = approx_row_count("raw", "cms_provider_utilization")

  return {
    "providers": providers,
    "utilization_rows": utilization_rows,
    "spending_rows": spending_rows,
    "avg_withhold": avg_withhold,
  }


st.title("Medicare Claim Denial Intelligence Platform")
st.caption(
  "End-to-end healthcare analytics — PostgreSQL, dbt, CMS public data, Streamlit"
)

st.markdown(
  """
  This dashboard surfaces **implied withhold rates** from Medicare utilization data —
  a transparent proxy for payment gaps that may reflect denials or adjustments.
  """
)

if not intermediate_ready():
  st.error(
    "Intermediate dbt models not found. Run:\n\n"
    "`cd dbt && dbt run --select intermediate`"
  )
  st.stop()

if not marts_ready():
  st.warning(
    "Marts are not built yet. Overview KPIs from marts will be limited.\n\n"
    "Run: `cd dbt && dbt run --select marts`"
  )

col1, col2, col3, col4 = st.columns(4)

try:
  with st.spinner("Loading KPIs (first load may take a minute)..."):
    kpis = load_kpis()

  col1.metric("Providers", f"{kpis['providers']:,}")
  col2.metric("Utilization rows", f"{kpis['utilization_rows']:,}")
  col3.metric("Spending rows", f"{kpis['spending_rows']:,}")
  rate = kpis["avg_withhold"]
  col4.metric("Avg withhold rate", f"{rate:.2%}" if rate is not None else "—")

except Exception as exc:
  st.error(f"Could not load KPIs: {exc}")
  st.info("Check PostgreSQL is running and `.env` has POSTGRES_HOST=localhost")

st.caption("Row counts are approximate Postgres statistics for fast loading.")

st.divider()
st.subheader("Pipeline status")
status = st.columns(5)
layers = [
  ("Raw", True),
  ("Staging", True),
  ("Intermediate", intermediate_ready()),
  ("Marts", marts_ready()),
  ("Dashboard", True),
]
for col, (name, ok) in zip(status, layers):
  col.metric(name, "Ready" if ok else "Pending")

st.divider()
st.markdown(
  """
  **Use the sidebar pages to explore:**
  - **Specialty Benchmarks** — withhold rates by specialty and state
  - **Drug Spending** — top Part D drugs and costs
  - **Provider Lookup** — search providers by NPI or name
  """
)
