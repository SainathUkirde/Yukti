"""
ml/models/forecaster.py
Production forecaster: gradient boosting quantile regression.

Predicts reservoir temperature, oil viscosity, and oil rate N days ahead,
with prediction intervals (q10, q50, q90).

Model: LightGBM with quantile loss (alpha = 0.1, 0.5, 0.9).
Fallback: scikit-learn GradientBoostingRegressor if LightGBM unavailable.

No PyTorch or GPU required.
"""
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Optional

try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "models" / "artifacts"
QUANTILES = [0.10, 0.50, 0.90]
TARGETS = ["reservoir_temp_c", "oil_viscosity_cp", "oil_rate_m3d"]


def _make_lgb_quantile(alpha: float) -> "lgb.LGBMRegressor":
    return lgb.LGBMRegressor(
        objective="quantile",
        alpha=alpha,
        n_estimators=300,
        learning_rate=0.05,
        max_depth=5,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )


def _make_sklearn_quantile(alpha: float) -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("model", GradientBoostingRegressor(
            loss="quantile",
            alpha=alpha,
            n_estimators=200,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.8,
            random_state=42,
        )),
    ])


class ProductionForecaster:
    """
    Multi-target quantile forecaster.

    For each target in TARGETS, trains 3 models (q10, q50, q90).
    Total: 9 model objects.

    Artifacts saved as:
      forecaster_{target}_q{int(alpha*100)}.joblib
    """

    def __init__(self) -> None:
        self.models: dict[str, dict[float, object]] = {t: {} for t in TARGETS}
        self.feature_names: list[str] = []
        self.metrics: dict = {}

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.DataFrame,
        eval_fraction: float = 0.2,
    ) -> dict:
        """
        Train quantile models for all targets.

        Parameters
        ----------
        X : pd.DataFrame   feature matrix (from build_forecaster_features)
        y : pd.DataFrame   targets [reservoir_temp_c, oil_viscosity_cp, oil_rate_m3d]
        eval_fraction      fraction of data held out for evaluation

        Returns
        -------
        dict   metrics per target: {target: {q50_mae, q50_rmse, coverage_80}}
        """
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_error, mean_squared_error

        feat_cols = [c for c in X.columns if c != "well_id"]
        self.feature_names = feat_cols
        X_vals = X[feat_cols].values
        X_tr, X_val, y_tr, y_val = train_test_split(
            X_vals, y.values, test_size=eval_fraction, random_state=42
        )

        self.metrics = {}
        for i, target in enumerate(TARGETS):
            y_tr_t = y_tr[:, i]
            y_val_t = y_val[:, i]

            for alpha in QUANTILES:
                if _HAS_LGB:
                    m = _make_lgb_quantile(alpha)
                    m.fit(X_tr, y_tr_t)
                else:
                    m = _make_sklearn_quantile(alpha)
                    m.fit(X_tr, y_tr_t)
                self.models[target][alpha] = m

            # Metrics on q50 (median)
            y_pred_q50 = self.models[target][0.50].predict(X_val)
            y_pred_q10 = self.models[target][0.10].predict(X_val)
            y_pred_q90 = self.models[target][0.90].predict(X_val)

            mae = float(mean_absolute_error(y_val_t, y_pred_q50))
            rmse = float(np.sqrt(mean_squared_error(y_val_t, y_pred_q50)))
            # 80% prediction interval coverage
            in_interval = np.mean((y_val_t >= y_pred_q10) & (y_val_t <= y_pred_q90))
            self.metrics[target] = {
                "q50_mae": round(mae, 4),
                "q50_rmse": round(rmse, 4),
                "coverage_80pct": round(float(in_interval), 3),
                "n_train": len(X_tr),
                "n_val": len(X_val),
                "backend": "lightgbm" if _HAS_LGB else "sklearn",
            }

        return self.metrics

    def predict(
        self,
        X: np.ndarray,
        horizon_steps: int = 1,
    ) -> dict[str, dict[str, float]]:
        """
        Predict all targets for one input row.

        Returns
        -------
        dict  {target: {q10, q50, q90}}
        """
        if X.ndim == 1:
            X = X.reshape(1, -1)
        result = {}
        for target in TARGETS:
            result[target] = {
                f"q{int(alpha*100):02d}": float(self.models[target][alpha].predict(X)[0])
                for alpha in QUANTILES
            }
        return result

    def save(self, directory: Optional[Path] = None) -> None:
        """Save all model artifacts to directory."""
        d = Path(directory or ARTIFACTS_DIR)
        d.mkdir(parents=True, exist_ok=True)
        for target in TARGETS:
            for alpha in QUANTILES:
                fname = d / f"forecaster_{target}_q{int(alpha*100):02d}.joblib"
                joblib.dump(self.models[target][alpha], fname)
        joblib.dump(self.feature_names, d / "forecaster_feature_names.joblib")
        joblib.dump(self.metrics, d / "forecaster_metrics.joblib")

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "ProductionForecaster":
        """Load saved model artifacts."""
        d = Path(directory or ARTIFACTS_DIR)
        fc = cls()
        fc.feature_names = joblib.load(d / "forecaster_feature_names.joblib")
        for target in TARGETS:
            for alpha in QUANTILES:
                fname = d / f"forecaster_{target}_q{int(alpha*100):02d}.joblib"
                fc.models[target][alpha] = joblib.load(fname)
        if (d / "forecaster_metrics.joblib").exists():
            fc.metrics = joblib.load(d / "forecaster_metrics.joblib")
        return fc
