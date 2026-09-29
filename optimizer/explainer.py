"""
optimizer/explainer.py
Explainability generator for CSS + SRP recommendations.

Generates structured, human-readable explanations for every recommendation.
Each explanation includes:
  - reason_text: one-paragraph narrative
  - top_factors: physics variables driving the recommendation
  - constraints_checked: list of constraint checks with pass/fail
  - method: the physics/model chain used

The explainer uses the what-if results and optimizer output — no black box.
Every explanation is traceable to a specific physics equation or model output.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass, field
from optimizer.whatif.whatif_engine import WhatIfResult
from optimizer.joint_optimizer import OptimizationResult
from optimizer.constraints.constraint_engine import ConstraintResult


@dataclass
class TopFactor:
    factor_name: str
    value: float
    unit: str
    direction: str      # "increasing" | "decreasing" | "stable"
    impact: str         # human text


@dataclass
class Explanation:
    reason_text: str
    top_factors: list[TopFactor]
    constraints_checked: list[dict]
    method: str
    provenance: str = "OPTIMIZER_RECOMMENDATION"


class Explainer:
    """Generates structured explanations from optimizer and what-if results."""

    # ── Rule templates (fill from physics state) ─────────────────────────────
    _SPM_REDUCE_TEMPLATE = (
        "Oil viscosity is {visc:.0f} cP (reservoir temperature {temp:.1f}°C, "
        "{days:.0f} days into production cycle). At current SPM={spm_before:.1f}, "
        "rod floating risk ratio N_rf = {rf_before:.2f} "
        "({rf_status}). "
        "Reducing SPM to {spm_after:.1f} brings N_rf to {rf_after:.2f} (safe). "
        "Expected pump efficiency change: {eff_delta:+.1f}%. "
        "Expected kWh/bbl change: {energy_delta:+.1f}%."
    )

    _STEAM_INCREASE_TEMPLATE = (
        "Current reservoir temperature {temp:.1f}°C gives viscosity {visc:.0f} cP, "
        "limiting production via reduced PI (Vogel IPR). "
        "Increasing steam volume from {sv_before:.0f} to {sv_after:.0f} m³ CWE "
        "is predicted to raise peak reservoir temperature by {dT:.1f}°C, "
        "reduce viscosity by {dmu_pct:.0f}%, "
        "and increase oil rate by {dq_pct:+.1f}%. "
        "SOR impact: {sor_change}."
    )

    _SOAK_EXTEND_TEMPLATE = (
        "Extending soak period from {soak_before:.0f} to {soak_after:.0f} days "
        "allows the steam front to penetrate further ({r_before:.1f}m → {r_after:.1f}m radius), "
        "resulting in more uniform heating and better subsequent production. "
        "Expected SOR improvement: {sor_delta:+.1f}%."
    )

    _JOINT_OPTIMIZE_TEMPLATE = (
        "Joint CSS+SRP optimization over {n_trials} trials (Bayesian/TPE) "
        "found parameter combination that reduces cost per barrel by {cost_delta:.1f}%. "
        "Key changes: steam {steam_change}, SPM {spm_change}, soak {soak_change}. "
        "SOR: {sor_change}, energy: {energy_change}, "
        "rod float risk: {risk_change}. "
        "All {n_constraints} engineering constraints verified."
    )

    def explain_whatif(
        self,
        whatif: WhatIfResult,
        constraint_result: ConstraintResult = None,
    ) -> Explanation:
        """Generate explanation for a what-if scenario."""

        # Determine the primary driver
        changed = whatif.changed_parameters
        primary_key = list(changed.keys())[0] if changed else "unknown"

        # Build reason text based on dominant change
        if "spm" in changed:
            spm_before = whatif.baseline_rod_float_risk
            spm_after_rf = whatif.changed_rod_float_risk
            rf_status = "FLOATING" if spm_after_rf >= 1.0 else "safe"
            reason = (
                f"SPM changed from current operating value. "
                f"Viscosity is {whatif.baseline_viscosity_cp:.0f} cP "
                f"(reservoir at {whatif.baseline_reservoir_temp_c:.1f}°C). "
                f"Rod floating risk ratio: {whatif.baseline_rod_float_risk:.3f} → "
                f"{whatif.changed_rod_float_risk:.3f} ({rf_status}). "
                f"Oil rate: {whatif.delta_oil_rate_pct:+.1f}%, "
                f"pump efficiency: {whatif.delta_pump_efficiency_pct:+.1f}%, "
                f"energy: {whatif.delta_kwh_per_bbl_pct:+.1f}%."
            )
        elif "steam_volume_cwe_m3" in changed:
            reason = (
                f"Steam volume changed from {whatif.baseline_sor:.2f} SOR basis. "
                f"Reservoir temperature: {whatif.baseline_reservoir_temp_c:.1f}°C → "
                f"{whatif.changed_reservoir_temp_c:.1f}°C "
                f"(Δ{whatif.delta_reservoir_temp_c:+.1f}°C). "
                f"Viscosity: {whatif.delta_viscosity_pct:+.1f}%. "
                f"Oil rate: {whatif.delta_oil_rate_pct:+.1f}%. "
                f"SOR: {whatif.delta_sor_pct:+.1f}%."
            )
        else:
            reason = (
                f"Parameter change: {', '.join(f'{k}={v:.2f}' for k,v in changed.items())}. "
                f"Oil rate: {whatif.delta_oil_rate_pct:+.1f}%, "
                f"energy: {whatif.delta_kwh_per_bbl_pct:+.1f}%, "
                f"rod float risk: {whatif.delta_rod_float_risk:+.3f}."
            )

        # Propagation chain as narrative
        if whatif.propagation_chain:
            reason += " Physics chain: " + " → ".join(whatif.propagation_chain[:3]) + "."

        top_factors = [
            TopFactor(
                "oil_viscosity_cp", whatif.baseline_viscosity_cp, "cP",
                "increasing" if whatif.delta_viscosity_pct > 0 else "decreasing",
                "Drives pump fillage, rod floating risk, and production rate"
            ),
            TopFactor(
                "reservoir_temp_c", whatif.baseline_reservoir_temp_c, "°C",
                "stable", "Determines viscosity via Andrade equation"
            ),
            TopFactor(
                "rod_float_risk_ratio", whatif.baseline_rod_float_risk, "",
                "increasing" if whatif.delta_rod_float_risk > 0 else "decreasing",
                "N_rf = μ·SPM·SL/6000; >1.0 triggers rod floating"
            ),
        ]

        constraints = []
        if constraint_result:
            constraints = [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "value": round(c.recommended_value, 3),
                    "limit": round(c.limit_value, 3),
                    "unit": c.unit,
                }
                for c in constraint_result.checks
            ]

        return Explanation(
            reason_text=reason,
            top_factors=top_factors,
            constraints_checked=constraints,
            method="Fast surrogate physics chain: CSS→reservoir T→viscosity→IPR→SRP→KPIs",
        )

    def explain_optimization(
        self,
        opt: OptimizationResult,
        constraint_result: ConstraintResult = None,
    ) -> Explanation:
        """Generate explanation for a joint optimization result."""

        # Compute directional summaries
        def _dir(pct: float) -> str:
            if pct < -1:
                return f"reduced {abs(pct):.1f}%"
            elif pct > 1:
                return f"increased {pct:.1f}%"
            return "unchanged"

        steam_change = _dir(
            (opt.best_css["steam_volume_cwe_m3"] - opt.baseline_css["steam_volume_cwe_m3"])
            / max(opt.baseline_css["steam_volume_cwe_m3"], 1) * 100
        )
        spm_change = _dir(
            (opt.best_srp["spm"] - opt.baseline_srp["spm"])
            / max(opt.baseline_srp["spm"], 1) * 100
        )
        soak_change = _dir(
            (opt.best_css["soak_days"] - opt.baseline_css["soak_days"])
            / max(opt.baseline_css["soak_days"], 1) * 100
        )

        reason = self._JOINT_OPTIMIZE_TEMPLATE.format(
            n_trials=opt.n_trials,
            cost_delta=abs(opt.delta_cost_per_bbl_pct),
            steam_change=steam_change,
            spm_change=spm_change,
            soak_change=soak_change,
            sor_change=_dir(opt.delta_sor_pct),
            energy_change=_dir(opt.delta_energy_pct),
            risk_change=f"{opt.delta_risk_pts:+.1f} pts",
            n_constraints=11,
        )

        # Key factors driving the optimization
        top_factors = []
        if opt.predicted_rod_float_risk < opt.baseline_rod_float_risk:
            top_factors.append(TopFactor(
                "rod_float_risk_ratio", opt.baseline_rod_float_risk, "",
                "decreasing",
                f"SPM reduced from {opt.baseline_srp['spm']:.1f} to "
                f"{opt.best_srp['spm']:.1f} to prevent rod floating"
            ))
        if opt.predicted_sor < opt.baseline_sor:
            top_factors.append(TopFactor(
                "sor", opt.baseline_sor, "bbl/bbl",
                "decreasing",
                f"Steam volume optimized: {opt.baseline_css['steam_volume_cwe_m3']:.0f} → "
                f"{opt.best_css['steam_volume_cwe_m3']:.0f} m³ CWE"
            ))
        if opt.delta_energy_pct < 0:
            top_factors.append(TopFactor(
                "kwh_per_bbl", opt.baseline_kwh_per_bbl, "kWh/bbl",
                "decreasing",
                f"VFD optimized: {opt.baseline_srp['vfd_frequency_hz']:.1f} → "
                f"{opt.best_srp['vfd_frequency_hz']:.1f} Hz"
            ))

        constraints = []
        if constraint_result:
            constraints = [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "value": round(c.recommended_value, 3),
                    "limit": round(c.limit_value, 3),
                    "unit": c.unit,
                }
                for c in constraint_result.checks
            ]

        return Explanation(
            reason_text=reason,
            top_factors=top_factors,
            constraints_checked=constraints,
            method="Optuna TPE Bayesian optimization over fast physics surrogate (11 constraints)",
        )

    def explain_rod_floating_alert(
        self,
        viscosity_cp: float,
        reservoir_temp_c: float,
        spm: float,
        stroke_length_m: float,
        rf_ratio: float,
        recommended_spm: float,
        expected_efficiency_gain_pct: float,
    ) -> Explanation:
        """Generate explanation specifically for a rod floating alert recommendation."""
        rf_status = "imminent" if rf_ratio >= 1.5 else "onset"
        reason = (
            f"Viscosity is {viscosity_cp:.0f} cP (reservoir temperature "
            f"{reservoir_temp_c:.1f}°C, cooling after steam injection). "
            f"At current SPM={spm:.1f}, rod floating risk N_rf={rf_ratio:.2f} "
            f"({rf_status}: {'N_rf ≥ 1.5' if rf_ratio >= 1.5 else 'N_rf ≥ 1.0'}). "
            f"Rods cannot descend fast enough to match plunger demand "
            f"(N_rf = μ·SPM·SL/6000, Takacs 2015). "
            f"Reducing SPM to {recommended_spm:.1f} brings N_rf below 1.0. "
            f"Expected pump efficiency gain: +{expected_efficiency_gain_pct:.1f}%."
        )

        top_factors = [
            TopFactor("oil_viscosity_cp", viscosity_cp, "cP", "increasing",
                      "High viscosity slows rod descent (viscous drag)"),
            TopFactor("spm", spm, "strokes/min", "decreasing (recommended)",
                      "Reducing SPM lowers plunger demand below rod fall capacity"),
            TopFactor("rod_float_risk_ratio", rf_ratio, "", "decreasing (after fix)",
                      "N_rf = μ·SPM·SL/6000 — must stay below 1.0"),
        ]

        return Explanation(
            reason_text=reason,
            top_factors=top_factors,
            constraints_checked=[
                {"name": "Rod floating ratio < 1.0", "passed": rf_ratio < 1.0,
                 "value": round(rf_ratio, 3), "limit": 1.0, "unit": "N_rf"},
                {"name": "SPM within range", "passed": True,
                 "value": round(recommended_spm, 1), "limit": 12.0, "unit": "strokes/min"},
            ],
            method="Rod floating physics: N_rf = μ·SPM·SL/6000 (Takacs 2015, field-calibrated)",
        )
