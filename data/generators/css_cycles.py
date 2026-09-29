"""
data/generators/css_cycles.py
Generate synthetic CSS cycle records by running the physics simulator
through complete CSS cycles for each well.

Dataset: SYNTHETIC_HISTORICAL
Source: simulator/reservoir/heated_zone.py, simulator/reservoir/ipr.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from simulator.config import make_well_fleet, STEAM_TEMPERATURE_C, THERMAL_DECAY_CONSTANT_PER_DAY
from simulator.reservoir.heated_zone import (
    heated_zone_radius_m, peak_temperature_c, reservoir_temperature_c, sor
)
from simulator.reservoir.ipr import (
    vogel_oil_rate, water_oil_ratio, reservoir_pressure_decline
)
from simulator.wellbore.viscosity import viscosity_cp
from simulator.config import (
    FLOWING_BOTTOMHOLE_PRESSURE_KPA,
    PI_REFERENCE_M3_DAY_KPA,
    VISCOSITY_REFERENCE_CP,
)


def simulate_cycle(
    well,
    cycle_number: int,
    start_date: datetime,
    inject_duration_days: float = 7.0,
    rng: np.random.Generator = None,
) -> dict:
    """
    Simulate one complete CSS cycle and return a record dict.
    Adds realistic noise (~3-5%) to simulated outputs.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    # Phase 1: Injection
    inject_end = start_date + timedelta(days=inject_duration_days)

    # Phase 2: Soak — compute peak temperature
    T_peak = peak_temperature_c(
        well.steam_volume_cwe_m3,
        well.steam_quality,
        well.pay_thickness_m,
        well.porosity,
        well.initial_temp_c,
        STEAM_TEMPERATURE_C,
        cycle_number=cycle_number,
    )
    soak_end = inject_end + timedelta(days=well.soak_days)

    # Phase 3: Production — simulate until WOR cut-off
    prod_start = soak_end
    Pr = well.reservoir_pressure_kpa
    t_prod = 0.0
    dt = 1.0  # daily time steps
    cum_oil = 0.0
    cum_water = 0.0
    WOR_cutoff = well.production_cutoff_wor
    max_prod_days = 180  # safety cap

    while t_prod < max_prod_days:
        T_res = reservoir_temperature_c(T_peak, well.initial_temp_c, t_prod)
        mu = viscosity_cp(T_res, well.api_gravity)
        Pr = reservoir_pressure_decline(Pr, dt)
        q_oil = vogel_oil_rate(Pr, FLOWING_BOTTOMHOLE_PRESSURE_KPA, mu,
                                PI_REFERENCE_M3_DAY_KPA, VISCOSITY_REFERENCE_CP)
        wor = water_oil_ratio(t_prod, T_peak, well.initial_temp_c)
        q_water = q_oil * wor

        cum_oil += q_oil * dt
        cum_water += q_water * dt
        t_prod += dt

        if wor >= WOR_cutoff:
            break

    cycle_end = prod_start + timedelta(days=t_prod)
    cycle_sor = sor(well.steam_volume_cwe_m3, max(cum_oil, 0.001))

    # Add small realistic noise (~3%)
    noise_fac = lambda: float(rng.normal(1.0, 0.03))

    return {
        "well_id": well.well_id,
        "cycle_number": cycle_number,
        "injection_start": start_date.isoformat(),
        "soak_start": inject_end.isoformat(),
        "production_start": soak_end.isoformat(),
        "cycle_end": cycle_end.isoformat(),
        "steam_volume_cwe_m3": round(well.steam_volume_cwe_m3 * noise_fac(), 1),
        "injection_pressure_kpa": round(well.injection_pressure_kpa * noise_fac(), 1),
        "steam_quality_fraction": round(float(np.clip(well.steam_quality * noise_fac(), 0.5, 1.0)), 3),
        "soak_days": round(well.soak_days * noise_fac(), 1),
        "peak_reservoir_temp_c": round(T_peak * noise_fac(), 2),
        "heated_zone_radius_m": round(heated_zone_radius_m(
            well.steam_volume_cwe_m3, well.steam_quality,
            well.pay_thickness_m, well.porosity,
            well.initial_temp_c, STEAM_TEMPERATURE_C,
            cycle_number=cycle_number
        ) * noise_fac(), 2),
        "cycle_oil_m3": round(cum_oil * noise_fac(), 2),
        "cycle_water_m3": round(cum_water * noise_fac(), 2),
        "cycle_sor": round(cycle_sor * noise_fac(), 3),
        "production_cutoff_wor": round(WOR_cutoff, 1),
        "production_duration_days": round(t_prod, 1),
        "cycle_duration_days": round(inject_duration_days + well.soak_days + t_prod, 1),
        "provenance": "SYNTHETIC_HISTORICAL",
    }


def generate_css_cycles(
    n_wells: int = 10,
    n_cycles: int = 8,
    seed: int = 42,
    start_date: str = "2019-01-01",
) -> pd.DataFrame:
    """
    Generate CSS cycle records for all wells over n_cycles cycles.

    Parameters
    ----------
    n_wells  : int    Number of wells
    n_cycles : int    CSS cycles per well
    seed     : int    Random seed
    start_date: str   Start date for the first injection

    Returns
    -------
    pd.DataFrame  matching css_cycle_records.schema.json
    """
    fleet = make_well_fleet(n_wells, seed)
    rng = np.random.default_rng(seed)
    records = []

    for w in fleet:
        # Each well starts at a slightly different time (realistic staggering)
        w_start = datetime.fromisoformat(start_date) + timedelta(
            days=int(rng.integers(0, 90))
        )
        cycle_start = w_start

        for c in range(1, n_cycles + 1):
            rec = simulate_cycle(w, c, cycle_start, rng=rng)
            records.append(rec)
            # Next cycle starts after current cycle ends + short idle gap
            cycle_end = datetime.fromisoformat(rec["cycle_end"])
            idle_days = int(rng.integers(3, 14))
            cycle_start = cycle_end + timedelta(days=idle_days)

    df = pd.DataFrame(records)
    df = df.sort_values(["well_id", "cycle_number"]).reset_index(drop=True)
    return df
