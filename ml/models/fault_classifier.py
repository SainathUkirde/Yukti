"""
ml/models/fault_classifier.py
Dynamometer card fault classifier.

Classes: normal, rod_floating, pump_off, gas_interference, fluid_pound, pump_unsetting
Default model: LightGBM (fast, CPU-only, feature-based).
Optional CNN: behind USE_CNN_CLASSIFIER=true env flag (requires torch).

Input: extracted dyno card features (31 features from dyno_features.py).
Output: predicted class + class probabilities + top contributing features.

Metrics reported: F1 (macro + per-class), confusion matrix, accuracy.
"""
import numpy as np
import pandas as pd
import joblib
import os
from pathlib import Path
from typing import Optional

try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    f1_score, accuracy_score, confusion_matrix, classification_report
)

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "models" / "artifacts"

FAULT_CLASSES = [
    "normal",
    "rod_floating",
    "pump_off",
    "gas_interference",
    "fluid_pound",
    "pump_unsetting",
]


def _make_lgb_classifier() -> "lgb.LGBMClassifier":
    return lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        max_depth=6,
        num_leaves=40,
        min_child_samples=15,
        subsample=0.85,
        colsample_bytree=0.85,
        class_weight="balanced",
        random_state=42,
        verbose=-1,
    )


def _make_rf_classifier() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        min_samples_leaf=5,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )


class DynoFaultClassifier:
    """
    Feature-based dynamometer card fault classifier.

    Default backend: LightGBM (if available), else RandomForest.
    Input: 31-dimensional feature vector from extract_features().
    """

    def __init__(self) -> None:
        self.model = None
        self.label_encoder = LabelEncoder()
        self.feature_names: list[str] = []
        self.metrics: dict = {}
        self._fitted = False

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[list[str]] = None,
        eval_fraction: float = 0.20,
    ) -> dict:
        """
        Train the fault classifier.

        Parameters
        ----------
        X : np.ndarray  shape (n_samples, n_features)
        y : np.ndarray  string class labels
        feature_names : list of feature names (for explainability)
        eval_fraction : held-out fraction for evaluation

        Returns
        -------
        dict   metrics: {accuracy, f1_macro, f1_per_class, confusion_matrix}
        """
        from sklearn.model_selection import train_test_split

        if feature_names is not None:
            self.feature_names = feature_names

        y_enc = self.label_encoder.fit_transform(y)
        X_tr, X_val, y_tr, y_val = train_test_split(
            X, y_enc, test_size=eval_fraction, random_state=42, stratify=y_enc
        )

        self.model = _make_lgb_classifier() if _HAS_LGB else _make_rf_classifier()
        self.model.fit(X_tr, y_tr)

        y_pred = self.model.predict(X_val)
        acc = float(accuracy_score(y_val, y_pred))
        f1_macro = float(f1_score(y_val, y_pred, average="macro"))
        f1_per = f1_score(y_val, y_pred, average=None)

        classes = self.label_encoder.classes_.tolist()
        cm = confusion_matrix(y_val, y_pred).tolist()

        self.metrics = {
            "accuracy": round(acc, 4),
            "f1_macro": round(f1_macro, 4),
            "f1_per_class": {
                cls: round(float(f1_per[i]), 4)
                for i, cls in enumerate(classes)
                if i < len(f1_per)
            },
            "confusion_matrix": cm,
            "classes": classes,
            "n_train": int(len(X_tr)),
            "n_val": int(len(X_val)),
            "backend": "lightgbm" if _HAS_LGB else "random_forest",
        }
        self._fitted = True
        return self.metrics

    def predict(
        self,
        X: np.ndarray,
    ) -> tuple[str, float, dict[str, float]]:
        """
        Predict fault class for one sample.

        Returns
        -------
        (predicted_class, confidence, class_probabilities)
        """
        if X.ndim == 1:
            X = X.reshape(1, -1)
        proba = self.model.predict_proba(X)[0]
        classes = self.label_encoder.classes_
        class_probs = {cls: round(float(p), 4) for cls, p in zip(classes, proba)}
        pred_idx = int(np.argmax(proba))
        return str(classes[pred_idx]), float(proba[pred_idx]), class_probs

    def get_top_features(
        self,
        X: np.ndarray,
        top_n: int = 5,
    ) -> list[dict]:
        """
        Return top_n features contributing to the prediction.
        Uses model feature importances (scaled by input value deviation from mean).
        """
        if not self.feature_names:
            return []
        if X.ndim == 1:
            X = X.reshape(1, -1)

        # Feature importance from the model
        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
        else:
            return []

        # Weight by the input value magnitude
        weighted = importances * np.abs(X[0])
        top_idx = np.argsort(weighted)[::-1][:top_n]

        return [
            {
                "feature": self.feature_names[i] if i < len(self.feature_names) else f"feat_{i}",
                "importance": round(float(importances[i]), 4),
                "value": round(float(X[0, i]), 4),
            }
            for i in top_idx
        ]

    def save(self, directory: Optional[Path] = None) -> None:
        d = Path(directory or ARTIFACTS_DIR)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, d / "fault_classifier.joblib")
        joblib.dump(self.label_encoder, d / "fault_classifier_encoder.joblib")
        joblib.dump(self.feature_names, d / "fault_classifier_features.joblib")
        joblib.dump(self.metrics, d / "fault_classifier_metrics.joblib")

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "DynoFaultClassifier":
        d = Path(directory or ARTIFACTS_DIR)
        c = cls()
        c.model = joblib.load(d / "fault_classifier.joblib")
        c.label_encoder = joblib.load(d / "fault_classifier_encoder.joblib")
        c.feature_names = joblib.load(d / "fault_classifier_features.joblib")
        if (d / "fault_classifier_metrics.joblib").exists():
            c.metrics = joblib.load(d / "fault_classifier_metrics.joblib")
        c._fitted = True
        return c
