"""
app.py — Medicare Claim Denial Intelligence Platform Dashboard
===============================================================
Streamlit entry point. Extend this file with your analytical pages.

Run with:
  streamlit run streamlit/app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Medicare Denial Intelligence",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Medicare Claim Denial Intelligence Platform")
st.markdown(
    """
    > **Portfolio project** — end-to-end healthcare data pipeline using
    > PostgreSQL, Apache Airflow, dbt, XGBoost, and HuggingFace.
    """
)

st.info(
    "Dashboard coming soon. Run the Airflow DAG `cms_daily_ingest` first to "
    "populate the database, then add your Streamlit pages here.",
    icon="ℹ️",
)

st.subheader("Stack Status")
cols = st.columns(4)
with cols[0]:
    st.metric("PostgreSQL", "16-alpine", "running")
with cols[1]:
    st.metric("Airflow", "2.9.3", "running")
with cols[2]:
    st.metric("dbt", "1.8.9", "ready")
with cols[3]:
    st.metric("Streamlit", "1.32+", "running")
