"""
ml/models/failure_risk.py
Rod failure risk scorer.

Output: continuous risk score 0-100 with top contributing factors.

Model: XGBoost regressor trained on SRP operating features + Goodman ratio.
Target: risk_score_at_failure (from rod_failure_history) — transformed to
        a continuous risk signal at every operating timestep via survival-style labeling.

Labeling strategy:
  - For each day in SRP operating history, assign a risk label:
    * days within 14 days before a failure event → high risk (70-100)
    * days within 14-30 days before a failure    → medium risk (40-70)
    * all other days                             → low risk (0-40), proportional to RF/Goodman
  - This creates a continuous regression target.

Features: from SRP operating data — Goodman ratio, RF ratio, viscosity, SPM,
          cumulative float days, cycle number, temperature.
"""
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Optional

try:
    from xgboost import XGBRegressor
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "models" / "artifacts"


def _make_xgb() -> "XGBRegressor":
    return XGBRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
        tree_method="hist",   # CPU-only, fast
    )


def _make_sklearn() -> GradientBoostingRegressor:
    return GradientBoostingRegressor(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        random_state=42,
    )


RISK_FEATURE_COLS = [
    "rod_float_risk_ratio",
    "rod_float_risk_score",
    "oil_viscosity_cp",
    "spm",
    "stroke_length_m",
    "motor_power_kw",
    "kwh_per_bbl",
    "pump_fillage_fraction",
    "pump_efficiency_fraction",
    "polished_rod_load_kn",
    "min_rod_load_kn",
    "reservoir_temp_c",
    "t_production_days",
    "cycle_number",
]


def build_risk_dataset(
    srp_df: pd.DataFrame,
    failure_df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build (X, y) risk dataset by labeling SRP operating records relative to failures.

    Labels:
      - Within 14 days before a failure: risk = 70 + (14-days_before)/14 * 30
      - Within 15-30 days before a failure: risk = 40 + (30-days_before)/16 * 30
      - Other: risk = physics_proxy_score (RF + Goodman proxy, 0-40 range)

    Returns
    -------
    X : np.ndarray  (n_samples, n_features)
    y : np.ndarray  (n_samples,)  risk score 0-100
    """
    srp = srp_df.copy()
    srp["timestamp"] = pd.to_datetime(srp["timestamp"])
    srp["date"] = srp["timestamp"].dt.date

    # Compute physics-proxy risk (0-60) for non-failure days
    # Uses rod float risk ratio and viscosity as proxy
    rf_col = srp["rod_float_risk_ratio"] if "rod_float_risk_ratio" in srp.columns else pd.Series(np.zeros(len(srp)), index=srp.index)
    mu_col = srp["oil_viscosity_cp"] if "oil_viscosity_cp" in srp.columns else pd.Series(np.ones(len(srp)) * 100, index=srp.index)

    # Physics proxy: scaled combination of RF excess and viscosity excess (0-60 range)
    rf_contrib = np.clip((rf_col - 0.3) * 35.0, 0, 40)   # RF>0.3 starts contributing
    mu_contrib = np.clip((mu_col - 100) / 60.0, 0, 20)   # viscosity above 100 cP
    proxy = np.clip(rf_contrib + mu_contrib, 0, 60)
    srp["risk_label"] = proxy.values

    # Overlay failure labels — rows near a failure get elevated risk scores
    if len(failure_df) > 0:
        fail = failure_df.copy()
        fail["failure_date"] = pd.to_datetime(fail["failure_date"])

        for _, row in fail.iterrows():
            well = row["well_id"]
            fdate = row["failure_date"]
            well_mask = srp["well_id"] == well

            # Within 14 days before failure → risk 70-100
            near_mask = (
                well_mask
                & (srp["timestamp"] <= fdate)
                & (srp["timestamp"] >= fdate - pd.Timedelta(days=14))
            )
            if near_mask.sum() > 0:
                days_before = (fdate - srp.loc[near_mask, "timestamp"]).dt.days
                risk_near = (70 + (14 - days_before) / 14.0 * 30).clip(70, 100)
                srp.loc[near_mask, "risk_label"] = risk_near.values

            # 15-30 days before failure → risk 50-70
            far_mask = (
                well_mask
                & (srp["timestamp"] < fdate - pd.Timedelta(days=14))
                & (srp["timestamp"] >= fdate - pd.Timedelta(days=30))
            )
            if far_mask.sum() > 0:
                days_before = (fdate - srp.loc[far_mask, "timestamp"]).dt.days
                risk_far = (50 + (30 - days_before) / 16.0 * 20).clip(50, 70)
                srp.loc[far_mask, "risk_label"] = risk_far.values

    # Feature matrix
    available = [c for c in RISK_FEATURE_COLS if c in srp.columns]
    X = srp[available].fillna(srp[available].median()).values
    y = srp["risk_label"].values.clip(0, 100)

    return X.astype(float), y.astype(float)


class FailureRiskScorer:
    """
    Rod failure risk scorer.
    Outputs 0-100 score with top contributing factors.
    """

    def __init__(self) -> None:
        self.model = None
        self.feature_names: list[str] = []
        self.metrics: dict = {}

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[list[str]] = None,
        eval_fraction: float = 0.20,
    ) -> dict:
        """Train the risk scorer."""
        from sklearn.model_selection import train_test_split

        if feature_names:
            self.feature_names = feature_names

        X_tr, X_val, y_tr, y_val = train_test_split(
            X, y, test_size=eval_fraction, random_state=42
        )

        self.model = _make_xgb() if _HAS_XGB else _make_sklearn()
        self.model.fit(X_tr, y_tr)

        y_pred = np.clip(self.model.predict(X_val), 0, 100)
        mae = float(mean_absolute_error(y_val, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_val, y_pred)))

        # High-risk precision: predicted > 60 when actual > 60
        high_true = y_val > 60
        high_pred = y_pred > 60
        if high_true.sum() > 0:
            prec = float(np.mean(high_true[high_pred])) if high_pred.sum() > 0 else 0.0
            rec = float(np.mean(high_pred[high_true]))
        else:
            prec, rec = 0.0, 0.0

        self.metrics = {
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "high_risk_precision": round(prec, 3),
            "high_risk_recall": round(rec, 3),
            "n_train": int(len(X_tr)),
            "n_val": int(len(X_val)),
            "backend": "xgboost" if _HAS_XGB else "sklearn",
        }
        return self.metrics

    def predict(self, X: np.ndarray) -> float:
        """Predict risk score 0-100 for one sample."""
        if X.ndim == 1:
            X = X.reshape(1, -1)
        score = self.model.predict(X)[0]
        return float(np.clip(score, 0, 100))

    def get_top_factors(self, X: np.ndarray, top_n: int = 5) -> list[dict]:
        """Return top contributing factors for the risk prediction."""
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
            weighted = importances * np.abs(X[0])
            top_idx = np.argsort(weighted)[::-1][:top_n]
            return [
                {
                    "factor": self.feature_names[i] if i < len(self.feature_names) else f"feat_{i}",
                    "importance": round(float(importances[i]), 4),
                    "value": round(float(X[0, i]), 4),
                }
                for i in top_idx
            ]
        return []

    def save(self, directory: Optional[Path] = None) -> None:
        d = Path(directory or ARTIFACTS_DIR)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, d / "failure_risk.joblib")
        joblib.dump(self.feature_names, d / "failure_risk_features.joblib")
        joblib.dump(self.metrics, d / "failure_risk_metrics.joblib")

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "FailureRiskScorer":
        d = Path(directory or ARTIFACTS_DIR)
        rs = cls()
        rs.model = joblib.load(d / "failure_risk.joblib")
        if (d / "failure_risk_features.joblib").exists():
            rs.feature_names = joblib.load(d / "failure_risk_features.joblib")
        if (d / "failure_risk_metrics.joblib").exists():
            rs.metrics = joblib.load(d / "failure_risk_metrics.joblib")
        return rs
