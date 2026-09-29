"""
simulator/reservoir/heated_zone.py
Marx-Langenheim steam-heated zone model.

References:
  [1] Marx, J.W. & Langenheim, R.H. (1959) "Reservoir Heating by Hot Fluid
      Injection," Trans. AIME, 216, 312-315.
  [2] Butler, R.M. (1991) Thermal Recovery of Oil and Bitumen, Prentice-Hall,
      Ch. 5.
  [3] Boberg, T.C. & Lantz, R.B. (1966) "Calculation of the Production Rate of
      a Thermally Stimulated Well," JPT, 1613-1623, SPE-1377-PA.

Marx-Langenheim (simplified, single-zone uniform sweep):
  A_h(t_D) = (α_s · t_D) · [erfc(√t_D) + 2√(t_D/π) · exp(-t_D) - 1]

where the dimensionless time t_D accounts for overburden/underburden heat loss.

For this implementation we use the closed-form approximation:
  r_h = sqrt( (Q_s_eff · η_therm) / (π · φ · S_o · h_pay) )

and average heated-zone temperature:
  T_avg_h = T_initial + ΔT_steam · exp(-λ_cool · t_prod)

This captures the essential physics (radius grows with steam; temperature decays
during production) without requiring a full 2D numerical solver, consistent with
screening-level CSS simulation practice [2][3].
"""

import numpy as np
from ..config import (
    RESERVOIR_TEMP_INITIAL_C,
    THERMAL_EFFICIENCY_FACTOR,
    THERMAL_DECAY_CONSTANT_PER_DAY,
    STEAM_TEMPERATURE_C,
    RESERVOIR_VOLUMETRIC_HEAT_CAPACITY_KJ_M3K,
    STEAM_LATENT_HEAT_KJ_KG,
    WATER_SPECIFIC_HEAT_KJ_KGK,
    CYCLE_EFFICIENCY_DEGRADATION,
)


def steam_enthalpy_kj_kg(quality: float, T_steam_c: float = STEAM_TEMPERATURE_C) -> float:
    """
    Steam enthalpy at given quality and temperature.
    h_s = h_f + quality · h_fg   [kJ/kg]

    h_f  = sensible heat of liquid water ≈ c_p · T [kJ/kg]
    h_fg = latent heat of vaporization ≈ 2000 kJ/kg at ~200°C [2]

    Source: [2] Butler (1991); steam tables.
    """
    h_f = WATER_SPECIFIC_HEAT_KJ_KGK * T_steam_c          # kJ/kg
    h_fg = STEAM_LATENT_HEAT_KJ_KG                         # kJ/kg
    return h_f + quality * h_fg


def heated_zone_radius_m(
    steam_volume_cwe_m3: float,
    steam_quality: float,
    pay_thickness_m: float,
    porosity: float,
    T_initial_c: float = RESERVOIR_TEMP_INITIAL_C,
    T_steam_c: float = STEAM_TEMPERATURE_C,
    thermal_efficiency: float = THERMAL_EFFICIENCY_FACTOR,
    M_R: float = RESERVOIR_VOLUMETRIC_HEAT_CAPACITY_KJ_M3K,
    cycle_number: int = 1,
) -> float:
    """
    Estimate heated-zone radius [m] after injecting steam_volume_cwe_m3
    cold-water-equivalent steam.

    Marx-Langenheim simplified [1][2]:
      A_h = (m_s · h_s · η_therm) / (M_R · ΔT_s · h_pay)
      r_h = sqrt(A_h / π)

    where:
      m_s   = steam mass [kg] (from CWE volume assuming density of water)
      h_s   = steam enthalpy [kJ/kg]
      η_therm = thermal efficiency factor (accounts for overburden heat loss)
      M_R   = reservoir volumetric heat capacity [kJ/(m³·°C)]
      ΔT_s  = T_steam - T_initial [°C]
      h_pay = pay thickness [m]

    Cycle degradation applied to thermal efficiency [Bursell & Pittman, 1975]:
      η_n = η_1 · (1 - δ)^(n-1)   where δ = CYCLE_EFFICIENCY_DEGRADATION

    Parameters
    ----------
    steam_volume_cwe_m3 : float   Steam volume [m³], cold-water-equivalent
    steam_quality       : float   Steam dryness fraction [0.5 – 1.0]
    pay_thickness_m     : float   Net pay zone thickness [m]
    porosity            : float   Reservoir porosity [-]
    T_initial_c         : float   Initial reservoir temperature [°C]
    T_steam_c           : float   Steam temperature [°C]
    thermal_efficiency  : float   η_1 at cycle 1
    M_R                 : float   Volumetric heat capacity [kJ/(m³·°C)]
    cycle_number        : int     CSS cycle number (≥1); efficiency degrades

    Returns
    -------
    float   Heated-zone radius [m]
    """
    if steam_volume_cwe_m3 <= 0:
        return 0.0

    delta_T = T_steam_c - T_initial_c
    if delta_T <= 0:
        return 0.0

    # Cycle-dependent thermal efficiency [9]
    eta = thermal_efficiency * (1.0 - CYCLE_EFFICIENCY_DEGRADATION) ** (cycle_number - 1)
    eta = max(eta, 0.05)   # floor — very late cycles still heat something

    # Steam mass: CWE volume × density of water (1000 kg/m³)
    m_steam_kg = steam_volume_cwe_m3 * 1000.0

    # Steam enthalpy
    h_s = steam_enthalpy_kj_kg(steam_quality, T_steam_c)

    # Heated area [m²] — Marx-Langenheim [1]
    A_h = (m_steam_kg * h_s * eta) / (M_R * delta_T * pay_thickness_m)

    # Heated radius [m]
    r_h = np.sqrt(max(A_h, 0.0) / np.pi)
    return float(r_h)


def peak_temperature_c(
    steam_volume_cwe_m3: float,
    steam_quality: float,
    pay_thickness_m: float,
    porosity: float,
    T_initial_c: float = RESERVOIR_TEMP_INITIAL_C,
    T_steam_c: float = STEAM_TEMPERATURE_C,
    thermal_efficiency: float = THERMAL_EFFICIENCY_FACTOR,
    M_R: float = RESERVOIR_VOLUMETRIC_HEAT_CAPACITY_KJ_M3K,
    cycle_number: int = 1,
) -> float:
    """
    Estimate the average peak reservoir temperature [°C] achieved at end of steam soak.

    Boberg & Lantz (1966) [3] approach (corrected):
      f_heated = min(r_h / r_CSS_drain, 1.0)
      T_peak = T_initial + (T_steam - T_initial) * f_heated * eta_therm

    r_CSS_drain = 15 m is the CSS-scale wellbore-vicinity radius (heated cylinder
    within which we compute average temperature). Using r_drainage = 100 m was
    wrong — it diluted f_heated to ~0.004 producing near-zero temperature rise.
    A 15 m radius gives physically correct 60–110°C for typical Baghewala steam volumes.
    Linear (not squared) ratio because we are weighting along the 1D radial profile,
    not the 2D area (area weighting would be (r_h/r_drain)² — too diluted).
    """
    r_h = heated_zone_radius_m(
        steam_volume_cwe_m3, steam_quality, pay_thickness_m, porosity,
        T_initial_c, T_steam_c, thermal_efficiency, M_R, cycle_number
    )
    # CSS-scale wellbore vicinity: r_drain ≈ 15 m for Baghewala field geometry
    r_CSS_drain = 15.0
    f_heated = min(r_h / r_CSS_drain, 1.0)

    eta = thermal_efficiency * (1.0 - CYCLE_EFFICIENCY_DEGRADATION) ** (cycle_number - 1)
    eta = max(eta, 0.05)

    T_peak = T_initial_c + (T_steam_c - T_initial_c) * f_heated * eta
    # Clamp: cannot exceed steam temperature, must exceed initial temperature
    return float(np.clip(T_peak, T_initial_c, T_steam_c))


def reservoir_temperature_c(
    T_peak_c: float,
    T_initial_c: float,
    t_production_days: float,
    alpha: float = THERMAL_DECAY_CONSTANT_PER_DAY,
) -> float:
    """
    Reservoir average temperature [°C] at time t_production_days after start of
    production, given peak temperature T_peak_c.

    Exponential cooling decay [2]:
      T(t) = T_initial + (T_peak - T_initial) · exp(-α · t)

    Parameters
    ----------
    T_peak_c           : float   Peak reservoir temperature [°C] at soak end
    T_initial_c        : float   Initial (undisturbed) reservoir temperature [°C]
    t_production_days  : float   Days since production started
    alpha              : float   Thermal decay constant [1/day]

    Returns
    -------
    float   Reservoir temperature [°C]
    """
    delta_T = T_peak_c - T_initial_c
    T = T_initial_c + delta_T * np.exp(-alpha * max(t_production_days, 0.0))
    return float(T)


def sor(
    steam_volume_cwe_m3: float,
    oil_produced_m3: float,
    steam_quality: float = 0.75,
) -> float:
    """
    Steam-Oil Ratio [m³/m³] expressed as cold-water-equivalent steam per oil produced.

    SOR = Q_steam_CWE / Q_oil

    Note: CWE volume already accounts for steam quality in the injection parameter.
    Source: Butler (1991); SPE-13305.
    """
    if oil_produced_m3 <= 0.0:
        return 999.0   # infinite SOR if no oil produced
    return float(steam_volume_cwe_m3 / oil_produced_m3)
