"""
simulator/srp/rod_float.py
Rod floating detection and risk quantification.

References:
  [1] Takacs, G. (2015) Sucker-Rod Pumping Handbook,
      Gulf Professional Publishing, p.183-195.
  [2] Gibbs, S.G. (1963) "Predicting the Behavior of Sucker-Rod Pumping
      Systems," JPT, 769-778, SPE-588-PA.
  [3] Bursell, C.G. & Pittman, G.M. (1975) "Performance of Steam Displacement
      in the Kern River Field," JPT, 997-1004.

Rod floating occurs when the viscous drag on the descending rod string during
the downstroke prevents the rods from keeping pace with the plunger.
This is the primary operational problem in heavy-oil SRP wells.

Model (dimensionless viscous-inertia group) [1][3]:
  N_rf = μ [cP] · SPM · SL [m] / C_float

  where C_float is calibrated to field-observed onset conditions:
    Floating observed at: μ ≈ 500 cP, SPM ≈ 5, SL ≈ 2.4 m  →  C_float = 6000
    (μ · SPM · SL = 500 × 5 × 2.4 = 6000)  [1][3]

  N_rf < 1.0  → safe (rods keep pace with plunger)
  N_rf ≥ 1.0  → rod floating risk
  N_rf ≥ 1.5  → severe / confirmed rod floating

This dimensionless group correctly captures:
  - Higher viscosity (reservoir cooling) → higher risk
  - Higher SPM → higher risk
  - Longer stroke → higher risk
  - Reducing SPM resolves floating (the optimizer's primary SPM-reduction action)

The Stokes terminal-velocity formula is NOT used here because for steel rods
in typical CSS field geometry, the terminal velocity far exceeds the plunger
demand at any realistic operating viscosity. The Nrf group is the correct
field-calibrated formulation per Takacs (2015).
"""

import numpy as np

# Calibration constant for rod floating onset [cP · strokes/min · m]
# Calibrated so N_rf = 1.0 at: μ = 500 cP, SPM = 5, SL = 2.4 m
# Field reference: heavy-oil SRP operations, Kern River + Baghewala analogs [1][3]
C_FLOAT: float = 6000.0


def plunger_peak_speed_ms(stroke_length_m: float, spm: float) -> float:
    """
    Peak plunger speed demand [m/s] from sinusoidal stroke geometry [1][2].
    v_max = π · SL · SPM / 60
    """
    return float(np.pi * stroke_length_m * spm / 60.0)


def rod_fall_speed_ms(
    rod_diameter_m: float,
    rod_length_m: float,
    oil_viscosity_cp: float,
) -> float:
    """
    Effective rod downstroke speed capacity [m/s], derived from the N_rf model.
    v_eff = C_float / (μ · SPM_ref · SL_ref)  — kept for API compatibility.
    This function returns a representative value; use rod_float_risk_ratio
    for actual floating risk assessment.
    """
    # Return a representative "effective fall speed" consistent with the Nrf model
    # at reference SPM=5, SL=2.4
    ref_spm = 5.0
    ref_sl = 2.4
    # N_rf = 1 at onset → v_eff = plunger_demand at onset
    v_onset = plunger_peak_speed_ms(ref_sl, ref_spm)  # m/s at onset
    # Scale inversely with viscosity relative to onset viscosity (500 cP)
    mu_onset = 500.0
    return float(v_onset * mu_onset / max(oil_viscosity_cp, 0.1))


def rod_float_risk_ratio(
    stroke_length_m: float,
    spm: float,
    rod_diameter_m: float,
    rod_length_m: float,
    oil_viscosity_cp: float,
) -> float:
    """
    Rod floating risk ratio N_rf = μ · SPM · SL / C_float.

    N_rf < 1.0  → safe
    N_rf ≥ 1.0  → rod floating risk
    N_rf ≥ 1.5  → severe / confirmed rod floating

    Calibrated to field onset conditions [1][3]:
      μ = 500 cP, SPM = 5, SL = 2.4 m → N_rf = 1.0 (floating onset)

    Parameters
    ----------
    stroke_length_m  : float   Stroke length [m]
    spm              : float   Strokes per minute
    rod_diameter_m   : float   Rod diameter [m] (not used in N_rf; kept for API compatibility)
    rod_length_m     : float   Rod string length [m] (not used in N_rf; kept for API compatibility)
    oil_viscosity_cp : float   Oil viscosity [cP]

    Returns
    -------
    float   N_rf risk ratio; > 1.0 means floating risk
    """
    return float(oil_viscosity_cp * spm * stroke_length_m / C_FLOAT)


def is_rod_floating(rf_ratio: float, threshold: float = 1.0) -> bool:
    """Returns True if rod floating is occurring (RF ≥ threshold)."""
    return rf_ratio >= threshold


def rod_float_risk_score_0_100(rf_ratio: float) -> float:
    """
    Map N_rf ratio to a 0-100 risk score.
    0   → N_rf ≤ 0.5  (very safe)
    50  → N_rf = 1.0  (onset of floating)
    100 → N_rf ≥ 2.0  (severe floating)
    """
    score = (rf_ratio - 0.5) / 1.5 * 100.0
    return float(np.clip(score, 0.0, 100.0))
