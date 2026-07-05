# ML — Medicare Withhold Risk Classifier

Predicts whether a provider-year has **high withhold risk** (average withhold rate above specialty median).

## Prerequisites

```powershell
cd E:\projects\healthcare\denial-platform
.\.venv\Scripts\Activate.ps1

# Analytics table must exist
cd dbt
dbt run --select anl_provider_withhold_risk --threads 1
```

## Train

```powershell
cd E:\projects\healthcare\denial-platform

Get-Content .\.env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
    Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
  }
}
$env:POSTGRES_HOST = "localhost"

python ml/train_withhold_classifier.py
```

**Defaults:**
- Train on **2023**, test on **2024** (temporal split)
- Sample up to **300k** training rows (laptop-friendly)
- Target: `withhold_risk_band == High`

**Options:**

```powershell
python ml/train_withhold_classifier.py --train-year 2023 --test-year 2024 --sample 500000
```

## Outputs (`ml/artifacts/` — gitignored)

| File | Description |
|------|-------------|
| `withhold_classifier.joblib` | Trained sklearn pipeline |
| `metrics.json` | ROC-AUC, row counts |
| `classification_report.txt` | Precision / recall |
| `shap_summary.png` | Feature importance plot |

## Features

| Feature | Description |
|---------|-------------|
| `cms_specialty` | Provider specialty (one-hot encoded) |
| `provider_state` | US state |
| `year` | Claim year |
| `service_line_count` | HCPCS lines for provider-year |
| `total_services` | Total service volume |
| `avg_medicare_payment` | Avg payment per line |
| `specialty_median_withhold` | National specialty benchmark |

## Optional MLflow

```powershell
$env:MLFLOW_TRACKING_URI = "file:///E:/projects/healthcare/denial-platform/mlruns"
python ml/train_withhold_classifier.py
```

View: `mlflow ui` → http://localhost:5000

## Next steps

- Add Streamlit page showing SHAP + metrics
- Great Expectations on `raw.*` tables
- README screenshots (Streamlit + Power BI)
