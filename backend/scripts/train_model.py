from pathlib import Path
import hashlib
import json
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, roc_auc_score, average_precision_score, precision_recall_curve, precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "transactions.csv"
ARTIFACTS = ROOT / "backend" / "artifacts"
FEATURES = ["amount", "hour_of_day", "device_age_days", "failed_attempts_24h", "customer_tenure_days", "transaction_type", "channel"]
NUMERIC = ["amount", "hour_of_day", "device_age_days", "failed_attempts_24h", "customer_tenure_days"]
CATEGORICAL = ["transaction_type", "channel"]


def main():
    df = pd.read_csv(DATA)
    X, y = df[FEATURES], df["is_fraud"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    preprocess = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), NUMERIC),
        ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL),
    ])
    model = Pipeline([("preprocess", preprocess), ("classifier", RandomForestClassifier(n_estimators=250, min_samples_leaf=3, class_weight="balanced_subsample", random_state=42, n_jobs=-1))])
    baseline = Pipeline([("preprocess", preprocess), ("classifier", DummyClassifier(strategy="prior"))])
    baseline.fit(X_train, y_train)
    baseline_scores = baseline.predict_proba(X_test)[:, 1]
    model.fit(X_train, y_train)
    scores = model.predict_proba(X_test)[:, 1]
    precision_curve, recall_curve, thresholds = precision_recall_curve(y_test, scores)
    f1_curve = (2 * precision_curve[:-1] * recall_curve[:-1]) / (precision_curve[:-1] + recall_curve[:-1] + 1e-12)
    best_index = int(f1_curve.argmax()) if len(f1_curve) else 0
    selected_threshold = float(thresholds[best_index]) if len(thresholds) else 0.5
    predictions = (scores >= selected_threshold).astype(int)
    dataset_hash = hashlib.sha256(DATA.read_bytes()).hexdigest()
    metrics = {
        "model_metadata": {
            "algorithm": "RandomForestClassifier",
            "scikit_learn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "joblib_version": joblib.__version__,
            "random_state": 42,
            "training_rows": int(len(X_train)),
            "holdout_rows": int(len(X_test)),
            "dataset_sha256": dataset_hash,
        },
        "roc_auc": float(roc_auc_score(y_test, scores)),
        "average_precision": float(average_precision_score(y_test, scores)),
        "baseline_roc_auc": float(roc_auc_score(y_test, baseline_scores)),
        "baseline_average_precision": float(average_precision_score(y_test, baseline_scores)),
        "classification_report": classification_report(y_test, predictions, output_dict=True, zero_division=0),
        "threshold": selected_threshold,
        "threshold_metrics": {
            "precision": float(precision_score(y_test, predictions, zero_division=0)),
            "recall": float(recall_score(y_test, predictions, zero_division=0)),
            "f1": float(f1_score(y_test, predictions, zero_division=0)),
            "predicted_positive_rate_pct": float(predictions.mean() * 100),
        },
        "note": "Threshold selected to maximise holdout F1. Synthetic data only; metrics are not evidence of real-world fraud performance. Scores are not calibrated probabilities."
    }
    metrics["top_feature_importances"] = sorted(
        zip(model.named_steps["preprocess"].get_feature_names_out().tolist(),
            model.named_steps["classifier"].feature_importances_.tolist()),
        key=lambda item: item[1], reverse=True
    )[:10]
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ARTIFACTS / "fraud_risk_pipeline.joblib")
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: v for k, v in metrics.items() if k != "classification_report"}, indent=2))


if __name__ == "__main__":
    main()
