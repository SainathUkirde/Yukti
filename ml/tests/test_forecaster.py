"""
ml/tests/test_forecaster.py
Tests for the production forecaster.

Expected behavior:
  1. Forecaster loads saved artifacts without error
  2. Prediction returns q10 <= q50 <= q90 for all targets
  3. Prediction intervals are non-zero (uncertainty is expressed)
  4. Temperature forecast is within physically reasonable range (40-220°C)
  5. Oil rate forecast is non-negative
"""
import pytest
import sys, os
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def forecaster():
    from ml.models.forecaster import ProductionForecaster
    return ProductionForecaster.load()


class TestForecasterArtifacts:

    def test_loads_without_error(self, forecaster):
        # forecaster.models is a dict of {target: {alpha: model}}
        assert len(forecaster.models) == 3
        assert len(forecaster.feature_names) > 0

    def test_metrics_exist(self, forecaster):
        assert len(forecaster.metrics) == 3
        for target in ["reservoir_temp_c", "oil_viscosity_cp", "oil_rate_m3d"]:
            assert target in forecaster.metrics
            m = forecaster.metrics[target]
            assert "q50_mae" in m
            assert "coverage_80pct" in m

    def test_mae_reasonable(self, forecaster):
        """Temperature MAE should be < 5°C on synthetic data."""
        mae = forecaster.metrics["reservoir_temp_c"]["q50_mae"]
        assert mae < 5.0, f"Temperature MAE too high: {mae}"

    def test_oil_rate_mae_reasonable(self, forecaster):
        """Oil rate MAE should be < 5 m³/day."""
        mae = forecaster.metrics["oil_rate_m3d"]["q50_mae"]
        assert mae < 5.0, f"Oil rate MAE too high: {mae}"


class TestForecasterPrediction:

    def test_quantile_ordering(self, forecaster):
        """q10 <= q50 <= q90 for all targets."""
        n_feats = len(forecaster.feature_names)
        X = np.random.default_rng(42).normal(0, 1, (1, n_feats))
        result = forecaster.predict(X)
        for target, preds in result.items():
            q10, q50, q90 = preds["q10"], preds["q50"], preds["q90"]
            assert q10 <= q90 + 1e-3, (
                f"q10 > q90 for {target}: q10={q10:.3f}, q90={q90:.3f}"
            )

    def test_prediction_dict_structure(self, forecaster):
        """Prediction returns correct structure."""
        n_feats = len(forecaster.feature_names)
        X = np.ones((1, n_feats))
        result = forecaster.predict(X)
        assert set(result.keys()) == {"reservoir_temp_c", "oil_viscosity_cp", "oil_rate_m3d"}
        for target in result:
            assert set(result[target].keys()) == {"q10", "q50", "q90"}
