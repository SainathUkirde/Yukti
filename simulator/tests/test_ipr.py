"""
simulator/tests/test_ipr.py
Tests for Vogel IPR and viscosity-coupled PI.

Expected physical behavior:
  1. Oil rate increases as viscosity decreases (CSS benefit)
  2. PI is inversely proportional to viscosity
  3. Oil rate = 0 when Pwf = Pr (no drawdown)
  4. Oil rate > 0 when Pwf < Pr
  5. WOR increases monotonically with production time
"""

import pytest
import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.reservoir.ipr import (
    productivity_index,
    vogel_oil_rate,
    water_oil_ratio,
    water_cut_from_wor,
    reservoir_pressure_decline,
)


class TestVogelIPR:

    def test_zero_rate_at_no_drawdown(self):
        """Oil rate must be zero when Pwf = Pr (no pressure drawdown)."""
        Pr = 4500.0
        q = vogel_oil_rate(Pr, Pr, viscosity_cp=50.0)
        assert q == pytest.approx(0.0, abs=1e-6), (
            f"Oil rate must be 0 when Pwf = Pr, got {q}"
        )

    def test_max_rate_at_zero_pwf(self):
        """Maximum rate at Pwf=0 (maximum drawdown)."""
        Pr = 4500.0
        q = vogel_oil_rate(Pr, 0.0, viscosity_cp=50.0)
        assert q > 0.0, "Oil rate must be positive at maximum drawdown"

    def test_rate_increases_as_viscosity_decreases(self):
        """Lower viscosity (steam heating) must give higher production rate — core CSS mechanism."""
        Pr, Pwf = 4500.0, 800.0
        q_cold = vogel_oil_rate(Pr, Pwf, viscosity_cp=2000.0)  # cold, high-visc
        q_hot = vogel_oil_rate(Pr, Pwf, viscosity_cp=20.0)      # hot, low-visc
        assert q_hot > q_cold, (
            f"Lower viscosity must give higher oil rate. "
            f"q_cold={q_cold:.4f}, q_hot={q_hot:.4f} m³/day"
        )

    def test_viscosity_ratio_scales_rate_approximately(self):
        """
        PI is inversely proportional to viscosity, so rate should scale roughly
        with viscosity ratio (at same pressure drawdown).
        """
        Pr, Pwf = 4500.0, 800.0
        mu1, mu2 = 100.0, 500.0
        q1 = vogel_oil_rate(Pr, Pwf, viscosity_cp=mu1)
        q2 = vogel_oil_rate(Pr, Pwf, viscosity_cp=mu2)
        # q1/q2 ≈ mu2/mu1 (Vogel is nonlinear, so approximately)
        expected_ratio = mu2 / mu1
        actual_ratio = q1 / max(q2, 1e-9)
        assert abs(actual_ratio - expected_ratio) / expected_ratio < 0.15, (
            f"Rate ratio {actual_ratio:.2f} should be close to viscosity ratio {expected_ratio:.2f}"
        )

    def test_pi_inversely_proportional_to_viscosity(self):
        """PI(T) = PI_ref · (μ_ref / μ) — exact relationship."""
        pi_1 = productivity_index(100.0)
        pi_2 = productivity_index(200.0)
        assert abs(pi_2 - pi_1 / 2.0) / pi_1 < 1e-9, (
            "PI must be exactly inversely proportional to viscosity."
        )


class TestWOR:

    def test_wor_increases_with_production_time(self):
        """WOR must increase as production continues (water influx increases with time)."""
        T_peak, T_init = 130.0, 47.0
        wors = [water_oil_ratio(t, T_peak, T_init) for t in range(0, 90, 10)]
        diffs = np.diff(wors)
        assert np.all(diffs >= 0), "WOR must be non-decreasing with production time"

    def test_water_cut_between_0_and_1(self):
        """Water cut fraction must always be in [0, 1]."""
        for wor in [0.0, 0.5, 1.0, 5.0, 10.0, 50.0]:
            wc = water_cut_from_wor(wor)
            assert 0.0 <= wc <= 1.0, f"Water cut must be in [0,1], got {wc} for WOR={wor}"

    def test_pressure_declines_during_production(self):
        """Reservoir pressure must decline during production (no steam re-injection)."""
        P0 = 4500.0
        P_later = reservoir_pressure_decline(P0, 30.0)
        assert P_later < P0, f"Pressure must decline: P0={P0}, P_later={P_later}"
