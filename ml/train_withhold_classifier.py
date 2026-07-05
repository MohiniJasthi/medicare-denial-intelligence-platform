#!/usr/bin/env python3
"""
Train an XGBoost classifier to predict high withhold risk at the provider level.

Uses public_analytics.anl_provider_withhold_risk (built by dbt).

Target: withhold_risk_band == 'High' (provider avg withhold > specialty median)

Usage (from project root, venv active):
  python ml/train_withhold_classifier.py
  python ml/train_withhold_classifier.py --train-year 2023 --test-year 2024
  python ml/train_withhold_classifier.py --sample 200000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from dotenv import load_dotenv
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

ARTIFACTS_DIR = PROJECT_ROOT / "ml" / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "withhold_classifier.joblib"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
SHAP_PATH = ARTIFACTS_DIR / "shap_summary.png"
REPORT_PATH = ARTIFACTS_DIR / "classification_report.txt"

FEATURE_COLS = [
    "cms_specialty",
    "provider_state",
    "year",
    "service_line_count",
    "total_services",
    "avg_medicare_payment",
    "specialty_median_withhold",
]
TARGET_COL = "is_high_risk"
CATEGORICAL = ["cms_specialty", "provider_state"]


def get_engine():
    user = os.getenv("POSTGRES_USER", "denial_user")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "denial_db")
    if not password:
        raise ValueError("POSTGRES_PASSWORD is not set in .env")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    )


def load_data(train_year: int, test_year: int, sample: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    sql = text(
        """
        SELECT
            cms_specialty,
            provider_state,
            year,
            service_line_count,
            total_services,
            avg_medicare_payment,
            specialty_median_withhold,
            withhold_risk_band
        FROM public_analytics.anl_provider_withhold_risk
        WHERE year IN (:train_year, :test_year)
          AND withhold_risk_band IN ('High', 'Low')
        """
    )
    with get_engine().connect() as conn:
        df = pd.read_sql(sql, conn, params={"train_year": train_year, "test_year": test_year})

    if df.empty:
        raise RuntimeError(
            "No rows returned. Run: cd dbt && dbt run --select anl_provider_withhold_risk"
        )

    df[TARGET_COL] = (df["withhold_risk_band"] == "High").astype(int)

    train_df = df[df["year"] == train_year].copy()
    test_df = df[df["year"] == test_year].copy()

    if sample and len(train_df) > sample:
        train_df = train_df.sample(n=sample, random_state=42)
        log.info("Sampled training set to %s rows", f"{sample:,}")

    log.info("Train rows: %s | Test rows: %s", f"{len(train_df):,}", f"{len(test_df):,}")
    log.info("Train high-risk rate: %.1f%%", 100 * train_df[TARGET_COL].mean())
    return train_df, test_df


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", max_categories=50),
                CATEGORICAL,
            ),
        ],
        remainder="passthrough",
    )
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    return Pipeline(steps=[("prep", preprocessor), ("model", model)])


def _encoded_feature_names(prep: ColumnTransformer) -> list[str]:
    cat_encoder = prep.named_transformers_["cat"]
    cat_names = list(cat_encoder.get_feature_names_out(CATEGORICAL))
    return cat_names + [c for c in FEATURE_COLS if c not in CATEGORICAL]


def _patch_xgboost_for_shap(model: xgb.XGBClassifier) -> None:
    """Fix XGBoost 2.x base_score bracket string for SHAP TreeExplainer."""
    try:
        booster = model.get_booster()
        config = json.loads(booster.save_config())
        learner = config.get("learner", {})
        param = learner.get("learner_model_param", {})
        base_score = param.get("base_score", "")
        if isinstance(base_score, str) and base_score.startswith("["):
            param["base_score"] = base_score.strip("[]")
            booster.load_config(json.dumps(config))
    except Exception as exc:
        log.warning("XGBoost SHAP patch skipped: %s", exc)


def save_importance_fallback(
    pipeline: Pipeline, X_sample: pd.DataFrame, feature_names: list[str]
) -> None:
    """Fallback chart when SHAP TreeExplainer fails (XGBoost version mismatch)."""
    prep = pipeline.named_steps["prep"]
    model = pipeline.named_steps["model"]
    xgb.plot_importance(model, max_num_features=15, importance_type="gain")
    plt.title("XGBoost feature importance (gain)")
    plt.tight_layout()
    plt.savefig(SHAP_PATH, dpi=120, bbox_inches="tight")
    plt.close()
    log.info("Feature importance plot saved (SHAP fallback): %s", SHAP_PATH)


def save_shap_plot(pipeline: Pipeline, X_sample: pd.DataFrame) -> None:
    """SHAP summary for tree model on encoded features."""
    prep = pipeline.named_steps["prep"]
    model = pipeline.named_steps["model"]
    X_enc = prep.transform(X_sample)
    feature_names = _encoded_feature_names(prep)

    _patch_xgboost_for_shap(model)

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_enc)

        sample_size = min(2000, X_enc.shape[0])
        shap.summary_plot(
            shap_values,
            X_enc[:sample_size],
            feature_names=feature_names,
            show=False,
            max_display=15,
        )
        plt.tight_layout()
        plt.savefig(SHAP_PATH, dpi=120, bbox_inches="tight")
        plt.close()
        log.info("SHAP plot saved: %s", SHAP_PATH)
    except Exception as exc:
        log.warning("SHAP TreeExplainer failed (%s). Using XGBoost importance plot.", exc)
        save_importance_fallback(pipeline, X_sample, feature_names)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train withhold risk classifier")
    parser.add_argument("--train-year", type=int, default=2023)
    parser.add_argument("--test-year", type=int, default=2024)
    parser.add_argument(
        "--sample",
        type=int,
        default=300_000,
        help="Max training rows (default 300k for laptop-friendly runtime)",
    )
    parser.add_argument(
        "--shap-only",
        action="store_true",
        help="Skip training; regenerate SHAP/importance plot from saved model",
    )
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.shap_only:
        if not MODEL_PATH.exists():
            log.error("Model not found at %s — train first.", MODEL_PATH)
            return 1
        pipeline = joblib.load(MODEL_PATH)
        _, test_df = load_data(args.train_year, args.test_year, sample=None)
        shap_sample = test_df[FEATURE_COLS].sample(
            n=min(5000, len(test_df)), random_state=42
        )
        save_shap_plot(pipeline, shap_sample)
        return 0

    train_df, test_df = load_data(args.train_year, args.test_year, args.sample)
    X_train = train_df[FEATURE_COLS]
    y_train = train_df[TARGET_COL]
    X_test = test_df[FEATURE_COLS]
    y_test = test_df[TARGET_COL]

    log.info("Training XGBoost...")
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    y_prob = pipeline.predict_proba(X_test)[:, 1]
    y_pred = pipeline.predict(X_test)

    metrics = {
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "train_year": args.train_year,
        "test_year": args.test_year,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "roc_auc": round(float(roc_auc_score(y_test, y_prob)), 4),
        "test_high_risk_rate": round(float(y_test.mean()), 4),
    }
    report = classification_report(y_test, y_pred, digits=3)
    cm = confusion_matrix(y_test, y_pred)

    log.info("ROC-AUC: %.4f", metrics["roc_auc"])
    log.info("\n%s", report)
    log.info("Confusion matrix:\n%s", cm)

    joblib.dump(pipeline, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(report, encoding="utf-8")

    log.info("Model saved: %s", MODEL_PATH)

    shap_sample = X_test.sample(n=min(5000, len(X_test)), random_state=42)
    try:
        save_shap_plot(pipeline, shap_sample)
    except Exception as exc:
        log.warning("Explainability plot failed (model still saved): %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
