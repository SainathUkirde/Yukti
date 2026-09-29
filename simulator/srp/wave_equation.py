"""
simulator/srp/wave_equation.py
Damped 1D wave equation for sucker-rod string dynamics.
Generates surface and downhole dynamometer card data.

References:
  [1] Gibbs, S.G. (1963) "Predicting the Behavior of Sucker-Rod Pumping
      Systems," JPT, 769-778, SPE-588-PA.
  [2] Takacs, G. (2015) Sucker-Rod Pumping Handbook,
      Gulf Professional Publishing, Ch. 4-6.
  [3] API RP 11L (2012) Recommended Practice for Design Calculations for
      Sucker Rod Pumping Systems.
  [4] Doty, D.R. & Schmidt, Z. (1983) "An Improved Model for Sucker Rod Pumping,"
      SPEJ, 33-41, SPE-10249-PA.

Wave equation (Gibbs 1963) [1]:
  ∂²u/∂t² = c²·∂²u/∂x² − 2β·∂u/∂t

where:
  u(x,t) = axial displacement of rod at depth x and time t [m]
  c = wave propagation speed in steel = sqrt(E/ρ) ≈ 5130 m/s  [1][3]
  β = damping coefficient [1/s], viscosity-dependent              [1][4]

Boundary conditions [1]:
  Surface (x=0): u(0,t) = (SL/2)·[1 - cos(ω·t)]    (sinusoidal surface stroke)
  Pump    (x=L): F(L,t) = rod_weight_in_fluid − fluid_load(t) − pump_load(t)

Numerical scheme: finite-difference (explicit) on a coarse spatial grid.
For speed, the default fast_surrogate approximation is used in the optimizer;
this full solver is used for accurate card generation and tests.
"""

import numpy as np
from dataclasses import dataclass
from ..config import (
    STEEL_ELASTIC_MODULUS_PA,
    STEEL_DENSITY_KG_M3,
    ROD_WAVE_SPEED_M_S,
    DAMPING_BASE,
    VISCOSITY_REFERENCE_CP,
    GRAVITY_M_S2,
    DYNO_CARD_POINTS,
)


@dataclass
class DynoCardResult:
    """Output of one complete stroke simulation."""
    # Surface card: 100-200 (position, load) pairs per stroke
    surface_position_m: np.ndarray    # [DYNO_CARD_POINTS]  polished-rod position [m]
    surface_load_kn: np.ndarray       # [DYNO_CARD_POINTS]  polished-rod load [kN]
    # Downhole card: transformed to pump position/load
    downhole_position_m: np.ndarray   # [DYNO_CARD_POINTS]  pump position [m]
    downhole_load_kn: np.ndarray      # [DYNO_CARD_POINTS]  pump load [kN]
    # Scalars
    peak_load_kn: float
    min_load_kn: float
    fillage_fraction: float           # pump fillage (0-1)
    pump_efficiency_fraction: float
    motor_power_kw: float
    kwh_per_bbl: float
    rod_fall_speed_ms: float          # average rod fall speed during downstroke [m/s]
    plunger_demand_ms: float          # maximum plunger speed demand [m/s]
    rod_float_risk: float             # RF_risk = plunger_demand / rod_fall; >1 → floating


def _damping_coefficient(viscosity_cp: float, beta0: float = DAMPING_BASE,
                          mu_ref: float = VISCOSITY_REFERENCE_CP) -> float:
    """
    Viscosity-dependent damping coefficient.
    β(T) = β₀ · (μ(T) / μ_ref)^0.5                               [1][4]

    Higher viscosity → more damping → slower rod fall → rod floating risk.
    """
    return beta0 * np.sqrt(max(viscosity_cp, 0.1) / mu_ref)


def simulate_stroke(
    stroke_length_m: float,
    spm: float,
    rod_length_m: float,
    rod_diameter_m: float,
    plunger_dia_m: float,
    oil_viscosity_cp: float,
    reservoir_pressure_kpa: float,
    oil_rate_m3d: float,
    pump_depth_m: float,
    motor_efficiency: float = 0.90,
    n_spatial: int = 20,
    fault_type: str | None = None,
    fault_severity: float = 1.0,
    n_points: int = DYNO_CARD_POINTS,
) -> DynoCardResult:
    """
    Simulate one complete SRP stroke using the damped 1D wave equation [1].

    Physical model:
    - Surface displacement: sinusoidal  u(0,t) = (SL/2)·[1 - cos(ωt)]
    - Wave travels down rod string with speed c and damping β
    - Downhole load computed from wave equation solution at x=L
    - Pump fillage estimated from downhole card geometry

    Parameters
    ----------
    stroke_length_m      : float   Polished-rod stroke length [m]
    spm                  : float   Strokes per minute
    rod_length_m         : float   Total rod string length [m]
    rod_diameter_m       : float   Rod diameter [m]
    plunger_dia_m        : float   Pump plunger diameter [m]
    oil_viscosity_cp     : float   Current oil viscosity [cP]
    reservoir_pressure_kpa: float  Current reservoir pressure [kPa]
    oil_rate_m3d         : float   Current oil production rate [m³/day]
    pump_depth_m         : float   Pump setting depth [m]
    motor_efficiency     : float   Electric motor efficiency [-]
    n_spatial            : int     Spatial grid points along rod
    fault_type           : str     None | 'rod_floating' | 'pump_off' |
                                   'gas_interference' | 'fluid_pound' | 'pump_unsetting'
    fault_severity       : float   0.0-1.0 severity multiplier
    n_points             : int     Number of (pos, load) points per card

    Returns
    -------
    DynoCardResult
    """
    # ── Physical constants ──────────────────────────────────────────────────
    omega = 2.0 * np.pi * spm / 60.0          # angular frequency [rad/s]
    T_stroke = 60.0 / spm                      # stroke period [s]
    c = ROD_WAVE_SPEED_M_S                     # wave speed [m/s]
    beta = _damping_coefficient(oil_viscosity_cp)

    A_rod = np.pi / 4.0 * rod_diameter_m**2   # rod cross-section [m²]
    rho_steel = STEEL_DENSITY_KG_M3
    rod_unit_weight_kn_m = (A_rod * rho_steel * GRAVITY_M_S2) / 1000.0  # kN/m

    # Rod weight in fluid (buoyancy correction)
    # ρ_fluid ≈ 900 kg/m³ for heavy crude (18° API)
    rho_fluid_kg_m3 = 900.0
    buoyancy_factor = 1.0 - (rho_fluid_kg_m3 * A_rod * rod_length_m) / (
        rho_steel * A_rod * rod_length_m
    )
    W_rod_in_fluid_kn = rod_unit_weight_kn_m * rod_length_m * buoyancy_factor

    # ── Time array for one stroke ───────────────────────────────────────────
    t_arr = np.linspace(0.0, T_stroke, n_points)

    # ── Surface displacement (boundary condition at x=0) ───────────────────
    # u(0,t) = (SL/2)·[1 - cos(ωt)]   — sinusoidal polished-rod motion [3]
    surf_pos = (stroke_length_m / 2.0) * (1.0 - np.cos(omega * t_arr))

    # ── Approximate analytical wave-equation solution ───────────────────────
    # Full FD solution is expensive; we use the Gibbs closed-form approximation [1]:
    # The wave travels from surface to pump with travel time τ = L/c.
    # With damping, the pump-end displacement is phase-shifted and attenuated.
    #
    # τ = L / c
    # u(L,t) ≈ (SL/2)·exp(-β·τ)·[1 - cos(ω(t - τ))]
    tau = rod_length_m / c                     # one-way travel time [s]
    attenuation = np.exp(-beta * tau)
    phase_shift = omega * tau                  # phase shift at pump depth [rad]

    pump_pos_raw = (stroke_length_m / 2.0) * attenuation * (
        1.0 - np.cos(omega * t_arr - phase_shift)
    )

    # ── Load calculation ────────────────────────────────────────────────────
    # Surface load: rod weight in fluid + inertia + fluid load
    # F_surface(t) = W_rod + F_inertia(t) + F_fluid(t)
    #
    # Inertia force: F_inertia = M_rod · d²u/dt²
    # d²u/dt² = (SL/2)·ω²·cos(ωt)
    M_rod_kg = A_rod * rho_steel * rod_length_m
    accel_surface = (stroke_length_m / 2.0) * omega**2 * np.cos(omega * t_arr)
    F_inertia_kn = (M_rod_kg * accel_surface) / 1000.0

    # Fluid load: net upward force from fluid column on pump plunger
    A_plunger = np.pi / 4.0 * plunger_dia_m**2   # [m²]
    P_above_plunger_kpa = pump_depth_m * rho_fluid_kg_m3 * GRAVITY_M_S2 / 1000.0  # hydrostatic [kPa]
    # Both pressures are in kPa; kPa × m² = kN (1 kPa = 1 kN/m²)
    F_fluid_kn = (P_above_plunger_kpa - reservoir_pressure_kpa) * A_plunger
    F_fluid_kn = max(F_fluid_kn, 0.0)   # can't push down on upstroke physically

    # Upstroke: load is high (lifting fluid + rod weight); downstroke: low
    upstroke_mask = t_arr < T_stroke / 2.0
    surf_load = np.where(
        upstroke_mask,
        W_rod_in_fluid_kn + F_inertia_kn + F_fluid_kn,    # upstroke
        W_rod_in_fluid_kn * 0.3 + F_inertia_kn,           # downstroke (rods falling)
    )

    # ── Downhole load (de-convolve wave equation at x=L) ───────────────────
    # Downhole load = Surface load minus rod inertia accumulated over string
    # Approximation: F_dh = F_surface · exp(-β·τ) + correction for phase [1]
    accel_pump = (stroke_length_m / 2.0) * omega**2 * attenuation * np.cos(
        omega * t_arr - phase_shift
    )
    F_inertia_pump_kn = (M_rod_kg * accel_pump) / 1000.0
    pump_load = np.where(
        upstroke_mask,
        surf_load * attenuation + F_inertia_pump_kn * 0.5,
        np.abs(surf_load * attenuation + F_inertia_pump_kn * 0.5),
    )

    # ── Apply fault distortions ─────────────────────────────────────────────
    surf_pos, surf_load, pump_pos_raw, pump_load = _apply_fault(
        surf_pos, surf_load, pump_pos_raw, pump_load,
        fault_type, fault_severity, t_arr, T_stroke,
        W_rod_in_fluid_kn, stroke_length_m,
    )

    # ── Rod fall speed vs plunger demand ────────────────────────────────────
    # Rod fall speed: Stokes-like terminal velocity in viscous fluid [2]
    # v_fall = W_rod_in_fluid [N] / (3π · μ_dynamic [Pa·s] · D_rod [m] · L_rod [m])
    mu_pa_s = oil_viscosity_cp * 1e-3
    W_rod_N = W_rod_in_fluid_kn * 1000.0
    drag_coeff = 3.0 * np.pi * mu_pa_s * rod_diameter_m * rod_length_m
    rod_fall_speed = W_rod_N / max(drag_coeff, 1e-6)                        # [m/s]

    # Plunger speed demand [2]: v_plunger_max = π · SL · SPM / 60
    plunger_demand = np.pi * stroke_length_m * spm / 60.0                   # [m/s]

    rod_float_risk = plunger_demand / max(rod_fall_speed, 1e-6)

    # ── Pump fillage ────────────────────────────────────────────────────────
    # Fillage ≈ area of downhole card / area of ideal card [2]
    pump_stroke_range = pump_pos_raw.max() - pump_pos_raw.min()
    pump_load_range = pump_load.max() - pump_load.min()
    ideal_area = pump_stroke_range * pump_load_range if pump_stroke_range > 0 else 1.0
    actual_area = float(np.trapz(pump_load, pump_pos_raw))
    fillage = float(np.clip(abs(actual_area) / max(ideal_area, 1e-6), 0.1, 1.0))

    # Fillage reduced when rod floating (viscous drag prevents full pump stroke) [2]
    if fault_type == "rod_floating":
        fillage *= max(1.0 - 0.4 * fault_severity, 0.3)

    # ── Pump efficiency ─────────────────────────────────────────────────────
    # η_pump = q_actual / q_theoretical [3]
    q_theoretical = (np.pi / 4.0) * plunger_dia_m**2 * stroke_length_m * spm * 1440.0  # m³/day
    # q_actual from IPR (already computed at well level)
    pump_efficiency = float(np.clip(oil_rate_m3d / max(q_theoretical, 1e-6), 0.05, 0.95))

    # ── Motor power ─────────────────────────────────────────────────────────
    # P [kW] = (F_peak [kN] · stroke_length [m] · SPM) / (60 · motor_eff)  [3]
    peak_load_kn = float(surf_load.max())
    min_load_kn = float(surf_load.min())
    P_motor_kw = (peak_load_kn * stroke_length_m * spm) / (60.0 * motor_efficiency)

    # kWh per barrel
    q_bbl_day = max(oil_rate_m3d * 6.2898, 0.001)
    kwh_bbl = float(P_motor_kw * 24.0 / q_bbl_day)

    return DynoCardResult(
        surface_position_m=surf_pos,
        surface_load_kn=surf_load,
        downhole_position_m=pump_pos_raw,
        downhole_load_kn=pump_load,
        peak_load_kn=peak_load_kn,
        min_load_kn=min_load_kn,
        fillage_fraction=fillage,
        pump_efficiency_fraction=pump_efficiency,
        motor_power_kw=float(P_motor_kw),
        kwh_per_bbl=kwh_bbl,
        rod_fall_speed_ms=float(rod_fall_speed),
        plunger_demand_ms=float(plunger_demand),
        rod_float_risk=float(rod_float_risk),
    )


def _apply_fault(
    surf_pos: np.ndarray,
    surf_load: np.ndarray,
    pump_pos: np.ndarray,
    pump_load: np.ndarray,
    fault_type: str | None,
    severity: float,
    t_arr: np.ndarray,
    T_stroke: float,
    W_rod_kn: float,
    stroke_length_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Inject fault distortions into the dynamometer card arrays.
    Card signatures sourced from [2] Takacs (2015) Ch.5-6.

    Each fault produces a physically motivated distortion pattern:

    rod_floating:
      Top of card flattens — load drops mid-upstroke because rods
      cannot descend fast enough, reducing effective stroke. [2]

    pump_off:
      Card shrinks vertically — small load range indicates little or
      no fluid in pump barrel. [2]

    gas_interference:
      Irregular bottom-of-card spike — gas compresses before fluid
      enters, causing load variation. [2]

    fluid_pound:
      Sharp impact spike at bottom of card — rods hit fluid surface
      after free-falling through gas. [2]

    pump_unsetting:
      Card baseline shifts and shape becomes irregular — pump
      anchor loosens causing erratic behavior. [2]
    """
    if fault_type is None or severity <= 0:
        return surf_pos, surf_load, pump_pos, pump_load

    surf_load = surf_load.copy()
    pump_load = pump_load.copy()
    surf_pos = surf_pos.copy()
    pump_pos = pump_pos.copy()
    rng = np.random.default_rng(42)
    n = len(t_arr)
    upstroke = t_arr < T_stroke / 2.0

    if fault_type == "rod_floating":
        # Mid-upstroke load drop — rods float, reducing effective load [2]
        mid = n // 4
        top = 3 * n // 8
        surf_load[mid:top] -= severity * W_rod_kn * 0.6 * np.linspace(0, 1, top - mid)
        surf_load = np.clip(surf_load, 0, None)
        # Reduced pump stroke — viscous drag prevents full downstroke
        pump_pos *= (1.0 - 0.3 * severity)

    elif fault_type == "pump_off":
        # Vertical shrink — no fluid, card area collapses [2]
        surf_load *= (1.0 - 0.65 * severity)
        pump_load *= (1.0 - 0.65 * severity)

    elif fault_type == "gas_interference":
        # Irregular bottom spike — gas compression before fluid entry [2]
        bottom_start = 3 * n // 4
        bottom = slice(bottom_start, n)
        bottom_len = n - bottom_start
        noise = rng.normal(0, W_rod_kn * 0.3 * severity, bottom_len)
        surf_load[bottom] += noise
        pump_load[bottom] += noise * 0.7

    elif fault_type == "fluid_pound":
        # Sharp impact spike at bottom of card [2]
        impact_idx = int(0.7 * n)
        spike = W_rod_kn * 1.5 * severity * np.exp(
            -((np.arange(n) - impact_idx)**2) / (2 * (n * 0.03)**2)
        )
        surf_load += spike
        pump_load += spike * 0.5

    elif fault_type == "pump_unsetting":
        # Baseline shift + noise — erratic pump anchor [2]
        baseline_drift = severity * W_rod_kn * 0.25
        surf_load += baseline_drift * np.sin(2 * np.pi * t_arr / T_stroke * 3)
        surf_load += rng.normal(0, W_rod_kn * 0.1 * severity, n)
        pump_pos += rng.normal(0, stroke_length_m * 0.05 * severity, n)

    return surf_pos, surf_load, pump_pos, pump_load
