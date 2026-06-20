"""Provider search by NPI or name."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import marts_ready, run_query

st.set_page_config(page_title="Provider Lookup", layout="wide")
st.title("Provider Lookup")
st.caption("Search the NPPES provider directory and view utilization summary")

dim_table = "public_marts.dim_providers" if marts_ready() else "public_intermediate.int_providers"

search = st.text_input("Search by NPI or provider name", placeholder="e.g. 1234567890 or Smith")
min_chars = 3

if not search or len(search.strip()) < min_chars:
  st.info(f"Enter at least {min_chars} characters to search.")
  st.stop()

query = search.strip()
params: dict = {"limit": 50}

if query.isdigit():
  sql = f"""
    SELECT npi, display_name, entity_type_label, city, state,
           primary_taxonomy_code, credentials
    FROM {dim_table}
    WHERE npi LIKE :npi
    ORDER BY npi
    LIMIT :limit
  """
  params["npi"] = f"{query}%"
else:
  sql = f"""
    SELECT npi, display_name, entity_type_label, city, state,
           primary_taxonomy_code, credentials
    FROM {dim_table}
    WHERE display_name ILIKE :name
    ORDER BY display_name
    LIMIT :limit
  """
  params["name"] = f"%{query}%"

providers = run_query(sql, params)

if providers.empty:
  st.warning("No providers found.")
  st.stop()

st.subheader(f"Matches ({len(providers)})")
st.dataframe(providers, use_container_width=True)

selected_npi = st.selectbox("Select NPI for utilization detail", providers["npi"].tolist())

util = run_query(
  """
  SELECT
    cms_specialty,
    hcpcs_code,
    hcpcs_description,
    year,
    service_count,
    avg_medicare_payment,
    implied_withhold_rate
  FROM public_intermediate.int_utilization_enriched
  WHERE npi = :npi
  ORDER BY implied_withhold_rate DESC NULLS LAST
  LIMIT 25
  """,
  {"npi": selected_npi},
)

st.subheader(f"Top utilization lines for NPI {selected_npi}")
if util.empty:
  st.info("No utilization records for this provider.")
else:
  st.dataframe(
    util.style.format(
      {
        "avg_medicare_payment": "${:,.2f}",
        "implied_withhold_rate": "{:.2%}",
        "service_count": "{:,.0f}",
      }
    ),
    use_container_width=True,
  )
