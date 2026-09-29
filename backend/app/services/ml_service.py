"""
backend/app/services/ml_service.py
Loads and caches all ML model artifacts at startup.
Provides predict/classify/score methods used by API endpoints.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, ROOT)

logger = logging.getLogger("ml_service")
ARTIFACTS_DIR = Path(ROOT) / "models" / "artifacts"


class MLService:
    """Singleton ML service — loads all models once."""

    def __init__(self):
        self._forecaster = None
        self._fault_clf = None
        self._risk_scorer = None
        self._loaded = False

    def load(self):
        """Load all model artifacts. Call once at startup."""
        try:
            from ml.models.forecaster import ProductionForecaster
            self._forecaster = ProductionForecaster.load(ARTIFACTS_DIR)
            logger.info("Forecaster loaded")
        except Exception as e:
            logger.warning(f"Forecaster not loaded: {e}")

        try:
            from ml.models.fault_classifier import DynoFaultClassifier
            self._fault_clf = DynoFaultClassifier.load(ARTIFACTS_DIR)
            logger.info("Fault classifier loaded")
        except Exception as e:
            logger.warning(f"Fault classifier not loaded: {e}")

        try:
            from ml.models.failure_risk import FailureRiskScorer
            self._risk_scorer = FailureRiskScorer.load(ARTIFACTS_DIR)
            logger.info("Risk scorer loaded")
        except Exception as e:
            logger.warning(f"Risk scorer not loaded: {e}")

        self._loaded = True
        logger.info("ML service ready")

    def classify_fault(self, features) -> dict:
        """Classify dyno card fault. Returns {class, confidence, probabilities, top_features}."""
        if self._fault_clf is None:
            return {"predicted_fault": "unknown", "confidence": 0.0,
                    "class_probabilities": {}, "top_features": []}
        import numpy as np
        X = np.asarray(features, dtype=float)
        pred, conf, probs = self._fault_clf.predict(X)
        top = self._fault_clf.get_top_features(X, top_n=5)
        return {"predicted_fault": pred, "confidence": conf,
                "class_probabilities": probs, "top_features": top}

    def forecast(self, X) -> dict:
        """Forecast next N days. Returns {target: {q10, q50, q90}}."""
        if self._forecaster is None:
            return {}
        import numpy as np
        return self._forecaster.predict(np.asarray(X, dtype=float))

    def score_risk(self, features) -> tuple[float, list]:
        """Score rod failure risk 0-100. Returns (score, top_factors)."""
        if self._risk_scorer is None:
            return 0.0, []
        import numpy as np
        X = np.asarray(features, dtype=float)
        score = self._risk_scorer.predict(X)
        factors = self._risk_scorer.get_top_factors(X, top_n=5)
        return float(score), factors

    @property
    def loaded(self) -> bool:
        return self._loaded


# Module-level singleton
ml_service = MLService()
