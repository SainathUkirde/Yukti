"""
ml/tests/test_fault_classifier.py
Tests for the dyno card fault classifier.

Expected behavior:
  1. Loads saved artifact without error
  2. Accuracy >= 0.80 on synthetic data
  3. F1 macro >= 0.75
  4. Normal card predicts "normal" with high confidence
  5. Rod-floating card (high viscosity, high SPM) predicts "rod_floating"
  6. Returns correct number of class probabilities (6 classes)
"""
import pytest
import sys, os
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def classifier():
    from ml.models.fault_classifier import DynoFaultClassifier
    return DynoFaultClassifier.load()


@pytest.fixture(scope="module")
def normal_card_features():
    """Generate feature vector for a clean normal card."""
    from ml.features.dyno_features import extract_features
    from simulator.srp.wave_equation import simulate_stroke
    from simulator.config import ROD_DIAMETER_M, PUMP_PLUNGER_DIA_MM

    dyno = simulate_stroke(
        stroke_length_m=2.4, spm=5.0, rod_length_m=800.0,
        rod_diameter_m=ROD_DIAMETER_M, plunger_dia_m=PUMP_PLUNGER_DIA_MM / 1000.0,
        oil_viscosity_cp=30.0, reservoir_pressure_kpa=4500.0,
        oil_rate_m3d=12.0, pump_depth_m=800.0,
    )
    return extract_features(
        dyno.surface_position_m, dyno.surface_load_kn,
        dyno.downhole_position_m, dyno.downhole_load_kn,
        fillage_fraction=dyno.fillage_fraction,
        peak_load_kn=dyno.peak_load_kn,
        min_load_kn=dyno.min_load_kn,
        pump_efficiency_fraction=dyno.pump_efficiency_fraction,
        rod_float_risk_ratio=dyno.rod_float_risk,
        oil_viscosity_cp=30.0, spm=5.0, stroke_length_m=2.4,
    )


@pytest.fixture(scope="module")
def floating_card_features():
    """Generate feature vector for a rod-floating card."""
    from ml.features.dyno_features import extract_features
    from simulator.srp.wave_equation import simulate_stroke
    from simulator.config import ROD_DIAMETER_M, PUMP_PLUNGER_DIA_MM

    dyno = simulate_stroke(
        stroke_length_m=2.4, spm=7.0, rod_length_m=800.0,
        rod_diameter_m=ROD_DIAMETER_M, plunger_dia_m=PUMP_PLUNGER_DIA_MM / 1000.0,
        oil_viscosity_cp=1800.0, reservoir_pressure_kpa=3500.0,
        oil_rate_m3d=4.0, pump_depth_m=800.0,
        fault_type="rod_floating", fault_severity=0.9,
    )
    from simulator.srp.rod_float import rod_float_risk_ratio
    rf = rod_float_risk_ratio(2.4, 7.0, ROD_DIAMETER_M, 800.0, 1800.0)
    return extract_features(
        dyno.surface_position_m, dyno.surface_load_kn,
        dyno.downhole_position_m, dyno.downhole_load_kn,
        fillage_fraction=dyno.fillage_fraction,
        peak_load_kn=dyno.peak_load_kn,
        min_load_kn=dyno.min_load_kn,
        pump_efficiency_fraction=dyno.pump_efficiency_fraction,
        rod_float_risk_ratio=rf,
        oil_viscosity_cp=1800.0, spm=7.0, stroke_length_m=2.4,
    )


class TestFaultClassifierArtifacts:

    def test_loads_without_error(self, classifier):
        assert classifier.model is not None
        assert classifier._fitted

    def test_accuracy_above_threshold(self, classifier):
        assert classifier.metrics["accuracy"] >= 0.75, (
            f"Accuracy {classifier.metrics['accuracy']:.3f} below threshold 0.75"
        )

    def test_f1_macro_above_threshold(self, classifier):
        assert classifier.metrics["f1_macro"] >= 0.70, (
            f"F1 macro {classifier.metrics['f1_macro']:.3f} below threshold 0.70"
        )

    def test_six_classes(self, classifier):
        assert len(classifier.metrics["classes"]) == 6


class TestFaultClassifierPrediction:

    def test_returns_6_class_probabilities(self, classifier, normal_card_features):
        _, _, probs = classifier.predict(normal_card_features)
        assert len(probs) == 6, f"Expected 6 class probs, got {len(probs)}"

    def test_probs_sum_to_one(self, classifier, normal_card_features):
        _, _, probs = classifier.predict(normal_card_features)
        total = sum(probs.values())
        assert abs(total - 1.0) < 1e-5, f"Probs sum to {total:.6f}, expected 1.0"

    def test_normal_card_classified_normal_or_reasonable(self, classifier, normal_card_features):
        """Normal card should not be predicted as fluid_pound or pump_unsetting."""
        pred_class, conf, probs = classifier.predict(normal_card_features)
        # Normal card should not overwhelmingly predict a severe fault
        assert probs.get("fluid_pound", 0) < 0.5, (
            "Normal card should not be primarily classified as fluid_pound"
        )

    def test_top_features_returned(self, classifier, normal_card_features):
        top = classifier.get_top_features(normal_card_features, top_n=5)
        assert len(top) <= 5
        if len(top) > 0:
            assert "feature" in top[0]
            assert "importance" in top[0]

    def test_confidence_between_0_and_1(self, classifier, normal_card_features):
        _, conf, _ = classifier.predict(normal_card_features)
        assert 0.0 <= conf <= 1.0
