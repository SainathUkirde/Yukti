"""
data/generators/production_history.py
Generate daily production history for all wells using the physics simulator.

Dataset: SYNTHETIC_HISTORICAL
Covers: 5 years of simulated production, multiple CSS cycles per well.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from simulator.config import (
    make_well_fleet,
    STEAM_TEMPERATURE_C,
    THERMAL_DECAY_CONSTANT_PER_DAY,
    FLOWING_BOTTOMHOLE_PRESSURE_KPA,
    PI_REFERENCE_M3_DAY_KPA,
    VISCOSITY_REFERENCE_CP,
)
from simulator.reservoir.heated_zone import (
    peak_temperature_c, reservoir_temperature_c
)
from simulator.reservoir.ipr import (
    vogel_oil_rate, water_oil_ratio, water_cut_from_wor, reservoir_pressure_decline
)
from simulator.wellbore.viscosity import viscosity_cp
from simulator.reservoir.heated_zone import sor as compute_sor


def generate_production_history(
    n_wells: int = 10,
    n_cycles: int = 8,
    seed: int = 42,
    start_date: str = "2019-01-01",
) -> pd.DataFrame:
    """
    Generate daily production history for all wells.

    For each well, simulates through n_cycles CSS cycles.
    Each cycle: injection (7 days) → soak (well.soak_days) → production (until WOR cut-off).

    Returns
    -------
    pd.DataFrame  matching production_history.schema.json
    """
    fleet = make_well_fleet(n_wells, seed)
    rng = np.random.default_rng(seed)
    all_records = []

    for w in fleet:
        w_start = datetime.fromisoformat(start_date) + timedelta(
            days=int(rng.integers(0, 30))
        )
        current_date = w_start
        Pr_base = w.reservoir_pressure_kpa
        cum_oil = 0.0
        cum_water = 0.0
        inject_duration = 7.0

        for cycle_n in range(1, n_cycles + 1):
            # ── INJECTION PHASE ──────────────────────────────────────────
            for d in range(int(inject_duration)):
                all_records.append({
                    "well_id": w.well_id,
                    "date": (current_date + timedelta(days=d)).strftime("%Y-%m-%d"),
                    "cycle_number": cycle_n,
                    "phase": "injection",
                    "oil_rate_m3d": 0.0,
                    "water_rate_m3d": 0.0,
                    "gas_rate_m3d": float(rng.uniform(0.05, 0.2)),
                    "cum_oil_m3": round(cum_oil, 2),
                    "water_cut_fraction": 0.0,
                    "reservoir_temp_c": round(w.initial_temp_c + cycle_n * 2.0, 2),
                    "bottomhole_pressure_kpa": round(w.injection_pressure_kpa * 0.9, 1),
                    "sor": 0.0,
                    "provenance": "SYNTHETIC_HISTORICAL",
                })
            current_date += timedelta(days=int(inject_duration))

            # ── SOAK PHASE ───────────────────────────────────────────────
            T_peak = peak_temperature_c(
                w.steam_volume_cwe_m3, w.steam_quality, w.pay_thickness_m,
                w.porosity, w.initial_temp_c, STEAM_TEMPERATURE_C,
                cycle_number=cycle_n,
            )
            for d in range(int(w.soak_days)):
                progress = d / max(w.soak_days, 1.0)
                T_soak = w.initial_temp_c + (T_peak - w.initial_temp_c) * progress
                all_records.append({
                    "well_id": w.well_id,
                    "date": (current_date + timedelta(days=d)).strftime("%Y-%m-%d"),
                    "cycle_number": cycle_n,
                    "phase": "soak",
                    "oil_rate_m3d": 0.0,
                    "water_rate_m3d": 0.0,
                    "gas_rate_m3d": 0.0,
                    "cum_oil_m3": round(cum_oil, 2),
                    "water_cut_fraction": 0.0,
                    "reservoir_temp_c": round(T_soak, 2),
                    "bottomhole_pressure_kpa": round(Pr_base * 0.85, 1),
                    "sor": 0.0,
                    "provenance": "SYNTHETIC_HISTORICAL",
                })
            current_date += timedelta(days=int(w.soak_days))

            # ── PRODUCTION PHASE ─────────────────────────────────────────
            Pr = Pr_base * float(rng.uniform(0.9, 1.0))  # slight pressure variation
            t_prod = 0.0
            cycle_oil = 0.0
            max_prod = 200

            while t_prod < max_prod:
                T_res = reservoir_temperature_c(T_peak, w.initial_temp_c, t_prod)
                mu = viscosity_cp(T_res, w.api_gravity)
                Pr = reservoir_pressure_decline(Pr, 1.0)
                q_oil = vogel_oil_rate(Pr, FLOWING_BOTTOMHOLE_PRESSURE_KPA, mu,
                                       PI_REFERENCE_M3_DAY_KPA, VISCOSITY_REFERENCE_CP)
                wor = water_oil_ratio(t_prod, T_peak, w.initial_temp_c)
                wc = water_cut_from_wor(wor)
                q_water = q_oil * wor

                # Add sensor noise ~2-3%
                noise = float(rng.normal(1.0, 0.025))
                q_oil_noisy = max(q_oil * noise, 0.0)
                q_water_noisy = max(q_water * float(rng.normal(1.0, 0.03)), 0.0)
                gas_rate = float(rng.uniform(0.1, 0.5)) * q_oil_noisy / 10.0

                cum_oil += q_oil_noisy
                cum_water += q_water_noisy
                cycle_oil += q_oil_noisy
                cycle_sor = compute_sor(w.steam_volume_cwe_m3, max(cycle_oil, 0.001))

                all_records.append({
                    "well_id": w.well_id,
                    "date": (current_date + timedelta(days=int(t_prod))).strftime("%Y-%m-%d"),
                    "cycle_number": cycle_n,
                    "phase": "production",
                    "oil_rate_m3d": round(q_oil_noisy, 4),
                    "water_rate_m3d": round(q_water_noisy, 4),
                    "gas_rate_m3d": round(gas_rate, 5),
                    "cum_oil_m3": round(cum_oil, 2),
                    "water_cut_fraction": round(wc, 4),
                    "reservoir_temp_c": round(T_res + float(rng.normal(0, 0.3)), 2),
                    "bottomhole_pressure_kpa": round(Pr + float(rng.normal(0, 30)), 1),
                    "sor": round(cycle_sor, 3),
                    "provenance": "SYNTHETIC_HISTORICAL",
                })
                t_prod += 1.0
                if wor >= w.production_cutoff_wor:
                    break

            current_date += timedelta(days=int(t_prod))

            # ── IDLE ─────────────────────────────────────────────────────
            idle_days = int(rng.integers(3, 10))
            for d in range(idle_days):
                all_records.append({
                    "well_id": w.well_id,
                    "date": (current_date + timedelta(days=d)).strftime("%Y-%m-%d"),
                    "cycle_number": cycle_n,
                    "phase": "idle",
                    "oil_rate_m3d": 0.0,
                    "water_rate_m3d": 0.0,
                    "gas_rate_m3d": 0.0,
                    "cum_oil_m3": round(cum_oil, 2),
                    "water_cut_fraction": 0.0,
                    "reservoir_temp_c": round(w.initial_temp_c + float(rng.normal(0, 0.5)), 2),
                    "bottomhole_pressure_kpa": round(Pr_base * float(rng.normal(0.7, 0.05)), 1),
                    "sor": 0.0,
                    "provenance": "SYNTHETIC_HISTORICAL",
                })
            current_date += timedelta(days=idle_days)

    df = pd.DataFrame(all_records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["well_id", "date"]).reset_index(drop=True)
    return df
