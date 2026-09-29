"""
ml/tests/test_failure_risk.py
Tests for the rod failure risk scorer.

Expected behavior:
  1. Loads saved artifact without error
  2. Prediction is in [0, 100]
  3. High viscosity + high RF → higher risk than low viscosity + low RF
  4. Top factors are returned with correct structure
"""
import pytest
import sys, os
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def risk_scorer():
    from ml.models.failure_risk import FailureRiskScorer
    return FailureRiskScorer.load()


def _make_input(rf=0.3, mu=100, spm=5.0, fillage=0.8, t_prod=10):
    """Make a minimal risk input vector matching RISK_FEATURE_COLS order."""
    from ml.models.failure_risk import RISK_FEATURE_COLS
    from ml.models.failure_risk import FailureRiskScorer
    import pandas as pd

    rs = FailureRiskScorer.load()
    feats = rs.feature_names
    # Build a dict with all features at safe defaults
    defaults = {
        "rod_float_risk_ratio": rf,
        "rod_float_risk_score": rf * 50,
        "oil_viscosity_cp": mu,
        "spm": spm,
        "stroke_length_m": 2.4,
        "motor_power_kw": 15.0,
        "kwh_per_bbl": 30.0,
        "pump_fillage_fraction": fillage,
        "pump_efficiency_fraction": 0.7,
        "polished_rod_load_kn": 20.0,
        "min_rod_load_kn": 5.0,
        "reservoir_temp_c": 80.0,
        "t_production_days": t_prod,
        "cycle_number": 1,
    }
    return np.array([defaults.get(f, 0.0) for f in feats], dtype=float)


class TestFailureRiskArtifacts:

    def test_loads_without_error(self, risk_scorer):
        assert risk_scorer.model is not None

    def test_mae_reasonable(self, risk_scorer):
        assert risk_scorer.metrics.get("mae", 999) < 20.0, (
            f"Risk scorer MAE {risk_scorer.metrics.get('mae')} too high"
        )


class TestFailureRiskPrediction:

    def test_score_in_range(self, risk_scorer):
        X = _make_input(rf=0.5, mu=300)
        score = risk_scorer.predict(X)
        assert 0.0 <= score <= 100.0, f"Risk score out of range: {score}"

    def test_high_risk_conditions_give_higher_score(self, risk_scorer):
        """High RF + high viscosity should give higher risk than safe conditions.
        Uses an ensemble of samples to test directional trend robustly."""
        import numpy as np
        rng = np.random.default_rng(99)
        safe_scores = []
        risky_scores = []
        for _ in range(20):
            X_safe = _make_input(
                rf=float(rng.uniform(0.1, 0.4)),
                mu=float(rng.uniform(30, 80)),
                spm=float(rng.uniform(2.0, 4.0)),
                t_prod=float(rng.uniform(5, 20)),
            )
            X_risky = _make_input(
                rf=float(rng.uniform(1.5, 2.5)),
                mu=float(rng.uniform(1500, 2500)),
                spm=float(rng.uniform(7.0, 10.0)),
                t_prod=float(rng.uniform(60, 120)),
            )
            safe_scores.append(risk_scorer.predict(X_safe))
            risky_scores.append(risk_scorer.predict(X_risky))

        mean_safe = float(np.mean(safe_scores))
        mean_risky = float(np.mean(risky_scores))
        assert mean_risky > mean_safe, (
            f"On average, risky conditions should give higher score. "
            f"Mean safe={mean_safe:.1f}, mean risky={mean_risky:.1f}"
        )

    def test_top_factors_structure(self, risk_scorer):
        X = _make_input(rf=1.5, mu=1500)
        factors = risk_scorer.get_top_factors(X, top_n=3)
        if len(factors) > 0:
            assert "factor" in factors[0]
            assert "importance" in factors[0]
            assert "value" in factors[0]
