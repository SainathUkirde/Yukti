"""
data/generators/dyno_cards.py
Generate labeled dynamometer cards using the wave-equation simulator.

Dataset: SYNTHETIC_HISTORICAL
Labels: normal, rod_floating, pump_off, gas_interference, fluid_pound, pump_unsetting

Each card is generated at realistic operating conditions.
Fault cards are generated at conditions where that fault physically occurs.
The label distribution is approximately:
  normal:           40%
  rod_floating:     20%  (most common in heavy-oil SRP)
  pump_off:         15%
  gas_interference: 10%
  fluid_pound:       8%
  pump_unsetting:    7%
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import numpy as np
from simulator.config import make_well_fleet, STEAM_TEMPERATURE_C, DYNO_CARD_POINTS
from simulator.wellbore.viscosity import viscosity_cp
from simulator.reservoir.heated_zone import peak_temperature_c, reservoir_temperature_c
from simulator.srp.wave_equation import simulate_stroke
from simulator.srp.rod_float import rod_float_risk_ratio


# Target class distribution
FAULT_DISTRIBUTION = {
    "normal": 0.40,
    "rod_floating": 0.20,
    "pump_off": 0.15,
    "gas_interference": 0.10,
    "fluid_pound": 0.08,
    "pump_unsetting": 0.07,
}


def _sample_operating_conditions(well, rng: np.random.Generator, fault_type: str):
    """
    Sample realistic operating conditions for a given fault type.
    Rod-floating cards are generated at high viscosity + high SPM conditions.
    Normal cards at moderate viscosity.
    """
    if fault_type == "rod_floating":
        # High viscosity (late cycle / cold reservoir) + moderate-high SPM
        t_prod = float(rng.uniform(40, 120))
        spm = float(rng.uniform(5.0, 8.0))
    elif fault_type == "pump_off":
        # Very low reservoir pressure
        t_prod = float(rng.uniform(80, 150))
        spm = float(rng.uniform(3.0, 6.0))
    elif fault_type in ("gas_interference", "fluid_pound"):
        # High gas rates — early production with low Pwf
        t_prod = float(rng.uniform(5, 30))
        spm = float(rng.uniform(4.0, 7.0))
    else:
        t_prod = float(rng.uniform(10, 80))
        spm = float(rng.uniform(3.0, 7.0))

    T_peak = peak_temperature_c(
        well.steam_volume_cwe_m3, well.steam_quality, well.pay_thickness_m,
        well.porosity, well.initial_temp_c, STEAM_TEMPERATURE_C,
    )
    T_res = reservoir_temperature_c(T_peak, well.initial_temp_c, t_prod)
    mu = viscosity_cp(T_res, well.api_gravity)
    stroke = float(rng.uniform(1.8, 3.2))
    Pr = well.reservoir_pressure_kpa * float(rng.uniform(0.5, 0.9))
    q_oil = max(float(rng.uniform(2.0, 15.0)), 0.5)
    return mu, spm, stroke, Pr, q_oil, T_res


def generate_dyno_cards(
    n_wells: int = 10,
    n_cards: int = 8000,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate n_cards labeled dynamometer cards.

    Returns
    -------
    pd.DataFrame  matching dyno_cards_labeled schema
      Columns: well_id, card_id, fault_label, fault_confidence,
               surface_position_m (list), surface_load_kn (list),
               downhole_position_m (list), downhole_load_kn (list),
               fillage_fraction, peak_load_kn, min_load_kn,
               rod_float_risk_ratio, oil_viscosity_cp, spm,
               reservoir_temp_c, provenance
    """
    fleet = make_well_fleet(n_wells, seed)
    rng = np.random.default_rng(seed)

    # Compute how many cards per fault class
    fault_types = list(FAULT_DISTRIBUTION.keys())
    fault_counts = {
        ft: int(n_cards * frac) for ft, frac in FAULT_DISTRIBUTION.items()
    }
    # Adjust for rounding
    fault_counts["normal"] += n_cards - sum(fault_counts.values())

    records = []
    card_id = 0

    for fault_type, count in fault_counts.items():
        for i in range(count):
            well = fleet[int(rng.integers(0, n_wells))]
            mu, spm, stroke, Pr, q_oil, T_res = _sample_operating_conditions(
                well, rng, fault_type
            )

            # For normal cards, no fault injection; for fault cards, severity ~0.6-1.0
            if fault_type == "normal":
                ft_arg = None
                severity = 0.0
            else:
                ft_arg = fault_type
                severity = float(rng.uniform(0.5, 1.0))

            dyno = simulate_stroke(
                stroke_length_m=stroke,
                spm=spm,
                rod_length_m=well.rod_string_length_m,
                rod_diameter_m=well.rod_diameter_m,
                plunger_dia_m=well.pump_plunger_dia_m,
                oil_viscosity_cp=mu,
                reservoir_pressure_kpa=Pr,
                oil_rate_m3d=q_oil,
                pump_depth_m=well.depth_m,
                fault_type=ft_arg,
                fault_severity=severity,
                n_points=DYNO_CARD_POINTS,
            )

            rf = rod_float_risk_ratio(stroke, spm, well.rod_diameter_m,
                                       well.rod_string_length_m, mu)

            # Confidence: for labeled synthetic data = 1.0 for true labels.
            # Add slight noise to a subset (10%) to simulate labeling uncertainty.
            confidence = 1.0
            actual_label = fault_type
            if rng.random() < 0.10:
                # Mislabel a small fraction to make classifier training realistic
                other = [f for f in fault_types if f != fault_type]
                actual_label = str(rng.choice(other))
                confidence = float(rng.uniform(0.55, 0.75))

            records.append({
                "card_id": f"card_{card_id:06d}",
                "well_id": well.well_id,
                "fault_label": actual_label,
                "fault_confidence": round(confidence, 3),
                "surface_position_m": dyno.surface_position_m.tolist(),
                "surface_load_kn": dyno.surface_load_kn.tolist(),
                "downhole_position_m": dyno.downhole_position_m.tolist(),
                "downhole_load_kn": dyno.downhole_load_kn.tolist(),
                "fillage_fraction": round(dyno.fillage_fraction, 4),
                "peak_load_kn": round(dyno.peak_load_kn, 3),
                "min_load_kn": round(dyno.min_load_kn, 3),
                "pump_efficiency_fraction": round(dyno.pump_efficiency_fraction, 4),
                "rod_float_risk_ratio": round(rf, 4),
                "oil_viscosity_cp": round(mu, 1),
                "spm": round(spm, 2),
                "stroke_length_m": round(stroke, 3),
                "reservoir_temp_c": round(T_res, 2),
                "motor_power_kw": round(dyno.motor_power_kw, 3),
                "kwh_per_bbl": round(dyno.kwh_per_bbl, 3),
                "provenance": "SYNTHETIC_HISTORICAL",
            })
            card_id += 1

    df = pd.DataFrame(records)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)  # shuffle
    return df
