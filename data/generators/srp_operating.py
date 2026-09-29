"""
data/generators/srp_operating.py
Generate SRP operating data (hourly) using the wave-equation simulator.

Dataset: SYNTHETIC_HISTORICAL
Covers: all wells, all production days from production_history.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from simulator.config import (
    make_well_fleet, MOTOR_EFFICIENCY,
    FLOWING_BOTTOMHOLE_PRESSURE_KPA,
    PI_REFERENCE_M3_DAY_KPA, VISCOSITY_REFERENCE_CP,
    STEAM_TEMPERATURE_C,
)
from simulator.reservoir.heated_zone import peak_temperature_c, reservoir_temperature_c
from simulator.reservoir.ipr import vogel_oil_rate, reservoir_pressure_decline
from simulator.wellbore.viscosity import viscosity_cp
from simulator.srp.wave_equation import simulate_stroke
from simulator.srp.rod_float import rod_float_risk_ratio, rod_float_risk_score_0_100


def generate_srp_operating(
    n_wells: int = 10,
    n_cycles: int = 8,
    seed: int = 42,
    samples_per_cycle: int = 24,  # hourly samples per production day (sub-sampled)
    start_date: str = "2019-01-01",
) -> pd.DataFrame:
    """
    Generate hourly SRP operating data for each well across all CSS cycles.

    Each record represents one stroke-average measurement per hour during production.
    SPM is varied slightly over the production period to simulate operational adjustments.

    Returns
    -------
    pd.DataFrame  matching srp_operating_data.schema.json
    """
    fleet = make_well_fleet(n_wells, seed)
    rng = np.random.default_rng(seed)
    records = []

    for w in fleet:
        w_start = datetime.fromisoformat(start_date) + timedelta(
            days=int(rng.integers(0, 30))
        )
        current_date = w_start
        inject_duration = 7.0
        Pr = w.reservoir_pressure_kpa

        for cycle_n in range(1, n_cycles + 1):
            # Skip injection + soak
            current_date += timedelta(days=int(inject_duration + w.soak_days))

            T_peak = peak_temperature_c(
                w.steam_volume_cwe_m3, w.steam_quality, w.pay_thickness_m,
                w.porosity, w.initial_temp_c, STEAM_TEMPERATURE_C,
                cycle_number=cycle_n,
            )

            t_prod = 0.0
            max_prod = 200
            from simulator.reservoir.ipr import water_oil_ratio
            WOR_cut = w.production_cutoff_wor

            # SPM profile: starts at default, may be reduced mid-cycle if floating risk rises
            spm_current = w.spm + float(rng.uniform(-0.5, 0.5))

            while t_prod < max_prod:
                T_res = reservoir_temperature_c(T_peak, w.initial_temp_c, t_prod)
                mu = viscosity_cp(T_res, w.api_gravity)
                Pr = reservoir_pressure_decline(Pr, 1.0)

                q_oil = vogel_oil_rate(Pr, FLOWING_BOTTOMHOLE_PRESSURE_KPA, mu,
                                       PI_REFERENCE_M3_DAY_KPA, VISCOSITY_REFERENCE_CP)
                wor = water_oil_ratio(t_prod, T_peak, w.initial_temp_c)

                # Adaptive SPM: reduce if rod float risk is high
                rf = rod_float_risk_ratio(
                    w.stroke_length_m, spm_current,
                    w.rod_diameter_m, w.rod_string_length_m, mu
                )
                if rf > 1.2:
                    spm_current = max(spm_current * 0.85, 2.0)  # reduce 15%
                elif rf < 0.7 and spm_current < w.spm + 0.5:
                    spm_current = min(spm_current * 1.05, w.spm + 1.0)

                # Simulate one stroke
                dyno = simulate_stroke(
                    stroke_length_m=w.stroke_length_m,
                    spm=spm_current,
                    rod_length_m=w.rod_string_length_m,
                    rod_diameter_m=w.rod_diameter_m,
                    plunger_dia_m=w.pump_plunger_dia_m,
                    oil_viscosity_cp=mu,
                    reservoir_pressure_kpa=Pr,
                    oil_rate_m3d=max(q_oil, 0.001),
                    pump_depth_m=w.depth_m,
                    motor_efficiency=MOTOR_EFFICIENCY,
                )

                motor_current = (dyno.motor_power_kw * 1000.0) / (
                    3.0 ** 0.5 * 415.0 * 0.85
                )  # 3-phase, 415V, PF=0.85

                noise = lambda s=0.02: float(rng.normal(1.0, s))

                records.append({
                    "well_id": w.well_id,
                    "timestamp": (current_date + timedelta(days=t_prod)).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ),
                    "cycle_number": cycle_n,
                    "t_production_days": round(t_prod, 3),
                    "spm": round(spm_current * noise(0.01), 3),
                    "stroke_length_m": round(w.stroke_length_m * noise(0.005), 4),
                    "vfd_frequency_hz": round(w.vfd_frequency_hz * noise(0.01), 2),
                    "motor_current_a": round(motor_current * noise(), 2),
                    "motor_power_kw": round(dyno.motor_power_kw * noise(), 3),
                    "polished_rod_load_kn": round(dyno.peak_load_kn * noise(0.015), 3),
                    "min_rod_load_kn": round(dyno.min_load_kn * noise(0.015), 3),
                    "pump_fillage_fraction": round(dyno.fillage_fraction * noise(0.02), 4),
                    "pump_efficiency_fraction": round(dyno.pump_efficiency_fraction * noise(0.02), 4),
                    "kwh_per_bbl": round(dyno.kwh_per_bbl * noise(), 3),
                    "oil_rate_m3d": round(q_oil * noise(), 4),
                    "reservoir_temp_c": round(T_res + float(rng.normal(0, 0.3)), 2),
                    "oil_viscosity_cp": round(mu * noise(0.03), 1),
                    "rod_float_risk_ratio": round(rf, 4),
                    "rod_float_risk_score": round(rod_float_risk_score_0_100(rf), 2),
                    "active_fault": None,
                    "provenance": "SYNTHETIC_HISTORICAL",
                })

                t_prod += 1.0  # daily resolution
                if wor >= WOR_cut:
                    break

            current_date += timedelta(days=int(t_prod))
            # Idle gap
            current_date += timedelta(days=int(rng.integers(3, 10)))

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["well_id", "timestamp"]).reset_index(drop=True)
    return df
