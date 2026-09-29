"""
simulator/well_system.py
Top-level WellSystem orchestrator — integrates all sub-models.

This is the single entry point for:
  - Advancing the simulation by one tick
  - Running a complete CSS cycle (injection → soak → production)
  - Injecting faults
  - Applying parameter updates (from optimizer recommendations)

State machine:
  idle → injection → soak → production → idle (next cycle)

One tick represents DEFAULT_TIME_ACCELERATION × TICK_INTERVAL_S seconds
of simulated time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional
import numpy as np

from .config import (
    WellParameters,
    THERMAL_DECAY_CONSTANT_PER_DAY,
    STEAM_TEMPERATURE_C,
    FLOWING_BOTTOMHOLE_PRESSURE_KPA,
    PI_REFERENCE_M3_DAY_KPA,
    VISCOSITY_REFERENCE_CP,
    MOTOR_EFFICIENCY,
    DYNO_CARD_POINTS,
    DEFAULT_TIME_ACCELERATION,
    TICK_INTERVAL_S,
    BARRELS_PER_M3,
    ROD_ENDURANCE_LIMIT_MPA,
    ROD_ULTIMATE_STRENGTH_MPA,
)
from .reservoir.heated_zone import (
    heated_zone_radius_m,
    peak_temperature_c,
    reservoir_temperature_c,
    sor as compute_sor,
)
from .reservoir.ipr import (
    vogel_oil_rate,
    water_oil_ratio,
    water_cut_from_wor,
    reservoir_pressure_decline,
)
from .wellbore.viscosity import viscosity_cp
from .srp.wave_equation import simulate_stroke, DynoCardResult
from .srp.rod_float import rod_float_risk_ratio, rod_float_risk_score_0_100, is_rod_floating
from .srp.faults import FaultInjector
from .sensor.noise import WellSensorLayer, twin_sensor_deviation_pct


# ── CSS Phase enum ──────────────────────────────────────────────────────────

class Phase:
    IDLE = "idle"
    INJECTION = "injection"
    SOAK = "soak"
    PRODUCTION = "production"


# ── Well state snapshot ─────────────────────────────────────────────────────

@dataclass
class WellStateSnapshot:
    """
    Complete state of the well at one simulation tick.
    All values are TRUE physics values (before sensor noise).
    Sensor-measured values are in the 'measured' dict.
    """
    # Identity
    well_id: str
    tick: int
    sim_time_days: float
    cycle_number: int
    phase: str
    time_in_phase_days: float

    # Reservoir (true physics)
    reservoir_temp_c: float
    heated_zone_radius_m: float
    reservoir_pressure_kpa: float
    oil_viscosity_cp: float
    T_peak_c: float

    # Production
    oil_rate_m3d: float
    water_rate_m3d: float
    water_cut_fraction: float
    cum_oil_m3: float
    cum_water_m3: float
    sor: float

    # SRP
    spm: float
    stroke_length_m: float
    vfd_frequency_hz: float
    peak_load_kn: float
    min_load_kn: float
    pump_fillage_fraction: float
    pump_efficiency_fraction: float
    motor_power_kw: float
    kwh_per_bbl: float
    rod_fall_speed_ms: float
    plunger_demand_ms: float
    rod_float_risk_ratio: float
    rod_float_risk_score: float

    # Goodman stress
    goodman_ratio: float

    # Faults & alerts
    active_fault: Optional[str]
    fault_severity: float
    active_alerts: list[str]

    # Dyno cards
    surface_position_m: list[float]
    surface_load_kn: list[float]
    downhole_position_m: list[float]
    downhole_load_kn: list[float]

    # Sensor-measured values (with noise)
    measured: dict[str, Any]

    # Twin vs sensor deviation
    twin_sensor_deviation_pct: float

    # Config in use at this tick
    config: WellParameters


# ── WellSystem ──────────────────────────────────────────────────────────────

class WellSystem:
    """
    Full well system simulator.

    Usage:
        ws = WellSystem(WellParameters(well_id="W01"))
        ws.start_cycle()          # begin CSS injection
        for _ in range(N):
            state = ws.tick()     # advance one time step
    """

    def __init__(
        self,
        params: WellParameters,
        time_acceleration: int = DEFAULT_TIME_ACCELERATION,
        tick_interval_s: float = TICK_INTERVAL_S,
    ) -> None:
        self.params = params
        self.time_acceleration = time_acceleration
        self.tick_interval_s = tick_interval_s

        # Simulated time step per tick [days]
        self._dt_days = (tick_interval_s * time_acceleration) / 86400.0

        # State
        self._tick: int = 0
        self._sim_time_days: float = 0.0
        self._phase: str = Phase.IDLE
        self._time_in_phase_days: float = 0.0
        self.cycle_number: int = 0

        # Reservoir state
        self._T_peak_c: float = params.initial_temp_c
        self._reservoir_pressure_kpa: float = params.reservoir_pressure_kpa
        self._T_production_start_days: float = 0.0
        self._t_production_days: float = 0.0
        self._t_injection_days: float = 0.0

        # Cumulative production
        self._cum_oil_m3: float = 0.0
        self._cum_water_m3: float = 0.0
        self._cycle_oil_m3: float = 0.0

        # SRP config (can be updated by optimizer)
        self._spm: float = params.spm
        self._stroke_length_m: float = params.stroke_length_m
        self._vfd_frequency_hz: float = params.vfd_frequency_hz

        # Sub-systems
        self._fault_injector = FaultInjector()
        self._sensor_layer = WellSensorLayer(seed=params.seed)

        # RNG
        self._rng = np.random.default_rng(params.seed)

    # ── Public API ───────────────────────────────────────────────────────────

    def start_cycle(self, cycle_number: Optional[int] = None) -> None:
        """Begin a new CSS injection phase."""
        if cycle_number is not None:
            self.cycle_number = cycle_number
        else:
            self.cycle_number += 1
        self._phase = Phase.INJECTION
        self._time_in_phase_days = 0.0
        self._t_injection_days = 0.0
        self._cycle_oil_m3 = 0.0
        # Re-pressurize reservoir on injection start (steam pushes pressure up)
        pressure_boost = self.params.injection_pressure_kpa * 0.15
        self._reservoir_pressure_kpa = min(
            self.params.reservoir_pressure_kpa + pressure_boost,
            self.params.injection_pressure_kpa * 0.95,
        )

    def advance_to_production(self) -> None:
        """
        Advance the well through injection and soak phases instantly.
        Used by the surrogate accuracy test.
        """
        # Complete injection
        self._phase = Phase.INJECTION
        self._time_in_phase_days = self.params.soak_days  # skip through
        self._complete_injection()
        # Complete soak
        self._phase = Phase.SOAK
        self._time_in_phase_days = self.params.soak_days
        self._complete_soak()

    def inject_fault(
        self,
        fault_type: str,
        ramp_ticks: int = 30,
        auto_recover: bool = True,
    ) -> None:
        """Inject a fault into the simulation."""
        self._fault_injector.inject(fault_type, self._tick, ramp_ticks, auto_recover)

    def resolve_fault(self, fault_type: str) -> None:
        """Manually resolve an active fault."""
        self._fault_injector.resolve(fault_type, self._tick)

    def apply_config(self, **kwargs: float) -> None:
        """
        Apply optimizer recommendation: update operating parameters.
        Accepted keys: spm, stroke_length_m, vfd_frequency_hz,
                       steam_volume_cwe_m3, injection_pressure_kpa,
                       soak_days, production_cutoff_wor.
        """
        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, float(value))
        # Also update live SRP settings
        self._spm = self.params.spm
        self._stroke_length_m = self.params.stroke_length_m
        self._vfd_frequency_hz = self.params.vfd_frequency_hz

    def tick(self) -> WellStateSnapshot:
        """
        Advance the simulation by one time step and return the new state.

        Physics chain per tick:
          1. Advance phase timer; handle phase transitions
          2. Compute reservoir temperature
          3. Compute oil viscosity (Walther/ASTM D341)
          4. Compute reservoir pressure decline
          5. Compute oil rate (Vogel IPR)
          6. Simulate SRP stroke (wave equation)
          7. Update cumulative production
          8. Check cut-off criterion; advance to next phase
          9. Check for rod floating; auto-resolve if applicable
         10. Compute Goodman stress ratio
         11. Apply sensor noise
         12. Build and return WellStateSnapshot
        """
        self._tick += 1
        self._sim_time_days += self._dt_days
        self._time_in_phase_days += self._dt_days

        # ── 1. Phase transitions ──────────────────────────────────────────
        if self._phase == Phase.IDLE:
            return self._idle_tick()

        if self._phase == Phase.INJECTION:
            # Injection runs for a fixed duration
            inject_duration = getattr(self.params, '_inject_duration_days', 7.0)
            if self._time_in_phase_days >= inject_duration:
                self._complete_injection()

        elif self._phase == Phase.SOAK:
            if self._time_in_phase_days >= self.params.soak_days:
                self._complete_soak()

        # ── 2. Reservoir temperature ──────────────────────────────────────
        if self._phase in (Phase.INJECTION, Phase.SOAK):
            # During injection/soak, temperature rises toward T_peak linearly
            progress = min(self._time_in_phase_days / max(self.params.soak_days, 1.0), 1.0)
            T_res = (self.params.initial_temp_c +
                     (self._T_peak_c - self.params.initial_temp_c) * progress)
        else:
            # During production, reservoir cools exponentially
            T_res = reservoir_temperature_c(
                self._T_peak_c,
                self.params.initial_temp_c,
                self._t_production_days,
                THERMAL_DECAY_CONSTANT_PER_DAY,
            )

        # ── 3. Viscosity ──────────────────────────────────────────────────
        mu = viscosity_cp(T_res, self.params.api_gravity)

        # ── 4. Reservoir pressure ─────────────────────────────────────────
        if self._phase == Phase.PRODUCTION:
            self._reservoir_pressure_kpa = reservoir_pressure_decline(
                self._reservoir_pressure_kpa,
                self._dt_days,
                decline_rate_per_day=0.002,
            )

        # ── 5. Oil rate (Vogel IPR) ───────────────────────────────────────
        if self._phase == Phase.PRODUCTION:
            q_oil = vogel_oil_rate(
                self._reservoir_pressure_kpa,
                FLOWING_BOTTOMHOLE_PRESSURE_KPA,
                mu,
                PI_REFERENCE_M3_DAY_KPA,
                VISCOSITY_REFERENCE_CP,
            )
            wor = water_oil_ratio(
                self._t_production_days,
                self._T_peak_c,
                self.params.initial_temp_c,
            )
            wc = water_cut_from_wor(wor)
            q_water = q_oil * wor
        else:
            q_oil = 0.0
            wor = 0.0
            wc = 0.0
            q_water = 0.0

        # ── 6. SRP stroke simulation ──────────────────────────────────────
        fault_type, fault_severity = self._fault_injector.active_fault(self._tick)

        # During injection/soak the pump is idle — run with minimal SPM so
        # the dyno card is physically present but shows near-zero output.
        _active_spm = self._spm if self._phase == Phase.PRODUCTION else 0.5

        dyno: DynoCardResult = simulate_stroke(
            stroke_length_m=self._stroke_length_m,
            spm=_active_spm,
            rod_length_m=self.params.rod_string_length_m,
            rod_diameter_m=self.params.rod_diameter_m,
            plunger_dia_m=self.params.pump_plunger_dia_m,
            oil_viscosity_cp=mu,
            reservoir_pressure_kpa=self._reservoir_pressure_kpa,
            oil_rate_m3d=max(q_oil, 0.001),
            pump_depth_m=self.params.depth_m,
            motor_efficiency=MOTOR_EFFICIENCY,
            fault_type=fault_type,
            fault_severity=fault_severity,
            n_points=DYNO_CARD_POINTS,
        )

        # ── 7. Production accounting ──────────────────────────────────────
        oil_increment = q_oil * self._dt_days
        water_increment = q_water * self._dt_days
        self._cum_oil_m3 += oil_increment
        self._cum_water_m3 += water_increment
        self._cycle_oil_m3 += oil_increment
        if self._phase == Phase.PRODUCTION:
            self._t_production_days += self._dt_days

        # ── 8. Cut-off check ──────────────────────────────────────────────
        if self._phase == Phase.PRODUCTION and wor >= self.params.production_cutoff_wor:
            self._phase = Phase.IDLE
            self._time_in_phase_days = 0.0

        # ── 9. Auto-resolve rod floating ─────────────────────────────────
        rf_ratio = dyno.rod_float_risk
        self._fault_injector.auto_resolve_rod_float(self._tick, rf_ratio)

        # ── 10. Goodman rod stress ratio ──────────────────────────────────
        goodman_ratio = self._goodman_ratio(dyno.peak_load_kn, dyno.min_load_kn)

        # ── 11. Alerts ────────────────────────────────────────────────────
        alerts = self._build_alerts(rf_ratio, goodman_ratio, wor, fault_type)

        # ── 12. SOR ───────────────────────────────────────────────────────
        # Return 0.0 when no oil produced yet (injection/soak phase);
        # avoids 999 or 500000 SOR sentinel being displayed as a KPI.
        if self._cycle_oil_m3 <= 0.0:
            sor_val = 0.0
        else:
            sor_val = compute_sor(
                self.params.steam_volume_cwe_m3,
                self._cycle_oil_m3,
            )

        # ── 13. Heated zone radius ────────────────────────────────────────
        r_h = heated_zone_radius_m(
            self.params.steam_volume_cwe_m3,
            self.params.steam_quality,
            self.params.pay_thickness_m,
            self.params.porosity,
            self.params.initial_temp_c,
            STEAM_TEMPERATURE_C,
            cycle_number=self.cycle_number,
        )

        # ── Sensor noise ─────────────────────────────────────────────────
        true_dict = {
            "oil_rate_m3d": q_oil,
            "water_rate_m3d": q_water,
            "reservoir_temp_c": T_res,
            "reservoir_pressure_kpa": self._reservoir_pressure_kpa,
            "polished_rod_load_kn": dyno.peak_load_kn,
        }
        measured_dict = self._sensor_layer.apply(true_dict)
        twin_dev = twin_sensor_deviation_pct(true_dict, measured_dict)

        # ── Assemble state ────────────────────────────────────────────────
        return WellStateSnapshot(
            well_id=self.params.well_id,
            tick=self._tick,
            sim_time_days=self._sim_time_days,
            cycle_number=self.cycle_number,
            phase=self._phase,
            time_in_phase_days=self._time_in_phase_days,
            reservoir_temp_c=T_res,
            heated_zone_radius_m=r_h,
            reservoir_pressure_kpa=self._reservoir_pressure_kpa,
            oil_viscosity_cp=mu,
            T_peak_c=self._T_peak_c,
            oil_rate_m3d=q_oil,
            water_rate_m3d=q_water,
            water_cut_fraction=wc,
            cum_oil_m3=self._cum_oil_m3,
            cum_water_m3=self._cum_water_m3,
            sor=sor_val,
            spm=_active_spm,
            stroke_length_m=self._stroke_length_m,
            vfd_frequency_hz=self._vfd_frequency_hz,
            peak_load_kn=dyno.peak_load_kn,
            min_load_kn=dyno.min_load_kn,
            pump_fillage_fraction=dyno.fillage_fraction if self._phase == Phase.PRODUCTION else 0.0,
            pump_efficiency_fraction=dyno.pump_efficiency_fraction if self._phase == Phase.PRODUCTION else 0.0,
            motor_power_kw=dyno.motor_power_kw,
            kwh_per_bbl=dyno.kwh_per_bbl if self._phase == Phase.PRODUCTION else 0.0,
            rod_fall_speed_ms=dyno.rod_fall_speed_ms,
            plunger_demand_ms=dyno.plunger_demand_ms,
            rod_float_risk_ratio=rf_ratio,
            rod_float_risk_score=rod_float_risk_score_0_100(rf_ratio),
            goodman_ratio=goodman_ratio,
            active_fault=fault_type,
            fault_severity=fault_severity,
            active_alerts=alerts,
            surface_position_m=dyno.surface_position_m.tolist(),
            surface_load_kn=dyno.surface_load_kn.tolist(),
            downhole_position_m=dyno.downhole_position_m.tolist(),
            downhole_load_kn=dyno.downhole_load_kn.tolist(),
            measured=measured_dict,
            twin_sensor_deviation_pct=twin_dev,
            config=self.params,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _idle_tick(self) -> WellStateSnapshot:
        """Return minimal state during idle phase."""
        mu = viscosity_cp(self.params.initial_temp_c, self.params.api_gravity)
        dyno = simulate_stroke(
            stroke_length_m=self._stroke_length_m,
            spm=0.5,  # minimal idle pumping
            rod_length_m=self.params.rod_string_length_m,
            rod_diameter_m=self.params.rod_diameter_m,
            plunger_dia_m=self.params.pump_plunger_dia_m,
            oil_viscosity_cp=mu,
            reservoir_pressure_kpa=self._reservoir_pressure_kpa,
            oil_rate_m3d=0.1,
            pump_depth_m=self.params.depth_m,
        )
        true_dict: dict[str, Any] = {
            "oil_rate_m3d": 0.0,
            "water_rate_m3d": 0.0,
            "reservoir_temp_c": self.params.initial_temp_c,
            "reservoir_pressure_kpa": self._reservoir_pressure_kpa,
            "polished_rod_load_kn": dyno.peak_load_kn,
        }
        return WellStateSnapshot(
            well_id=self.params.well_id,
            tick=self._tick,
            sim_time_days=self._sim_time_days,
            cycle_number=self.cycle_number,
            phase=Phase.IDLE,
            time_in_phase_days=self._time_in_phase_days,
            reservoir_temp_c=self.params.initial_temp_c,
            heated_zone_radius_m=0.0,
            reservoir_pressure_kpa=self._reservoir_pressure_kpa,
            oil_viscosity_cp=mu,
            T_peak_c=self.params.initial_temp_c,
            oil_rate_m3d=0.0,
            water_rate_m3d=0.0,
            water_cut_fraction=0.0,
            cum_oil_m3=self._cum_oil_m3,
            cum_water_m3=self._cum_water_m3,
            sor=0.0,
            spm=0.5,
            stroke_length_m=self._stroke_length_m,
            vfd_frequency_hz=self._vfd_frequency_hz,
            peak_load_kn=dyno.peak_load_kn,
            min_load_kn=dyno.min_load_kn,
            pump_fillage_fraction=0.0,
            pump_efficiency_fraction=0.0,
            motor_power_kw=dyno.motor_power_kw,
            kwh_per_bbl=0.0,
            rod_fall_speed_ms=dyno.rod_fall_speed_ms,
            plunger_demand_ms=dyno.plunger_demand_ms,
            rod_float_risk_ratio=0.0,
            rod_float_risk_score=0.0,
            goodman_ratio=0.0,
            active_fault=None,
            fault_severity=0.0,
            active_alerts=[],
            surface_position_m=dyno.surface_position_m.tolist(),
            surface_load_kn=dyno.surface_load_kn.tolist(),
            downhole_position_m=dyno.downhole_position_m.tolist(),
            downhole_load_kn=dyno.downhole_load_kn.tolist(),
            measured=true_dict,
            twin_sensor_deviation_pct=0.0,
            config=self.params,
        )

    def _complete_injection(self) -> None:
        """Compute T_peak and transition to soak."""
        self._T_peak_c = peak_temperature_c(
            self.params.steam_volume_cwe_m3,
            self.params.steam_quality,
            self.params.pay_thickness_m,
            self.params.porosity,
            self.params.initial_temp_c,
            STEAM_TEMPERATURE_C,
            cycle_number=self.cycle_number,
        )
        self._phase = Phase.SOAK
        self._time_in_phase_days = 0.0

    def _complete_soak(self) -> None:
        """Transition from soak to production."""
        self._phase = Phase.PRODUCTION
        self._time_in_phase_days = 0.0
        self._t_production_days = 0.0
        self._cycle_oil_m3 = 0.0

    def _goodman_ratio(self, peak_load_kn: float, min_load_kn: float) -> float:
        """
        Compute Goodman fatigue ratio for the rod string.

        Goodman criterion [Shigley 2011; API Spec 11B]:
          σ_mean = (F_max + F_min) / (2 · A_rod)
          σ_alt  = (F_max - F_min) / (2 · A_rod)
          ratio  = σ_alt/S_e + σ_mean/S_u   ← must be ≤ 1.0

        Ratio > 1.0 → constraint violation → rod failure risk is HIGH.
        """
        A_rod = np.pi / 4.0 * self.params.rod_diameter_m**2
        F_max_N = peak_load_kn * 1000.0
        F_min_N = min_load_kn * 1000.0
        A_m2 = A_rod

        sigma_mean_pa = (F_max_N + F_min_N) / (2.0 * max(A_m2, 1e-6))
        sigma_alt_pa = (F_max_N - F_min_N) / (2.0 * max(A_m2, 1e-6))

        Se_pa = ROD_ENDURANCE_LIMIT_MPA * 1e6
        Su_pa = ROD_ULTIMATE_STRENGTH_MPA * 1e6

        ratio = sigma_alt_pa / max(Se_pa, 1.0) + sigma_mean_pa / max(Su_pa, 1.0)
        return float(max(ratio, 0.0))

    def _build_alerts(
        self,
        rf_ratio: float,
        goodman_ratio: float,
        wor: float,
        fault_type: Optional[str],
    ) -> list[str]:
        """Build list of active alert strings from current state."""
        alerts = []
        if rf_ratio >= 1.0:
            severity = "CRITICAL" if rf_ratio >= 1.5 else "WARNING"
            alerts.append(f"{severity}: Rod floating risk (RF={rf_ratio:.2f})")
        if goodman_ratio >= 0.85:
            alerts.append(f"WARNING: Rod stress approaching limit (Goodman={goodman_ratio:.2f})")
        if goodman_ratio >= 1.0:
            alerts.append("CRITICAL: Goodman criterion violated — rod failure risk")
        if wor >= self.params.production_cutoff_wor * 0.85:
            alerts.append(f"INFO: WOR approaching cut-off ({wor:.1f}/{self.params.production_cutoff_wor:.1f})")
        if fault_type:
            alerts.append(f"FAULT DETECTED: {fault_type.replace('_', ' ').title()}")
        return alerts
