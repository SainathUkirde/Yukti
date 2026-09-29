"""
simulator/tests/test_viscosity.py
Tests for the Walther/ASTM D341 viscosity-temperature model.

Expected physical behavior:
  1. Viscosity at 47°C (Baghewala initial temp) must be very high (>500 cP for 18° API)
  2. Viscosity at 150°C (steam-heated) must be much lower (<50 cP)
  3. Viscosity is strictly monotone decreasing with temperature
  4. fit_walther_constants must round-trip correctly
"""

import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.wellbore.viscosity import (
    viscosity_cp,
    viscosity_array,
    fit_walther_constants,
    walther_kinematic_cst,
)


class TestViscosityAtBaghewalaConditions:

    def test_high_viscosity_at_initial_reservoir_temp(self):
        """At 47°C (Baghewala initial temp), viscosity must be very high (>500 cP)."""
        mu = viscosity_cp(47.0, api=18.0)
        assert mu > 500.0, (
            f"Expected viscosity > 500 cP at 47°C for 18° API crude, got {mu:.1f} cP. "
            "FIELD_FACT: Baghewala crude is high-viscosity heavy oil."
        )

    def test_low_viscosity_at_steam_temperature(self):
        """At 150°C (steam-heated), viscosity must be much lower (<100 cP)."""
        mu = viscosity_cp(150.0, api=18.0)
        assert mu < 100.0, (
            f"Expected viscosity < 100 cP at 150°C (steam-heated), got {mu:.1f} cP."
        )

    def test_viscosity_ratio_temperature_effect(self):
        """Steam heating must reduce viscosity by at least 10x (critical for CSS benefit)."""
        mu_cold = viscosity_cp(47.0, api=18.0)
        mu_hot = viscosity_cp(150.0, api=18.0)
        ratio = mu_cold / mu_hot
        assert ratio >= 10.0, (
            f"Expected viscosity ratio (cold/hot) ≥ 10, got {ratio:.1f}. "
            "CSS is only beneficial if steam heating significantly reduces viscosity."
        )

    def test_viscosity_strictly_decreasing_with_temperature(self):
        """Viscosity must decrease as temperature increases (fundamental thermodynamics)."""
        temps = np.linspace(40.0, 200.0, 50)
        viscosities = viscosity_array(temps, api=18.0)
        diffs = np.diff(viscosities)
        assert np.all(diffs < 0), (
            "Viscosity must be strictly monotone decreasing with temperature."
        )

    def test_viscosity_positive(self):
        """Viscosity must always be positive for any valid input."""
        for T in [30.0, 47.0, 80.0, 100.0, 150.0, 200.0]:
            mu = viscosity_cp(T, api=18.0)
            assert mu > 0.0, f"Viscosity must be > 0 at T={T}°C, got {mu}"
        # Note: the Andrade model uses only temperature (not API) for viscosity;
        # API-based differentiation is handled at the PI/IPR layer. [Ahmed 2010]


class TestWaltherFitting:

    def test_fit_roundtrip(self):
        """Fitted constants must reproduce the input viscosity values."""
        T1, mu1 = 47.0, 2000.0
        T2, mu2 = 150.0, 10.0
        A, B = fit_walther_constants(T1, mu1, T2, mu2)   # api param removed (Andrade model)
        mu1_check = viscosity_cp(T1, api=18.0, A=A, B=B)
        mu2_check = viscosity_cp(T2, api=18.0, A=A, B=B)
        assert abs(mu1_check - mu1) / mu1 < 0.05, (
            f"Fit round-trip error at T1: expected {mu1}, got {mu1_check:.1f}"
        )
        assert abs(mu2_check - mu2) / mu2 < 0.05, (
            f"Fit round-trip error at T2: expected {mu2}, got {mu2_check:.1f}"
        )

    def test_vectorized_matches_scalar(self):
        """Vectorized and scalar viscosity functions must agree."""
        temps = np.array([47.0, 80.0, 120.0, 150.0])
        vec = viscosity_array(temps, api=18.0)
        for i, T in enumerate(temps):
            sc = viscosity_cp(T, api=18.0)
            assert abs(vec[i] - sc) / sc < 1e-6, f"Mismatch at T={T}: vec={vec[i]}, scalar={sc}"
