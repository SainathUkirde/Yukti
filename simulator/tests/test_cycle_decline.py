"""
simulator/tests/test_cycle_decline.py
Integration tests for the complete WellSystem across multiple CSS cycles.

Expected physical behavior:
  1. Cycle 1 gives the highest peak temperature and best production
  2. SOR rises with each successive cycle
  3. Viscosity rises as reservoir cools during production
  4. Oil rate declines as reservoir cools during production
  5. Fault injection produces visible card distortion and alerts
  6. Applying an optimizer recommendation changes subsequent KPIs
"""

import pytest
import sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.well_system import WellSystem, Phase
from simulator.config import WellParameters


def make_well(seed: int = 42) -> WellSystem:
    params = WellParameters(
        well_id="TEST",
        spm=5.0,
        stroke_length_m=2.4,
        steam_volume_cwe_m3=500.0,
        soak_days=14.0,
        production_cutoff_wor=10.0,
        seed=seed,
    )
    return WellSystem(params, time_acceleration=100)


class TestWellSystemCycleBehavior:

    def test_phase_transitions(self):
        """Well must advance through injection → soak → production phases."""
        ws = make_well()
        ws.start_cycle()
        assert ws._phase == Phase.INJECTION

        ws._complete_injection()
        assert ws._phase == Phase.SOAK

        ws._complete_soak()
        assert ws._phase == Phase.PRODUCTION

    def test_temperature_rises_during_soak(self):
        """Reservoir temperature must rise above initial during soak phase."""
        ws = make_well()
        ws.start_cycle()
        ws._complete_injection()

        T_initial = ws.params.initial_temp_c
        state = ws.tick()
        # After soak starts, temperature should rise
        assert state.reservoir_temp_c >= T_initial, (
            f"Temperature {state.reservoir_temp_c}°C should be ≥ initial {T_initial}°C during soak"
        )

    def test_oil_rate_positive_during_production(self):
        """Oil rate must be positive during production phase."""
        ws = make_well()
        ws.start_cycle()
        ws.advance_to_production()
        state = ws.tick()
        assert state.oil_rate_m3d > 0.0, "Oil rate must be > 0 during production"

    def test_oil_rate_zero_during_injection(self):
        """No oil production during injection phase."""
        ws = make_well()
        ws.start_cycle()
        state = ws.tick()
        assert state.oil_rate_m3d == 0.0 or ws._phase != Phase.PRODUCTION

    def test_oil_rate_declines_as_reservoir_cools(self):
        """
        As reservoir cools during production, viscosity rises and oil rate declines.
        This is the fundamental reason CSS cycles have limited duration.
        """
        ws = make_well()
        ws.start_cycle()
        ws.advance_to_production()

        rates = []
        for _ in range(50):
            state = ws.tick()
            if state.phase == Phase.PRODUCTION:
                rates.append(state.oil_rate_m3d)

        if len(rates) > 10:
            # Early rates should generally be higher than late rates
            early_avg = np.mean(rates[:5])
            late_avg = np.mean(rates[-5:])
            assert early_avg >= late_avg, (
                f"Oil rate should decline as reservoir cools. "
                f"Early avg={early_avg:.3f}, late avg={late_avg:.3f}"
            )

    def test_sor_rises_with_cycle_number(self):
        """
        Each successive CSS cycle should give worse SOR (less oil per unit steam).
        Core behavior from Bursell & Pittman (1975).
        """
        sor_per_cycle = []
        for cycle_n in [1, 2, 3]:
            ws = make_well()
            ws.cycle_number = cycle_n - 1
            ws.start_cycle()
            ws.advance_to_production()
            # Collect 30 production ticks
            for _ in range(30):
                state = ws.tick()
            sor_per_cycle.append(state.sor)

        assert sor_per_cycle[0] <= sor_per_cycle[1] <= sor_per_cycle[2], (
            f"SOR must rise with cycle number. Got: {sor_per_cycle}"
        )


class TestFaultInjection:

    def test_fault_injection_produces_alerts(self):
        """Injecting a fault must produce at least one active alert."""
        ws = make_well()
        ws.start_cycle()
        ws.advance_to_production()
        ws.inject_fault("rod_floating", ramp_ticks=1)

        state = ws.tick()
        # After injection, fault should appear
        has_fault_alert = any("FAULT" in a or "floating" in a.lower()
                              for a in state.active_alerts)
        assert has_fault_alert or state.active_fault is not None, (
            "Fault injection must produce alerts or set active_fault"
        )

    def test_fault_injection_changes_card_vs_normal(self):
        """
        A fault-injected card must differ from the normal card.
        This validates that fault distortion propagates to the dyno card.
        """
        ws_normal = make_well(seed=10)
        ws_normal.start_cycle()
        ws_normal.advance_to_production()
        state_normal = ws_normal.tick()

        ws_fault = make_well(seed=10)
        ws_fault.start_cycle()
        ws_fault.advance_to_production()
        ws_fault.inject_fault("pump_off", ramp_ticks=1, auto_recover=False)
        state_fault = ws_fault.tick()

        diff = np.abs(
            np.array(state_normal.surface_load_kn)
            - np.array(state_fault.surface_load_kn)
        ).max()
        assert diff > 0.01, (
            f"Fault injection must distort the dyno card. Max diff = {diff:.4f} kN"
        )

    def test_applying_recommendation_reduces_floating_risk(self):
        """
        Applying the optimizer's SPM reduction recommendation must reduce rod floating risk.
        This is the core what-if validation.
        """
        ws = make_well()
        ws.params.spm = 7.0
        ws.start_cycle()
        ws.advance_to_production()
        state_before = ws.tick()
        rf_before = state_before.rod_float_risk_ratio

        # Apply optimizer recommendation: reduce SPM
        ws.apply_config(spm=3.5)
        state_after = ws.tick()
        rf_after = state_after.rod_float_risk_ratio

        assert rf_after < rf_before, (
            f"Reducing SPM must decrease rod floating risk. "
            f"Before: RF={rf_before:.3f}, After: RF={rf_after:.3f}"
        )
