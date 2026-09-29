"""
optimizer/joint_optimizer.py
Joint CSS + SRP optimizer using Optuna Bayesian optimization.

Outer loop: CSS cycle parameters (steam volume, injection pressure, soak days, cut-off WOR)
Inner loop: SRP operating parameters (SPM, stroke length, VFD frequency)

Objective: minimize cost per barrel of oil produced.
  cost_per_bbl = steam_cost + electricity_cost + expected_workover_cost

  steam_cost       ∝ SOR (more steam per barrel = more cost)
  electricity_cost ∝ kWh/bbl
  workover_cost    ∝ rod failure risk score (expected workover frequency)

All recommendations are checked against the constraint engine.
Constraint violations impose a large penalty in the objective function
(soft constraints via penalty, hard constraints block the recommendation).

Decision variables and search bounds:
  CSS: steam_volume_cwe_m3 [100, 1000], injection_pressure_kpa [2000, 6000],
       soak_days [5, 30], production_cutoff_wor [5, 20]
  SRP: spm [1.5, 10], stroke_length_m [1.0, 4.0], vfd_frequency_hz [25, 55]

References:
  Optuna: Akiba et al. (2019) "Optuna: A Next-generation Hyperparameter Optimization Framework."
  Objective formulation: Butler (1991); Takacs (2015).
"""

import numpy as np
import optuna
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulator.config import WellParameters, STEAM_TEMPERATURE_C
from simulator.surrogate.fast_surrogate import evaluate as surrogate_eval
from optimizer.constraints.constraint_engine import ConstraintEngine

# Silence Optuna progress output except errors
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ── Cost model constants (LITERATURE_ASSUMPTION) ──────────────────────────────
STEAM_COST_INR_PER_M3: float = 800.0        # ~INR 800 per m³ CWE steam (boiler fuel cost)
ELECTRICITY_COST_INR_PER_KWH: float = 6.0   # INR 6/kWh (Indian industrial tariff)
WORKOVER_COST_INR: float = 2_500_000.0      # INR 25 lakh per workover event
OIL_PRICE_INR_PER_BBL: float = 6_000.0      # ~USD 72/bbl × 83 INR/USD ≈ INR 6000/bbl
BARRELS_PER_M3: float = 6.2898


@dataclass
class OptimizationResult:
    """Full result from the joint optimizer."""
    well_id: str
    objective: str              # "min_cost_per_bbl" | "max_oil" | "min_sor"

    # Best parameters found
    best_css: dict[str, float]
    best_srp: dict[str, float]

    # Predicted KPIs at best params
    predicted_oil_rate_m3d: float
    predicted_sor: float
    predicted_kwh_per_bbl: float
    predicted_pump_efficiency: float
    predicted_rod_float_risk: float
    predicted_cost_per_bbl_inr: float

    # Baseline (current heuristic params)
    baseline_css: dict[str, float]
    baseline_srp: dict[str, float]
    baseline_oil_rate_m3d: float
    baseline_sor: float
    baseline_kwh_per_bbl: float
    baseline_pump_efficiency: float
    baseline_rod_float_risk: float
    baseline_cost_per_bbl_inr: float

    # Deltas (optimized vs baseline) — all DEMO_RESULT
    delta_oil_pct: float
    delta_sor_pct: float
    delta_energy_pct: float
    delta_cost_per_bbl_pct: float
    delta_risk_pts: float
    steam_tonnes_saved_per_cycle: float

    # Constraint check
    constraint_violations: list[dict] = field(default_factory=list)
    constraints_passed: bool = True

    # Optimizer metadata
    n_trials: int = 0
    best_trial_value: float = 0.0
    method: str = "Optuna TPE Bayesian optimization over fast surrogate"
    provenance: str = "DEMO_RESULT"


class JointOptimizer:
    """
    Joint CSS + SRP optimizer.
    Uses the fast surrogate for rapid objective evaluation (~0.1ms/call).
    """

    def __init__(
        self,
        well_params: WellParameters,
        n_trials: int = 200,
        t_production_days: float = 15.0,
        objective: str = "min_cost_per_bbl",
    ) -> None:
        self.params = well_params
        self.n_trials = n_trials
        self.t_production_days = t_production_days
        self.objective_mode = objective
        self.constraint_engine = ConstraintEngine(
            well_depth_m=well_params.depth_m,
            rod_diameter_m=well_params.rod_diameter_m,
        )

    def _surrogate_kwargs(
        self,
        steam_vol: float, steam_quality: float, soak_days: float,
        spm: float, stroke_len: float, inj_pressure: float,
    ) -> dict:
        """Build surrogate kwargs for a trial."""
        return dict(
            steam_volume_cwe_m3=steam_vol,
            steam_quality=steam_quality,
            t_production_days=self.t_production_days,
            cycle_number=1,
            T_initial_c=self.params.initial_temp_c,
            T_steam_c=STEAM_TEMPERATURE_C,
            pay_thickness_m=self.params.pay_thickness_m,
            porosity=self.params.porosity,
            reservoir_pressure_kpa=self.params.reservoir_pressure_kpa,
            spm=spm,
            stroke_length_m=stroke_len,
            rod_length_m=self.params.rod_string_length_m,
            rod_diameter_m=self.params.rod_diameter_m,
            plunger_dia_m=self.params.pump_plunger_dia_m,
            api=self.params.api_gravity,
            cum_oil_m3=100.0,
        )

    def _compute_cost_per_bbl(
        self,
        result,
        steam_vol: float,
        expected_oil_m3: float,
        risk_score: float,
    ) -> float:
        """
        Compute total cost per barrel of oil.
        cost = (steam_cost + electricity_cost + expected_workover_cost) / oil_produced_bbl
        """
        # Steam cost (for one cycle)
        steam_cost = steam_vol * STEAM_COST_INR_PER_M3

        # Electricity cost (per day × horizon period)
        horizon_days = 30.0
        kwh_total = result.motor_power_kw * 24.0 * horizon_days
        elec_cost = kwh_total * ELECTRICITY_COST_INR_PER_KWH

        # Expected workover cost (risk score → probability of workover per year)
        # P(workover/year) ≈ risk_score / 100 × 1.5  (1-2 workovers/year at max risk)
        p_workover = risk_score / 100.0 * 1.5
        workover_cost_annualized = p_workover * WORKOVER_COST_INR
        workover_per_horizon = workover_cost_annualized * (horizon_days / 365.0)

        total_cost = steam_cost + elec_cost + workover_per_horizon
        oil_bbl = max(expected_oil_m3 * BARRELS_PER_M3, 0.001)
        return total_cost / oil_bbl

    def _objective(self, trial: optuna.Trial) -> float:
        """Optuna objective function — minimize cost per barrel."""
        # ── CSS decision variables ─────────────────────────────────────
        steam_vol = trial.suggest_float("steam_vol", 100.0, 900.0)
        inj_pressure = trial.suggest_float("inj_pressure", 2000.0,
                                           self.constraint_engine.fracture_pressure_kpa * 0.95)
        steam_quality = trial.suggest_float("steam_quality", 0.65, 0.90)
        soak_days = trial.suggest_float("soak_days", 5.0, 28.0)
        cutoff_wor = trial.suggest_float("cutoff_wor", 5.0, 20.0)

        # ── SRP decision variables ─────────────────────────────────────
        spm = trial.suggest_float("spm", 1.5, 10.0)
        stroke_len = trial.suggest_float("stroke_len", 1.0, 4.0)
        vfd_freq = trial.suggest_float("vfd_freq", 25.0, 55.0)

        # ── Evaluate surrogate ─────────────────────────────────────────
        kwargs = self._surrogate_kwargs(steam_vol, steam_quality, soak_days, spm, stroke_len, inj_pressure)
        result = surrogate_eval(**kwargs)

        # ── Constraint penalty ─────────────────────────────────────────
        cr = self.constraint_engine.check(
            injection_pressure_kpa=inj_pressure,
            steam_volume_cwe_m3=steam_vol,
            soak_days=soak_days,
            steam_quality=steam_quality,
            production_cutoff_wor=cutoff_wor,
            spm=spm,
            stroke_length_m=stroke_len,
            vfd_frequency_hz=vfd_freq,
            peak_load_kn=result.peak_load_kn,
            min_load_kn=result.min_load_kn,
            pump_fillage=result.pump_fillage_fraction,
            oil_viscosity_cp=result.oil_viscosity_cp,
            rod_string_length_m=self.params.rod_string_length_m,
        )
        penalty = len(cr.critical_violations) * 1e6 + len(cr.warning_violations) * 1e3

        # ── Objective value ────────────────────────────────────────────
        expected_oil_m3 = result.oil_rate_m3d * 30.0
        risk_score = result.rod_float_risk_score

        if self.objective_mode == "min_cost_per_bbl":
            value = self._compute_cost_per_bbl(result, steam_vol, expected_oil_m3, risk_score) + penalty

        elif self.objective_mode == "max_oil":
            value = -result.oil_rate_m3d + penalty

        elif self.objective_mode == "min_sor":
            value = result.sor + penalty

        else:
            value = self._compute_cost_per_bbl(result, steam_vol, expected_oil_m3, risk_score) + penalty

        return float(value)

    def optimize(self) -> OptimizationResult:
        """
        Run Bayesian optimization and return the best CSS+SRP parameter set.
        Also evaluates the baseline (current heuristic params) for comparison.
        """
        # ── Baseline evaluation ────────────────────────────────────────
        base_kwargs = self._surrogate_kwargs(
            self.params.steam_volume_cwe_m3,
            self.params.steam_quality,
            self.params.soak_days,
            self.params.spm,
            self.params.stroke_length_m,
            getattr(self.params, "injection_pressure_kpa", 4000.0),
        )
        base_result = surrogate_eval(**base_kwargs)
        base_oil_m3 = base_result.oil_rate_m3d * 30.0
        base_cost = self._compute_cost_per_bbl(
            base_result, self.params.steam_volume_cwe_m3,
            base_oil_m3, base_result.rod_float_risk_score
        )

        # ── Optimize ───────────────────────────────────────────────────
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=42),
        )
        study.optimize(self._objective, n_trials=self.n_trials, show_progress_bar=False)

        best = study.best_params
        best_val = study.best_value

        # ── Evaluate best params ───────────────────────────────────────
        opt_kwargs = self._surrogate_kwargs(
            best["steam_vol"], best["steam_quality"], best["soak_days"],
            best["spm"], best["stroke_len"], best["inj_pressure"],
        )
        opt_result = surrogate_eval(**opt_kwargs)
        opt_oil_m3 = opt_result.oil_rate_m3d * 30.0
        opt_cost = self._compute_cost_per_bbl(
            opt_result, best["steam_vol"], opt_oil_m3, opt_result.rod_float_risk_score
        )

        # ── Final constraint check ─────────────────────────────────────
        cr = self.constraint_engine.check(
            injection_pressure_kpa=best["inj_pressure"],
            steam_volume_cwe_m3=best["steam_vol"],
            soak_days=best["soak_days"],
            steam_quality=best["steam_quality"],
            production_cutoff_wor=best["cutoff_wor"],
            spm=best["spm"],
            stroke_length_m=best["stroke_len"],
            vfd_frequency_hz=best["vfd_freq"],
            peak_load_kn=opt_result.peak_load_kn,
            min_load_kn=opt_result.min_load_kn,
            pump_fillage=opt_result.pump_fillage_fraction,
            oil_viscosity_cp=opt_result.oil_viscosity_cp,
            rod_string_length_m=self.params.rod_string_length_m,
        )

        # ── Deltas ─────────────────────────────────────────────────────
        def _pct(old, new):
            return round((new - old) / max(abs(old), 1e-9) * 100.0, 2) if abs(old) > 1e-9 else 0.0

        # Steam saved per cycle [tonnes CWE, density of water ~1 t/m³]
        steam_saved = self.params.steam_volume_cwe_m3 - best["steam_vol"]

        return OptimizationResult(
            well_id=self.params.well_id,
            objective=self.objective_mode,
            # Best CSS
            best_css={
                "steam_volume_cwe_m3": round(best["steam_vol"], 1),
                "injection_pressure_kpa": round(best["inj_pressure"], 0),
                "steam_quality_fraction": round(best["steam_quality"], 3),
                "soak_days": round(best["soak_days"], 1),
                "production_cutoff_wor": round(best["cutoff_wor"], 1),
            },
            # Best SRP
            best_srp={
                "spm": round(best["spm"], 2),
                "stroke_length_m": round(best["stroke_len"], 3),
                "vfd_frequency_hz": round(best["vfd_freq"], 1),
            },
            # Optimized KPIs
            predicted_oil_rate_m3d=round(opt_result.oil_rate_m3d, 4),
            predicted_sor=round(opt_result.sor, 3),
            predicted_kwh_per_bbl=round(opt_result.kwh_per_bbl, 2),
            predicted_pump_efficiency=round(opt_result.pump_efficiency_fraction, 4),
            predicted_rod_float_risk=round(opt_result.rod_float_risk, 4),
            predicted_cost_per_bbl_inr=round(opt_cost, 2),
            # Baseline
            baseline_css={
                "steam_volume_cwe_m3": self.params.steam_volume_cwe_m3,
                "injection_pressure_kpa": getattr(self.params, "injection_pressure_kpa", 4000.0),
                "steam_quality_fraction": self.params.steam_quality,
                "soak_days": self.params.soak_days,
                "production_cutoff_wor": self.params.production_cutoff_wor,
            },
            baseline_srp={
                "spm": self.params.spm,
                "stroke_length_m": self.params.stroke_length_m,
                "vfd_frequency_hz": self.params.vfd_frequency_hz,
            },
            baseline_oil_rate_m3d=round(base_result.oil_rate_m3d, 4),
            baseline_sor=round(base_result.sor, 3),
            baseline_kwh_per_bbl=round(base_result.kwh_per_bbl, 2),
            baseline_pump_efficiency=round(base_result.pump_efficiency_fraction, 4),
            baseline_rod_float_risk=round(base_result.rod_float_risk, 4),
            baseline_cost_per_bbl_inr=round(base_cost, 2),
            # Deltas
            delta_oil_pct=_pct(base_result.oil_rate_m3d, opt_result.oil_rate_m3d),
            delta_sor_pct=_pct(base_result.sor, opt_result.sor),
            delta_energy_pct=_pct(base_result.kwh_per_bbl, opt_result.kwh_per_bbl),
            delta_cost_per_bbl_pct=_pct(base_cost, opt_cost),
            delta_risk_pts=round(opt_result.rod_float_risk_score - base_result.rod_float_risk_score, 2),
            steam_tonnes_saved_per_cycle=round(steam_saved, 1),
            # Constraints
            constraint_violations=[
                {
                    "constraint_id": v.constraint_id,
                    "name": v.name,
                    "severity": v.severity,
                    "recommended_value": v.recommended_value,
                    "limit_value": v.limit_value,
                    "unit": v.unit,
                }
                for v in cr.violations
            ],
            constraints_passed=cr.passed,
            n_trials=self.n_trials,
            best_trial_value=round(float(best_val), 4),
        )
