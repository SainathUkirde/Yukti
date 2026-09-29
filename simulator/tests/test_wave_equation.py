"""
simulator/tests/test_wave_equation.py
Tests for the damped 1D wave equation (SRP dyno card generator).

Expected physical behavior:
  1. Normal card is parallelogram-shaped (high load upstroke, low downstroke)
  2. Rod floating card shows load drop mid-upstroke
  3. Pump-off card has reduced load range
  4. Higher viscosity increases damping → different card shape
  5. Peak load > min load (always)
  6. Dyno card has exactly DYNO_CARD_POINTS
"""

import pytest
import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.srp.wave_equation import simulate_stroke, DynoCardResult
from simulator.config import DYNO_CARD_POINTS, ROD_DIAMETER_M, PUMP_PLUNGER_DIA_MM


COMMON_KWARGS = dict(
    stroke_length_m=2.4,
    spm=5.0,
    rod_length_m=800.0,
    rod_diameter_m=ROD_DIAMETER_M,
    plunger_dia_m=PUMP_PLUNGER_DIA_MM / 1000.0,
    reservoir_pressure_kpa=4500.0,
    oil_rate_m3d=10.0,
    pump_depth_m=800.0,
    n_points=DYNO_CARD_POINTS,
)


class TestNormalCard:

    def test_card_has_correct_number_of_points(self):
        result = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        assert len(result.surface_position_m) == DYNO_CARD_POINTS
        assert len(result.surface_load_kn) == DYNO_CARD_POINTS
        assert len(result.downhole_position_m) == DYNO_CARD_POINTS
        assert len(result.downhole_load_kn) == DYNO_CARD_POINTS

    def test_peak_load_greater_than_min_load(self):
        result = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        assert result.peak_load_kn > result.min_load_kn, (
            f"Peak load must exceed min load: peak={result.peak_load_kn:.2f}, "
            f"min={result.min_load_kn:.2f}"
        )

    def test_fillage_between_0_and_1(self):
        result = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        assert 0.0 <= result.fillage_fraction <= 1.0

    def test_pump_efficiency_between_0_and_1(self):
        result = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        assert 0.0 <= result.pump_efficiency_fraction <= 1.0

    def test_motor_power_positive(self):
        result = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        assert result.motor_power_kw > 0.0

    def test_kwh_per_bbl_positive(self):
        result = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        assert result.kwh_per_bbl > 0.0


class TestRodFloatingCard:

    def test_rod_floating_reduces_fillage(self):
        """Rod floating fault must reduce pump fillage below normal."""
        normal = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        floating = simulate_stroke(
            oil_viscosity_cp=50.0, fault_type="rod_floating", fault_severity=1.0,
            **COMMON_KWARGS
        )
        assert floating.fillage_fraction < normal.fillage_fraction, (
            "Rod floating must reduce pump fillage."
        )

    def test_rod_floating_distorts_load_array(self):
        """Rod floating fault must change the load array (card distortion)."""
        normal = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        floating = simulate_stroke(
            oil_viscosity_cp=50.0, fault_type="rod_floating", fault_severity=1.0,
            **COMMON_KWARGS
        )
        diff = np.abs(np.array(normal.surface_load_kn) - np.array(floating.surface_load_kn))
        assert diff.max() > 0.01, "Rod floating fault must distort the load card"


class TestPumpOffCard:

    def test_pump_off_reduces_load_range(self):
        """Pump-off must reduce the peak-to-min load range."""
        normal = simulate_stroke(oil_viscosity_cp=50.0, **COMMON_KWARGS)
        pump_off = simulate_stroke(
            oil_viscosity_cp=50.0, fault_type="pump_off", fault_severity=1.0,
            **COMMON_KWARGS
        )
        normal_range = normal.peak_load_kn - normal.min_load_kn
        pumpoff_range = pump_off.peak_load_kn - pump_off.min_load_kn
        assert pumpoff_range < normal_range, (
            "Pump-off must reduce load range (less fluid in pump barrel)."
        )


class TestViscosityEffect:

    def test_high_viscosity_increases_damping(self):
        """
        High viscosity increases damping coefficient → different rod fall speed
        and rod floating risk compared to low viscosity.
        """
        result_low_visc = simulate_stroke(oil_viscosity_cp=20.0, **COMMON_KWARGS)
        result_high_visc = simulate_stroke(oil_viscosity_cp=3000.0, **COMMON_KWARGS)
        # High viscosity → slower rod fall → higher float risk
        assert result_high_visc.rod_float_risk > result_low_visc.rod_float_risk, (
            "Higher viscosity must produce higher rod floating risk."
        )

    def test_higher_spm_increases_floating_risk(self):
        """Higher SPM increases plunger demand → higher rod floating risk."""
        kwargs_low = {**COMMON_KWARGS, "spm": 3.0}
        kwargs_high = {**COMMON_KWARGS, "spm": 8.0}
        r_low = simulate_stroke(oil_viscosity_cp=500.0, **kwargs_low)
        r_high = simulate_stroke(oil_viscosity_cp=500.0, **kwargs_high)
        assert r_high.rod_float_risk > r_low.rod_float_risk, (
            "Higher SPM must produce higher rod floating risk."
        )
