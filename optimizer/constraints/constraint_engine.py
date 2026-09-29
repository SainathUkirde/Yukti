"""
optimizer/constraints/constraint_engine.py
Hard engineering constraint checker for CSS and SRP recommendations.

Every recommendation produced by the optimizer is passed through this engine
BEFORE being shown to the user. Violations are surfaced, never hidden.

Hard Constraints (any violation blocks the recommendation):
  CSS:
    C1  Injection pressure < fracture pressure (depth × FPG)
    C2  Steam volume > 0 and within generator capacity
    C3  Soak days in [3, 90]
    C4  Steam quality in [0.50, 1.0]
    C5  Production cut-off WOR in [2, 25]

  SRP:
    C6  SPM in [1, 12]
    C7  Stroke length in [0.5, 4.5] m
    C8  VFD frequency in [20, 60] Hz
    C9  Polished-rod load ≤ rod allowable stress (Goodman ratio ≤ 1.0)
    C10 Pump fillage ≥ 0.40 (pump must be partially filled)
    C11 Rod floating ratio < 1.0 (rod fall speed ≥ plunger demand)

References:
  API RP 11L (2012); API Spec 11B (2013); Shigley (2011).
  Fracture pressure gradient: typical Rajasthan basin 0.0185 MPa/m.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.config import (
    FRACTURE_PRESSURE_GRADIENT_KPA_M,
    ROD_ENDURANCE_LIMIT_MPA,
    ROD_ULTIMATE_STRENGTH_MPA,
    SPM_MIN, SPM_MAX,
    STROKE_LENGTH_M_MIN, STROKE_LENGTH_M_MAX,
    VFD_FREQUENCY_HZ_MIN, VFD_FREQUENCY_HZ_MAX,
)
from simulator.srp.rod_float import rod_float_risk_ratio


@dataclass
class ConstraintViolation:
    """A single constraint violation."""
    constraint_id: str
    name: str
    description: str
    recommended_value: float
    limit_value: float
    unit: str
    severity: str          # "warning" | "critical"
    passed: bool = False


@dataclass
class ConstraintResult:
    """Full constraint check result for a set of parameters."""
    passed: bool                          # True only if ALL hard constraints pass
    violations: list[ConstraintViolation] = field(default_factory=list)
    checks: list[ConstraintViolation] = field(default_factory=list)   # all checks including passing

    @property
    def critical_violations(self) -> list[ConstraintViolation]:
        return [v for v in self.violations if v.severity == "critical"]

    @property
    def warning_violations(self) -> list[ConstraintViolation]:
        return [v for v in self.violations if v.severity == "warning"]


class ConstraintEngine:
    """
    Checks all hard engineering constraints for a CSS+SRP parameter set.
    Instantiated once at startup with well completion parameters.
    """

    def __init__(
        self,
        well_depth_m: float = 800.0,
        rod_diameter_m: float = 0.022225,
        steam_generator_capacity_m3_day: float = 200.0,
    ) -> None:
        self.well_depth_m = well_depth_m
        self.rod_diameter_m = rod_diameter_m
        self.steam_gen_cap = steam_generator_capacity_m3_day

        # Fracture pressure [kPa] = FPG [kPa/m] × depth [m]
        self.fracture_pressure_kpa = FRACTURE_PRESSURE_GRADIENT_KPA_M * well_depth_m

        # Rod cross-section [m²]
        self.A_rod = np.pi / 4.0 * rod_diameter_m**2

    def check(
        self,
        # CSS parameters
        injection_pressure_kpa: float,
        steam_volume_cwe_m3: float,
        soak_days: float,
        steam_quality: float,
        production_cutoff_wor: float,
        inject_duration_days: float = 7.0,
        # SRP parameters
        spm: float = 5.0,
        stroke_length_m: float = 2.4,
        vfd_frequency_hz: float = 45.0,
        peak_load_kn: float = 0.0,
        min_load_kn: float = 0.0,
        pump_fillage: float = 0.8,
        oil_viscosity_cp: float = 100.0,
        rod_string_length_m: float = 800.0,
    ) -> ConstraintResult:
        """
        Run all constraint checks and return a ConstraintResult.

        Parameters match the joint optimizer decision variables.
        All constraints documented with source in inline comments.
        """
        all_checks: list[ConstraintViolation] = []
        violations: list[ConstraintViolation] = []

        def _check(
            cid: str, name: str, desc: str,
            val: float, limit: float, unit: str,
            op: str,           # "lt" | "gt" | "between"
            severity: str,
            lo: float = None, hi: float = None,
        ) -> ConstraintViolation:
            if op == "lt":
                passed = val < limit
            elif op == "le":
                passed = val <= limit
            elif op == "gt":
                passed = val > limit
            elif op == "ge":
                passed = val >= limit
            elif op == "between":
                passed = (lo <= val <= hi)
                limit = hi
            else:
                passed = True
            cv = ConstraintViolation(
                constraint_id=cid, name=name, description=desc,
                recommended_value=val, limit_value=limit, unit=unit,
                severity=severity, passed=passed,
            )
            all_checks.append(cv)
            if not passed:
                violations.append(cv)
            return cv

        # ── C1: Injection pressure < fracture pressure ────────────────────
        _check(
            "C1", "Injection pressure below fracture",
            f"Injection pressure must be below fracture gradient × depth "
            f"({self.fracture_pressure_kpa:.0f} kPa). "
            f"Source: API RP 11L; Rajasthan FPG ~0.0185 MPa/m.",
            val=injection_pressure_kpa,
            limit=self.fracture_pressure_kpa,
            unit="kPa",
            op="lt",
            severity="critical",
        )

        # ── C2: Steam volume within generator capacity ────────────────────
        daily_steam_rate = steam_volume_cwe_m3 / max(inject_duration_days, 1.0)
        _check(
            "C2", "Steam rate within generator capacity",
            f"Daily steam rate must not exceed generator capacity ({self.steam_gen_cap} m³/day CWE).",
            val=daily_steam_rate,
            limit=self.steam_gen_cap,
            unit="m³/day",
            op="le",
            severity="warning",
        )

        # ── C3: Soak days ─────────────────────────────────────────────────
        _check(
            "C3", "Soak period in valid range [3, 90] days",
            "Soak period must be between 3 and 90 days. Source: CSS operations literature.",
            val=soak_days, limit=90.0, unit="days", op="between",
            severity="warning", lo=3.0, hi=90.0,
        )

        # ── C4: Steam quality ─────────────────────────────────────────────
        _check(
            "C4", "Steam quality in [0.50, 1.0]",
            "Steam quality (dryness fraction) must be 0.50–1.0. Source: Butler (1991).",
            val=steam_quality, limit=1.0, unit="fraction", op="between",
            severity="warning", lo=0.50, hi=1.0,
        )

        # ── C5: Production cut-off WOR ────────────────────────────────────
        _check(
            "C5", "Cut-off WOR in [2, 25]",
            "Production cut-off water-oil ratio must be 2–25. Source: Bursell & Pittman (1975).",
            val=production_cutoff_wor, limit=25.0, unit="m³/m³", op="between",
            severity="warning", lo=2.0, hi=25.0,
        )

        # ── C6: SPM range ─────────────────────────────────────────────────
        _check(
            "C6", f"SPM in [{SPM_MIN}, {SPM_MAX}]",
            "Strokes per minute must be within equipment rating. Source: API RP 11L.",
            val=spm, limit=SPM_MAX, unit="strokes/min", op="between",
            severity="critical", lo=SPM_MIN, hi=SPM_MAX,
        )

        # ── C7: Stroke length ─────────────────────────────────────────────
        _check(
            "C7", f"Stroke length in [{STROKE_LENGTH_M_MIN}, {STROKE_LENGTH_M_MAX}] m",
            "Stroke length within equipment range. Source: API RP 11L.",
            val=stroke_length_m, limit=STROKE_LENGTH_M_MAX, unit="m", op="between",
            severity="critical", lo=STROKE_LENGTH_M_MIN, hi=STROKE_LENGTH_M_MAX,
        )

        # ── C8: VFD frequency ─────────────────────────────────────────────
        _check(
            "C8", f"VFD frequency in [{VFD_FREQUENCY_HZ_MIN}, {VFD_FREQUENCY_HZ_MAX}] Hz",
            "VFD drive frequency within equipment limits.",
            val=vfd_frequency_hz, limit=VFD_FREQUENCY_HZ_MAX, unit="Hz", op="between",
            severity="critical", lo=VFD_FREQUENCY_HZ_MIN, hi=VFD_FREQUENCY_HZ_MAX,
        )

        # ── C9: Goodman rod stress ────────────────────────────────────────
        if peak_load_kn > 0 and min_load_kn >= 0:
            F_max_N = peak_load_kn * 1000.0
            F_min_N = min_load_kn * 1000.0
            A = self.A_rod
            sigma_mean = (F_max_N + F_min_N) / (2.0 * max(A, 1e-9))
            sigma_alt = (F_max_N - F_min_N) / (2.0 * max(A, 1e-9))
            Se = ROD_ENDURANCE_LIMIT_MPA * 1e6
            Su = ROD_ULTIMATE_STRENGTH_MPA * 1e6
            goodman = sigma_alt / Se + sigma_mean / Su
            _check(
                "C9", "Goodman rod stress criterion",
                "σ_alt/Se + σ_mean/Su ≤ 1.0. Source: Shigley (2011); API Spec 11B.",
                val=goodman, limit=1.0, unit="ratio", op="le",
                severity="critical",
            )

        # ── C10: Minimum pump fillage ─────────────────────────────────────
        _check(
            "C10", "Pump fillage ≥ 0.40",
            "Pump must be at least 40% filled per stroke for productive pumping. Source: Takacs (2015).",
            val=pump_fillage, limit=0.40, unit="fraction", op="ge",
            severity="warning",
        )

        # ── C11: Rod floating ratio < 1.0 ────────────────────────────────
        rf = rod_float_risk_ratio(
            stroke_length_m, spm, self.rod_diameter_m, rod_string_length_m, oil_viscosity_cp
        )
        _check(
            "C11", "Rod floating ratio < 1.0",
            f"N_rf = μ·SPM·SL / 6000 < 1.0 required to prevent rod floating. "
            f"Current N_rf = {rf:.3f}. Reduce SPM or stroke length. Source: Takacs (2015).",
            val=rf, limit=1.0, unit="ratio", op="lt",
            severity="critical",
        )

        return ConstraintResult(
            passed=len(violations) == 0,
            violations=violations,
            checks=all_checks,
        )

    def check_css_only(self, **kwargs) -> ConstraintResult:
        """Check CSS constraints only (no SRP params needed)."""
        defaults = dict(
            spm=5.0, stroke_length_m=2.4, vfd_frequency_hz=45.0,
            peak_load_kn=20.0, min_load_kn=5.0, pump_fillage=0.8,
            oil_viscosity_cp=200.0, rod_string_length_m=800.0,
        )
        defaults.update(kwargs)
        return self.check(**defaults)

    def check_srp_only(self, **kwargs) -> ConstraintResult:
        """Check SRP constraints only (with safe CSS defaults)."""
        defaults = dict(
            injection_pressure_kpa=4000.0, steam_volume_cwe_m3=500.0,
            soak_days=14.0, steam_quality=0.75, production_cutoff_wor=10.0,
        )
        defaults.update(kwargs)
        return self.check(**defaults)
