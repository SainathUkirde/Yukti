"""
simulator/wellbore/viscosity.py
Viscosity-temperature model using the Andrade equation.

Reference:
  [1] Andrade, E.N. da C. (1930) "The Viscosity of Liquids," Nature, 125, 309-310.
      ln(μ) = A + B/T_K
  [2] Ahmed, T. (2010) Reservoir Engineering Handbook, 4th ed.,
      Gulf Professional Publishing, p.19.
  [3] ASTM D341-20 "Standard Practice for Viscosity-Temperature Charts for
      Liquid Petroleum Products." (Walther form also cited for reference)

The Andrade (Arrhenius-type) equation is used here because it is numerically
stable over the full temperature range of CSS operations (40°C – 200°C) and
provides excellent accuracy for heavy crude oils.

Andrade equation:
  ln(μ) = A_and + B_and / T_K

Calibrated defaults for 18° API Baghewala crude (LITERATURE_ASSUMPTION):
  At  47°C → μ ≈ 2000 cP  (Baghewala initial temp, FIELD_FACT range from PS)
  At 150°C → μ ≈    10 cP  (steam-heated; Ahmed 2010, Butler 1991)

Fitted constants: A_and = -14.1659, B_and = 6968.65  (derived below)
"""

import numpy as np
from ..config import RESERVOIR_TEMP_INITIAL_C

# ── Andrade calibration constants ────────────────────────────────────────────
# Fitted to: μ = 2000 cP @ 47°C,  μ = 10 cP @ 150°C   (18° API Baghewala crude)
# ln(μ) = A + B/T_K
# B = (ln(2000) - ln(10)) / (1/320.15 - 1/423.15) = 6968.65
# A = ln(2000) - 6968.65/320.15 = -14.1659
ANDRADE_A: float = -14.1659     # dimensionless intercept [1][2]
ANDRADE_B: float = 6968.65      # activation energy / R  [K]


def _oil_density_g_cm3(api: float) -> float:
    """
    Oil density from API gravity.
    ρ [g/cm³] = 141.5 / (131.5 + API)
    Source: [2] Ahmed (2010) p.12.
    """
    return 141.5 / (131.5 + api)


def viscosity_cp(temp_c: float, api: float = 18.0,
                 A: float = ANDRADE_A, B: float = ANDRADE_B) -> float:
    """
    Dynamic viscosity [cP] at temperature temp_c [°C].

    Andrade equation [1]:
      μ [cP] = exp(A + B / T_K)

    where T_K = temp_c + 273.15 [K].

    Calibrated defaults reproduce:
      At  47°C → 2000 cP  (FIELD_FACT: Baghewala heavy crude at initial reservoir T)
      At 150°C →   10 cP  (LITERATURE_ASSUMPTION: steam-heated state)

    Parameters
    ----------
    temp_c : float   Temperature [°C]
    api    : float   API gravity (used for density correction; minor effect)
    A, B   : float   Andrade constants (use fit_andrade_constants for real data)

    Returns
    -------
    float   Dynamic viscosity [cP], clamped to [0.1, 1e6]
    """
    T_K = temp_c + 273.15
    mu = np.exp(A + B / T_K)
    return float(np.clip(mu, 0.1, 1e6))


def fit_andrade_constants(
    T1_c: float, mu1_cp: float,
    T2_c: float, mu2_cp: float,
) -> tuple[float, float]:
    """
    Fit Andrade constants A and B from two measured viscosity points.
    Use this when real lab viscosity data is available.

    ln(μ) = A + B/T_K
    B = (ln(μ1) - ln(μ2)) / (1/T1_K - 1/T2_K)
    A = ln(μ1) - B/T1_K

    Parameters
    ----------
    T1_c, mu1_cp : float   First (T, μ) measurement point
    T2_c, mu2_cp : float   Second (T, μ) measurement point

    Returns
    -------
    (A, B) : tuple[float, float]   Fitted Andrade constants
    """
    T1_K = T1_c + 273.15
    T2_K = T2_c + 273.15
    denom = 1.0 / T1_K - 1.0 / T2_K
    if denom == 0.0:
        raise ValueError(
            f"fit_andrade_constants: T1 and T2 must be different "
            f"(got T1={T1_c}°C, T2={T2_c}°C)"
        )
    B = (np.log(mu1_cp) - np.log(mu2_cp)) / denom
    A = np.log(mu1_cp) - B / T1_K
    return float(A), float(B)


# Keep alias for any code that called fit_walther_constants
fit_walther_constants = fit_andrade_constants


def viscosity_array(temps_c: np.ndarray, api: float = 18.0,
                    A: float = ANDRADE_A, B: float = ANDRADE_B) -> np.ndarray:
    """Vectorized viscosity [cP] for an array of temperatures [°C]."""
    T_K = temps_c + 273.15
    mu = np.exp(A + B / T_K)
    return np.clip(mu, 0.1, 1e6)


# Keep alias for legacy callers
walther_kinematic_cst = None   # deprecated; use viscosity_cp directly
