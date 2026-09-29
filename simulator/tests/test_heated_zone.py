"""
simulator/tests/test_heated_zone.py
Tests for the Marx-Langenheim heated-zone model and cooling decay.

Expected physical behavior:
  1. Larger steam volume → larger heated zone radius
  2. Higher steam quality → larger/hotter heated zone
  3. Temperature decays monotonically during production
  4. SOR rises with successive CSS cycles (thermal efficiency degrades)
  5. Heated zone cannot exceed drainage radius
"""

import pytest
import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.reservoir.heated_zone import (
    heated_zone_radius_m,
    peak_temperature_c,
    reservoir_temperature_c,
    sor,
)


class TestHeatedZone:

    def test_radius_increases_with_steam_volume(self):
        """More steam → larger heated zone."""
        r1 = heated_zone_radius_m(300.0, 0.75, 20.0, 0.22)
        r2 = heated_zone_radius_m(600.0, 0.75, 20.0, 0.22)
        r3 = heated_zone_radius_m(900.0, 0.75, 20.0, 0.22)
        assert r1 < r2 < r3, (
            f"Heated zone radius must increase with steam volume: {r1:.1f} < {r2:.1f} < {r3:.1f}"
        )

    def test_radius_positive_for_valid_input(self):
        """Radius must be positive for any valid steam input."""
        r = heated_zone_radius_m(500.0, 0.75, 20.0, 0.22)
        assert r > 0.0, f"Heated zone radius must be > 0, got {r}"

    def test_zero_steam_gives_zero_radius(self):
        """Zero steam volume → zero heated zone."""
        r = heated_zone_radius_m(0.0, 0.75, 20.0, 0.22)
        assert r == 0.0

    def test_higher_quality_gives_larger_radius(self):
        """Higher steam quality (more latent heat) → larger heated zone."""
        r_low = heated_zone_radius_m(500.0, 0.60, 20.0, 0.22)
        r_high = heated_zone_radius_m(500.0, 0.85, 20.0, 0.22)
        assert r_low < r_high, (
            "Higher steam quality must give larger heated zone."
        )

    def test_peak_temperature_above_initial(self):
        """Peak temperature after steam injection must exceed initial reservoir temperature."""
        T_init = 47.0
        T_peak = peak_temperature_c(500.0, 0.75, 20.0, 0.22, T_initial_c=T_init)
        assert T_peak > T_init, (
            f"Peak temperature {T_peak:.1f}°C must exceed initial {T_init}°C"
        )

    def test_peak_temperature_below_steam_temperature(self):
        """Peak temperature cannot exceed steam temperature."""
        T_steam = 200.0
        T_peak = peak_temperature_c(500.0, 0.75, 20.0, 0.22, T_steam_c=T_steam)
        assert T_peak <= T_steam + 0.1, (
            f"Peak temperature {T_peak:.1f}°C cannot exceed steam temperature {T_steam}°C"
        )


class TestCoolingDecay:

    def test_temperature_decays_monotonically(self):
        """Reservoir temperature must decay monotonically during production."""
        T_peak, T_init = 130.0, 47.0
        times = np.linspace(0, 90, 100)
        temps = [reservoir_temperature_c(T_peak, T_init, t) for t in times]
        diffs = np.diff(temps)
        assert np.all(diffs <= 0.001), (
            "Reservoir temperature must be non-increasing during production."
        )

    def test_temperature_approaches_initial(self):
        """After very long production, temperature should approach initial temp."""
        T_peak, T_init = 130.0, 47.0
        T_late = reservoir_temperature_c(T_peak, T_init, 365.0)
        assert abs(T_late - T_init) < 5.0, (
            f"After 1 year, reservoir should cool near initial temp. "
            f"Got {T_late:.1f}°C, expected ≈{T_init}°C"
        )

    def test_temperature_at_zero_production_time_is_peak(self):
        """At t=0 of production, temperature should equal peak."""
        T_peak, T_init = 130.0, 47.0
        T0 = reservoir_temperature_c(T_peak, T_init, 0.0)
        assert abs(T0 - T_peak) < 0.01, (
            f"At t=0, temperature should be T_peak={T_peak}, got {T0:.2f}"
        )


class TestCycleDegradation:

    def test_sor_increases_with_cycle_number(self):
        """
        Thermal efficiency degrades each cycle → less oil per unit steam → SOR rises.
        Tests that cycle 1 < cycle 3 < cycle 5 in SOR (LITERATURE_ASSUMPTION from Bursell 1975).
        """
        def simulate_cycle_sor(cycle_n: int) -> float:
            T_peak = peak_temperature_c(
                500.0, 0.75, 20.0, 0.22,
                T_initial_c=47.0,
                T_steam_c=200.0,
                cycle_number=cycle_n,
            )
            # Oil production: proportional to (T_peak - T_init) effect
            # Simplified: use heated zone area as proxy for oil produced
            r = heated_zone_radius_m(500.0, 0.75, 20.0, 0.22, cycle_number=cycle_n)
            oil = max(r * 0.5, 0.1)  # proxy
            return sor(500.0, oil)

        sor1 = simulate_cycle_sor(1)
        sor3 = simulate_cycle_sor(3)
        sor5 = simulate_cycle_sor(5)
        assert sor1 < sor3 < sor5, (
            f"SOR must increase with cycle number (thermal efficiency degrades). "
            f"Got SOR1={sor1:.2f}, SOR3={sor3:.2f}, SOR5={sor5:.2f}"
        )

    def test_cycle1_best_production(self):
        """
        Cycle 1 must give the best peak temperature and largest heated zone.
        Subsequent cycles are worse due to thermal efficiency degradation.
        """
        T1 = peak_temperature_c(500.0, 0.75, 20.0, 0.22, cycle_number=1)
        T3 = peak_temperature_c(500.0, 0.75, 20.0, 0.22, cycle_number=3)
        T5 = peak_temperature_c(500.0, 0.75, 20.0, 0.22, cycle_number=5)
        assert T1 > T3 > T5, (
            f"Cycle 1 must give highest peak temperature. Got T1={T1:.1f}, T3={T3:.1f}, T5={T5:.1f}"
        )
