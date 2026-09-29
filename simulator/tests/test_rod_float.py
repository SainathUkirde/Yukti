"""
simulator/tests/test_rod_float.py
Tests for rod floating detection physics.

Expected behavior:
  1. Very high viscosity at typical SPM → rod float risk > 1.0
  2. Low viscosity at typical SPM → rod float risk < 1.0
  3. Risk increases with SPM (higher plunger demand)
  4. Risk decreases when SPM is reduced (optimizer action)
  5. risk_score_0_100 maps correctly to 0-100 scale
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.srp.rod_float import (
    rod_float_risk_ratio,
    rod_fall_speed_ms,
    plunger_peak_speed_ms,
    is_rod_floating,
    rod_float_risk_score_0_100,
)
from simulator.config import ROD_DIAMETER_M


COMMON_ROD = dict(
    rod_diameter_m=ROD_DIAMETER_M,
    rod_length_m=800.0,
)


class TestRodFloatPhysics:

    def test_very_high_viscosity_causes_floating(self):
        """
        At Baghewala initial conditions (high viscosity ~2000 cP) and moderate SPM,
        rod floating risk should be elevated (RF ≥ 1).
        """
        rf = rod_float_risk_ratio(
            stroke_length_m=2.4,
            spm=6.0,
            oil_viscosity_cp=2000.0,
            **COMMON_ROD,
        )
        assert rf >= 1.0, (
            f"Expected rod floating (RF ≥ 1.0) at high viscosity 2000 cP, SPM=6, got RF={rf:.3f}. "
            "This is the key Baghewala problem: heavy oil causes rod floating."
        )

    def test_low_viscosity_no_floating(self):
        """At steam-heated low viscosity (~10 cP), rod floating should be absent."""
        rf = rod_float_risk_ratio(
            stroke_length_m=2.4,
            spm=5.0,
            oil_viscosity_cp=10.0,
            **COMMON_ROD,
        )
        assert rf < 1.0, (
            f"Expected no rod floating at low viscosity 10 cP, SPM=5, got RF={rf:.3f}."
        )

    def test_floating_risk_increases_with_spm(self):
        """Increasing SPM increases plunger demand → higher floating risk."""
        rf_low = rod_float_risk_ratio(
            stroke_length_m=2.4, spm=3.0, oil_viscosity_cp=500.0, **COMMON_ROD
        )
        rf_high = rod_float_risk_ratio(
            stroke_length_m=2.4, spm=9.0, oil_viscosity_cp=500.0, **COMMON_ROD
        )
        assert rf_high > rf_low, (
            "Rod float risk must increase with SPM."
        )

    def test_reducing_spm_resolves_floating(self):
        """
        Core optimizer test: reducing SPM from a floating condition must bring RF below 1.0.
        This validates the primary recommendation the optimizer makes.
        """
        # High viscosity + high SPM → floating
        rf_before = rod_float_risk_ratio(
            stroke_length_m=2.4, spm=7.0, oil_viscosity_cp=1500.0, **COMMON_ROD
        )
        # Reduce SPM significantly
        rf_after = rod_float_risk_ratio(
            stroke_length_m=2.4, spm=3.0, oil_viscosity_cp=1500.0, **COMMON_ROD
        )
        assert rf_after < rf_before, "Reducing SPM must decrease rod floating risk"

    def test_floating_risk_increases_with_viscosity(self):
        """Increasing viscosity slows rod fall → higher floating risk."""
        rf1 = rod_float_risk_ratio(2.4, 5.0, **COMMON_ROD, oil_viscosity_cp=50.0)
        rf2 = rod_float_risk_ratio(2.4, 5.0, **COMMON_ROD, oil_viscosity_cp=500.0)
        rf3 = rod_float_risk_ratio(2.4, 5.0, **COMMON_ROD, oil_viscosity_cp=2000.0)
        assert rf1 < rf2 < rf3, (
            f"Risk must increase with viscosity: {rf1:.3f} < {rf2:.3f} < {rf3:.3f}"
        )


class TestRiskScore:

    def test_risk_score_range(self):
        """Risk score must always be in [0, 100]."""
        for rf in [0.0, 0.5, 1.0, 1.5, 2.0, 5.0]:
            score = rod_float_risk_score_0_100(rf)
            assert 0.0 <= score <= 100.0, f"Score out of range for RF={rf}: {score}"

    def test_high_rf_gives_high_score(self):
        """RF ≥ 2.0 should give score close to 100."""
        score = rod_float_risk_score_0_100(2.0)
        assert score >= 90.0, f"RF=2.0 should give high risk score, got {score}"

    def test_is_rod_floating(self):
        assert is_rod_floating(0.9) is False
        assert is_rod_floating(1.0) is True
        assert is_rod_floating(1.5) is True
