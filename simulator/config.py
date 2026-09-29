"""
simulator/config.py
Global physics constants and default well parameters for YUKTI.

Every parameter is tagged with its provenance category and source citation.
FIELD_FACT           — from the problem statement (real Baghewala field facts)
LITERATURE_ASSUMPTION— from published petroleum engineering literature

Sources used throughout:
  [1] Ahmed, T. (2010) Reservoir Engineering Handbook, 4th ed., Gulf Professional Publishing.
  [2] Butler, R.M. (1991) Thermal Recovery of Oil and Bitumen, Prentice-Hall.
  [3] Takacs, G. (2015) Sucker-Rod Pumping Handbook, Gulf Professional Publishing.
  [4] Gibbs, S.G. (1963) "Predicting the Behavior of Sucker-Rod Pumping Systems," JPT, 769-778.
  [5] API RP 11L (2012) Recommended Practice for Design Calculations for Sucker Rod Pumping Systems.
  [6] API Spec 11B (2013) Sucker Rods.
  [7] Vogel, J.V. (1968) "Inflow Performance Relationships for Solution-Gas Drive Wells," JPT, 83-92.
  [8] Marx, J.W. & Langenheim, R.H. (1959) "Reservoir Heating by Hot Fluid Injection," Trans. AIME, 216.
  [9] Bursell, C.G. & Pittman, G.M. (1975) "Performance of Steam Displacement in the Kern River Field," JPT.
  [10] ASTM D341-20 "Standard Practice for Viscosity-Temperature Charts for Liquid Petroleum Products."
  [11] Shigley, J.E. (2011) Mechanical Engineering Design, 9th ed., McGraw-Hill.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


# ---------------------------------------------------------------------------
# Physical constants (universal)
# ---------------------------------------------------------------------------

STEEL_ELASTIC_MODULUS_PA: float = 2.07e11     # Young's modulus of steel rod [Pa], [5][6]
STEEL_DENSITY_KG_M3: float = 7850.0           # Rod steel density [kg/m³], [5]
ROD_WAVE_SPEED_M_S: float = float(np.sqrt(STEEL_ELASTIC_MODULUS_PA / STEEL_DENSITY_KG_M3))
# ≈ 5130 m/s, consistent with Gibbs (1963) [4]

WATER_SPECIFIC_HEAT_KJ_KGK: float = 4.187     # [kJ/(kg·K)]
STEAM_LATENT_HEAT_KJ_KG: float = 2000.0       # Approx latent heat at typical injection pressure [kJ/kg], [2]
GRAVITY_M_S2: float = 9.81                     # [m/s²]
BARRELS_PER_M3: float = 6.2898                 # 1 m³ = 6.2898 bbl


# ---------------------------------------------------------------------------
# Baghewala Field Facts (FIELD_FACT from PS)
# ---------------------------------------------------------------------------

RESERVOIR_TEMP_INITIAL_C_MIN: float = 46.0    # °C, FIELD_FACT [PS]
RESERVOIR_TEMP_INITIAL_C_MAX: float = 48.0    # °C, FIELD_FACT [PS]
RESERVOIR_TEMP_INITIAL_C: float = 47.0        # Default mid-range, FIELD_FACT [PS]

API_GRAVITY_MIN: float = 17.0                 # FIELD_FACT [PS]
API_GRAVITY_MAX: float = 19.0                 # FIELD_FACT [PS]
API_GRAVITY_DEFAULT: float = 18.0             # FIELD_FACT [PS]


# ---------------------------------------------------------------------------
# Reservoir Parameters (LITERATURE_ASSUMPTION unless noted)
# ---------------------------------------------------------------------------

RESERVOIR_PRESSURE_KPA: float = 4500.0        # Initial reservoir pressure [kPa], [1][2]
RESERVOIR_DEPTH_M: float = 800.0              # Well depth [m], Jodhpur Sandstone typical, [2]
PAY_THICKNESS_M: float = 20.0                 # Net pay thickness [m], [2]
POROSITY_FRACTION: float = 0.22               # Jodhpur Sandstone porosity, [1]
PERMEABILITY_MD: float = 400.0                # Reservoir permeability [mD], heavy oil ss, [1]

RESERVOIR_VOLUMETRIC_HEAT_CAPACITY_KJ_M3K: float = 2100.0
# M_R [kJ/(m³·°C)], Marx-Langenheim default [8]

THERMAL_EFFICIENCY_FACTOR: float = 0.65
# Heat utilization efficiency (accounts for overburden/underburden losses) [2]

THERMAL_DECAY_CONSTANT_PER_DAY: float = 0.08
# α in T(t) = T_initial + ΔT · exp(−α · t), calibrated to typical CSS production curves [2][9]

CYCLE_EFFICIENCY_DEGRADATION: float = 0.08
# 8% thermal efficiency loss per successive CSS cycle [9]


# ---------------------------------------------------------------------------
# Viscosity Model — Andrade equation [Andrade 1930; Ahmed 2010]
# ln(μ) = ANDRADE_A + ANDRADE_B / T_K
# Calibrated: μ = 2000 cP @ 47°C, μ = 10 cP @ 150°C (18° API Baghewala crude)
# B = (ln(2000)-ln(10)) / (1/320.15 - 1/423.15) = 6968.65
# A = ln(2000) - 6968.65/320.15 = -14.1659
# More numerically stable than Walther/ASTM D341 for heavy oil over 40-200°C range.
# ---------------------------------------------------------------------------

ANDRADE_A: float = -14.1659                   # Andrade intercept, dimensionless [1][2]
ANDRADE_B: float = 6968.65                    # Andrade slope [K] (activation energy/R)
# Legacy aliases — do not use directly; import from simulator.wellbore.viscosity
WALTHER_A: float = ANDRADE_A
WALTHER_B: float = ANDRADE_B

VISCOSITY_REFERENCE_TEMP_C: float = 100.0     # Reference temp for PI calculation [°C]
VISCOSITY_REFERENCE_CP: float = 50.0          # Reference viscosity [cP] at reference temp, [1]


# ---------------------------------------------------------------------------
# IPR / Productivity Index — Vogel (1968) [7]
# ---------------------------------------------------------------------------

PI_REFERENCE_M3_DAY_KPA: float = 0.004        # PI at reference viscosity [m³/(day·kPa)], [1][7]
VOGEL_C1: float = 0.2                         # Vogel equation coefficient 1 [7]
VOGEL_C2: float = 0.8                         # Vogel equation coefficient 2 [7]
FLOWING_BOTTOMHOLE_PRESSURE_KPA: float = 800.0
# Approximate Pwf during production [kPa], [1]


# ---------------------------------------------------------------------------
# CSS Operating Parameters (LITERATURE_ASSUMPTION)
# ---------------------------------------------------------------------------

STEAM_INJECTION_RATE_T_DAY: float = 100.0     # Default injection rate [tonnes/day], [2][9]
STEAM_QUALITY_DEFAULT: float = 0.75           # Steam quality (dryness fraction), [2]
STEAM_TEMPERATURE_C: float = 200.0            # Approximate saturation temp at injection P, [2]
SOAK_DAYS_DEFAULT: float = 14.0               # Default soak period [days], [2][9]
PRODUCTION_CUTOFF_WOR: float = 10.0           # Water-oil ratio to end cycle, [9]
INJECTION_DURATION_DAYS: float = 7.0          # Default steam injection period [days]

FRACTURE_PRESSURE_GRADIENT_KPA_M: float = 18.5
# Fracture pressure gradient [kPa/m]; hard constraint ceiling for injection P, [1]
# Fracture pressure = FPG × depth (hard constraint, never violated in recommendations)


# ---------------------------------------------------------------------------
# SRP Parameters (LITERATURE_ASSUMPTION, refs [3][4][5])
# ---------------------------------------------------------------------------

SPM_DEFAULT: float = 5.0                      # Default strokes per minute, [3]
SPM_MIN: float = 1.0
SPM_MAX: float = 12.0
STROKE_LENGTH_M_DEFAULT: float = 2.4          # [m], [5]
STROKE_LENGTH_M_MIN: float = 0.5
STROKE_LENGTH_M_MAX: float = 4.5
VFD_FREQUENCY_HZ_DEFAULT: float = 45.0        # VFD drive frequency [Hz], [3]
VFD_FREQUENCY_HZ_MIN: float = 20.0
VFD_FREQUENCY_HZ_MAX: float = 60.0

PUMP_PLUNGER_DIA_MM: float = 50.8             # 2-inch plunger, common for heavy oil [5]
ROD_DIAMETER_M: float = 0.022225              # 7/8-inch rod (22.225 mm), [6]
ROD_STRING_LENGTH_M: float = RESERVOIR_DEPTH_M  # Rod length ≈ well depth
MOTOR_EFFICIENCY: float = 0.90                # Electric motor efficiency, [3][5]

DAMPING_BASE: float = 0.05                    # β₀ base damping coefficient [1/s], [4]
# Damping β(T) = β₀ × (μ(T)/μ_ref)^0.5 — viscous drag coupling [4]

ROD_WEIGHT_PER_M_KG: float = 3.63            # 7/8-inch rod linear weight [kg/m], [6]


# ---------------------------------------------------------------------------
# Rod Stress / Goodman Criterion [11][6]
# ---------------------------------------------------------------------------

ROD_ENDURANCE_LIMIT_MPA: float = 207.0        # S_e, API Grade D rod, [6]
ROD_ULTIMATE_STRENGTH_MPA: float = 620.0      # S_u, API Grade D rod, [6]
ROD_CROSS_SECTION_M2: float = float(np.pi / 4 * ROD_DIAMETER_M**2)


# ---------------------------------------------------------------------------
# Sensor noise defaults (used when Volve calibration is not available)
# Based on industry practice; see docs/data_strategy.md
# ---------------------------------------------------------------------------

NOISE_OIL_RATE_SIGMA_FRAC: float = 0.02       # 2% of reading
NOISE_TEMP_SIGMA_C: float = 0.5               # °C
NOISE_PRESSURE_SIGMA_KPA: float = 50.0        # kPa
NOISE_CURRENT_SIGMA_FRAC: float = 0.015       # 1.5% of reading
NOISE_SPIKE_PROB: float = 0.002               # per tick
NOISE_DROPOUT_PROB: float = 0.001             # per tick
NOISE_DRIFT_RATE: float = 0.001               # fractional drift per tick


# ---------------------------------------------------------------------------
# Simulation control
# ---------------------------------------------------------------------------

TICK_INTERVAL_S: float = 1.5                  # Simulated tick every 1.5 s wall time
DEFAULT_TIME_ACCELERATION: int = 10           # 10x: 1 tick = 10 min simulated time
NUM_WELLS_DEFAULT: int = 10                   # Default number of wells to simulate
DYNO_CARD_POINTS: int = 150                   # Points per dynamometer card stroke
RANDOM_SEED: int = 42                         # Deterministic seed for reproducibility


# ---------------------------------------------------------------------------
# Dataclass for per-well configuration (used by the simulator)
# ---------------------------------------------------------------------------

@dataclass
class WellParameters:
    """
    Complete parameter set for one simulated well.
    Defaults represent a 'typical' Baghewala well (LITERATURE_ASSUMPTION except where noted).
    """
    well_id: str = "W01"
    well_name: str = "Well-01"

    # Reservoir (FIELD_FACT where noted)
    initial_temp_c: float = RESERVOIR_TEMP_INITIAL_C          # FIELD_FACT
    api_gravity: float = API_GRAVITY_DEFAULT                   # FIELD_FACT
    reservoir_pressure_kpa: float = RESERVOIR_PRESSURE_KPA
    depth_m: float = RESERVOIR_DEPTH_M
    pay_thickness_m: float = PAY_THICKNESS_M
    porosity: float = POROSITY_FRACTION
    permeability_md: float = PERMEABILITY_MD

    # CSS
    steam_volume_cwe_m3: float = 500.0
    injection_pressure_kpa: float = 4000.0
    steam_quality: float = STEAM_QUALITY_DEFAULT
    soak_days: float = SOAK_DAYS_DEFAULT
    production_cutoff_wor: float = PRODUCTION_CUTOFF_WOR

    # SRP
    spm: float = SPM_DEFAULT
    stroke_length_m: float = STROKE_LENGTH_M_DEFAULT
    vfd_frequency_hz: float = VFD_FREQUENCY_HZ_DEFAULT
    pump_plunger_dia_m: float = PUMP_PLUNGER_DIA_MM / 1000.0
    rod_diameter_m: float = ROD_DIAMETER_M
    rod_string_length_m: float = ROD_STRING_LENGTH_M

    # Seed for reproducibility
    seed: int = RANDOM_SEED


def make_well_fleet(n: int = NUM_WELLS_DEFAULT, base_seed: int = RANDOM_SEED) -> list[WellParameters]:
    """
    Generate a fleet of n wells with slightly varied parameters (realistic heterogeneity).
    Parameters are varied within the literature ranges defined in this config.
    """
    rng = np.random.default_rng(base_seed)
    wells = []
    for i in range(n):
        w = WellParameters(
            well_id=f"W{i+1:02d}",
            well_name=f"Well-{i+1:02d}",
            initial_temp_c=float(rng.uniform(RESERVOIR_TEMP_INITIAL_C_MIN, RESERVOIR_TEMP_INITIAL_C_MAX)),
            api_gravity=float(rng.uniform(API_GRAVITY_MIN, API_GRAVITY_MAX)),
            reservoir_pressure_kpa=float(rng.uniform(3500.0, 5000.0)),
            depth_m=float(rng.uniform(700.0, 900.0)),
            pay_thickness_m=float(rng.uniform(15.0, 25.0)),
            permeability_md=float(rng.uniform(200.0, 800.0)),
            steam_volume_cwe_m3=float(rng.uniform(300.0, 800.0)),
            injection_pressure_kpa=float(rng.uniform(3000.0, 5500.0)),
            steam_quality=float(rng.uniform(0.70, 0.85)),
            soak_days=float(rng.uniform(7.0, 21.0)),
            spm=float(rng.uniform(3.0, 7.0)),
            stroke_length_m=float(rng.uniform(1.5, 3.5)),
            vfd_frequency_hz=float(rng.uniform(35.0, 55.0)),
            seed=base_seed + i,
        )
        wells.append(w)
    return wells
