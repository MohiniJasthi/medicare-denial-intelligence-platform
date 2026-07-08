"""ML model results — metrics, SHAP, and training instructions."""

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(page_title="ML Insights", layout="wide")
st.title("ML — Withhold Risk Classifier")
st.caption("XGBoost model predicting high withhold risk vs specialty median")

ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts"
METRICS_FILE = ARTIFACTS / "metrics.json"
SHAP_FILE = ARTIFACTS / "shap_summary.png"
REPORT_FILE = ARTIFACTS / "classification_report.txt"
MODEL_FILE = ARTIFACTS / "withhold_classifier.joblib"
DEMO_METRICS = {
    "roc_auc": 0.7418,
    "train_year": 2023,
    "test_year": 2024,
    "test_rows": 640038,
}

st.markdown(
    """
    This page shows results from **`ml/train_withhold_classifier.py`**:
    - **Target:** provider-year classified as **High** withhold risk
    - **Train:** 2023 | **Test:** 2024
    - **Features:** specialty, state, volume, payments, specialty median
    """
)

if METRICS_FILE.exists():
    metrics = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
else:
    st.info(
        "Running in demo mode on Streamlit Cloud: local training artifacts are not "
        "packaged with deployment."
    )
    st.code(
        """
cd E:\\projects\\healthcare\\denial-platform
.\\.venv\\Scripts\\Activate.ps1
$env:POSTGRES_HOST = "localhost"
python ml/train_withhold_classifier.py
        """.strip(),
        language="powershell",
    )
    metrics = DEMO_METRICS

col1, col2, col3, col4 = st.columns(4)
col1.metric("ROC-AUC", f"{metrics.get('roc_auc', 0):.3f}")
col2.metric("Train year", metrics.get("train_year", "—"))
col3.metric("Test year", metrics.get("test_year", "—"))
col4.metric("Test rows", f"{metrics.get('test_rows', 0):,}")

st.subheader("Model performance")
if REPORT_FILE.exists():
    st.text(REPORT_FILE.read_text(encoding="utf-8"))
else:
    st.warning("Classification report not found.")

st.subheader("SHAP — feature importance")
if SHAP_FILE.exists():
    st.image(str(SHAP_FILE), use_container_width=True)
    st.caption(
        "SHAP values show which features push predictions toward high withhold risk."
    )
else:
    st.warning("SHAP plot not found. Re-run training to generate.")

st.subheader("Artifacts")
st.markdown(
    f"""
| File | Status |
|------|--------|
| `metrics.json` | {'✅' if METRICS_FILE.exists() else '❌'} |
| `withhold_classifier.joblib` | {'✅' if MODEL_FILE.exists() else '❌'} |
| `shap_summary.png` | {'✅' if SHAP_FILE.exists() else '❌'} |
| `classification_report.txt` | {'✅' if REPORT_FILE.exists() else '❌'} |
    """
)

with st.expander("How to interpret results"):
    st.markdown(
        """
        - **ROC-AUC > 0.7** — reasonable discrimination for a portfolio baseline
        - **High recall on High class** — catches more at-risk providers (may trade off precision)
        - **Top SHAP features** — often `specialty_median_withhold`, `total_services`, `cms_specialty`
        - This is a **proxy model** on public CMS data — not a production clinical billing model
        """
    )
