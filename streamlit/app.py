"""
Medicare Claim Denial Intelligence Platform — Dashboard home page.

Run from project root:
  streamlit run streamlit/app.py
"""

import streamlit as st

from db import intermediate_ready, marts_ready, run_query

st.set_page_config(
  page_title="Medicare Denial Intelligence",
  page_icon="🏥",
  layout="wide",
  initial_sidebar_state="expanded",
)

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
  providers = run_query(
    "SELECT COUNT(*) AS n FROM public_marts.dim_providers"
    if marts_ready()
    else "SELECT COUNT(*) AS n FROM public_intermediate.int_providers"
  ).iloc[0, 0]

  utilization_rows = run_query(
    "SELECT COUNT(*) AS n FROM public_intermediate.int_utilization_enriched"
  ).iloc[0, 0]

  spending_rows = run_query(
    "SELECT COUNT(*) AS n FROM public_marts.fct_provider_spending"
    if marts_ready()
    else "SELECT COUNT(*) AS n FROM public_intermediate.int_spending_enriched"
  ).iloc[0, 0]

  if marts_ready():
    avg_withhold = run_query(
      """
      SELECT ROUND(AVG(avg_withhold_rate)::numeric, 4) AS rate
      FROM public_marts.fct_utilization_by_specialty
      """
    ).iloc[0, 0]
  else:
    avg_withhold = run_query(
      """
      SELECT ROUND(AVG(implied_withhold_rate)::numeric, 4) AS rate
      FROM public_intermediate.int_utilization_enriched
      WHERE implied_withhold_rate IS NOT NULL
      """
    ).iloc[0, 0]

  col1.metric("Providers", f"{int(providers):,}")
  col2.metric("Utilization rows", f"{int(utilization_rows):,}")
  col3.metric("Spending rows", f"{int(spending_rows):,}")
  col4.metric("Avg withhold rate", f"{avg_withhold:.2%}" if avg_withhold else "—")

except Exception as exc:
  st.error(f"Could not load KPIs: {exc}")
  st.info("Check Docker is running and `.env` has POSTGRES_HOST=localhost")

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
