"""
simulator/reservoir/ipr.py
Inflow Performance Relationship: Vogel (1968) + viscosity-coupled PI.

References:
  [1] Vogel, J.V. (1968) "Inflow Performance Relationships for Solution-Gas
      Drive Wells," JPT, 83-92, SPE-1476-PA.
  [2] Ahmed, T. (2010) Reservoir Engineering Handbook, 4th ed.,
      Gulf Professional Publishing, Ch. 8.
  [3] Standing, M.B. (1970) "Inflow Performance Relationships for Damaged Wells
      in Solution-Gas Drive Reservoirs," JPT, 1399-1400, SPE-3209-PA.

Vogel IPR [1]:
  q_o / q_max = 1 - 0.2·(Pwf/Pr) - 0.8·(Pwf/Pr)²
  q_max = PI · Pr / 1.8

Viscosity coupling [2][3]:
  PI(T) = PI_ref · (μ_ref / μ(T))
  This means as the reservoir cools after steam injection, viscosity rises,
  PI falls, and oil rate drops — physically correct behavior.
"""

import numpy as np
from ..config import (
    PI_REFERENCE_M3_DAY_KPA,
    VOGEL_C1,
    VOGEL_C2,
    FLOWING_BOTTOMHOLE_PRESSURE_KPA,
    VISCOSITY_REFERENCE_CP,
)


def productivity_index(
    viscosity_cp: float,
    pi_ref: float = PI_REFERENCE_M3_DAY_KPA,
    mu_ref_cp: float = VISCOSITY_REFERENCE_CP,
) -> float:
    """
    Viscosity-coupled productivity index [m³/(day·kPa)].

    PI(T) = PI_ref · (μ_ref / μ(T))                              [2][3]

    As reservoir cools → viscosity rises → PI falls → production declines.
    This is the primary mechanism linking CSS thermal state to production rate.

    Parameters
    ----------
    viscosity_cp : float   Current oil viscosity [cP]
    pi_ref       : float   Reference PI at reference viscosity [m³/(day·kPa)]
    mu_ref_cp    : float   Reference viscosity [cP]

    Returns
    -------
    float   PI [m³/(day·kPa)], always > 0
    """
    if viscosity_cp <= 0:
        viscosity_cp = 0.1
    return float(pi_ref * mu_ref_cp / viscosity_cp)


def vogel_qmax(
    pi: float,
    reservoir_pressure_kpa: float,
) -> float:
    """
    Maximum deliverability rate (AOF) from Vogel IPR [1].
    q_max = PI · Pr / 1.8   [m³/day]
    """
    return float(pi * reservoir_pressure_kpa / 1.8)


def vogel_oil_rate(
    reservoir_pressure_kpa: float,
    pwf_kpa: float,
    viscosity_cp: float,
    pi_ref: float = PI_REFERENCE_M3_DAY_KPA,
    mu_ref_cp: float = VISCOSITY_REFERENCE_CP,
) -> float:
    """
    Oil production rate [m³/day] from Vogel IPR with viscosity-coupled PI.

    Vogel IPR [1]:
      q_o = q_max · [1 - C1·(Pwf/Pr) - C2·(Pwf/Pr)²]
      C1 = 0.2,  C2 = 0.8

    Parameters
    ----------
    reservoir_pressure_kpa : float   Average reservoir pressure [kPa]
    pwf_kpa                : float   Flowing bottomhole pressure [kPa]
    viscosity_cp           : float   Current oil viscosity [cP]
    pi_ref, mu_ref_cp      : float   PI calibration

    Returns
    -------
    float   Oil rate [m³/day], ≥ 0
    """
    if reservoir_pressure_kpa <= 0:
        return 0.0
    pwf_kpa = np.clip(pwf_kpa, 0.0, reservoir_pressure_kpa)

    pi = productivity_index(viscosity_cp, pi_ref, mu_ref_cp)
    q_max = vogel_qmax(pi, reservoir_pressure_kpa)
    ratio = pwf_kpa / reservoir_pressure_kpa
    q_o = q_max * (1.0 - VOGEL_C1 * ratio - VOGEL_C2 * ratio**2)
    return float(max(q_o, 0.0))


def water_oil_ratio(
    t_production_days: float,
    peak_temp_c: float,
    initial_temp_c: float,
    base_wor: float = 0.5,
    wor_slope: float = 0.15,
) -> float:
    """
    Water-oil ratio as a function of production time and thermal state.
    As the well cools and production continues, WOR rises [2][3].

    WOR(t) = base_wor + wor_slope · t_production_days · (T_initial / T_peak)

    Parameters
    ----------
    t_production_days : float   Days into the production phase
    peak_temp_c       : float   Peak reservoir temperature [°C]
    initial_temp_c    : float   Initial reservoir temperature [°C]
    base_wor          : float   WOR at production start
    wor_slope         : float   WOR rise rate [per day]

    Returns
    -------
    float   WOR [m³ water / m³ oil], ≥ base_wor
    """
    if peak_temp_c <= initial_temp_c:
        thermal_factor = 1.0
    else:
        thermal_factor = initial_temp_c / peak_temp_c  # lower T peak → higher WOR

    wor = base_wor + wor_slope * t_production_days * thermal_factor
    return float(max(wor, base_wor))


def water_cut_from_wor(wor: float) -> float:
    """
    Water cut fraction from water-oil ratio.
    fw = WOR / (1 + WOR)
    """
    return float(wor / (1.0 + wor))


def reservoir_pressure_decline(
    initial_pressure_kpa: float,
    t_production_days: float,
    decline_rate_per_day: float = 0.002,
) -> float:
    """
    Simple exponential reservoir pressure decline during production phase.
    Pr(t) = Pr_0 · exp(−λ · t)

    A CSS steam injection cycle re-pressurizes the reservoir — this is handled
    by resetting pressure each injection cycle in WellSystem.

    Source: [2] Ahmed (2010) Ch. 4 — exponential decline.
    """
    Pr = initial_pressure_kpa * np.exp(-decline_rate_per_day * max(t_production_days, 0.0))
    return float(max(Pr, initial_pressure_kpa * 0.3))   # floor at 30% of initial
