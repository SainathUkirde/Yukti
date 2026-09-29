"""
data/generators/well_completion.py
Generate synthetic well completion and reservoir data for the 10-well Baghewala fleet.

SYNTHETIC_HISTORICAL — generated from WellParameters in simulator/config.py.
Parameters vary within published literature ranges for the Jodhpur Sandstone / heavy oil fields.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import numpy as np
from simulator.config import make_well_fleet


def generate_well_completion(n_wells: int = 10, seed: int = 42) -> pd.DataFrame:
    """
    Generate well completion and reservoir parameter table.

    Returns
    -------
    pd.DataFrame  with schema matching data/schemas/well_completion.schema.json
    """
    fleet = make_well_fleet(n_wells, seed)
    records = []
    for i, w in enumerate(fleet):
        # Slightly varied lat/lon around a central point (Baghewala area — approximate)
        rng = np.random.default_rng(seed + i)
        lat = 29.35 + rng.uniform(-0.05, 0.05)
        lon = 74.05 + rng.uniform(-0.05, 0.05)

        records.append({
            "well_id": w.well_id,
            "well_name": w.well_name,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "total_depth_m": round(w.depth_m, 1),
            "pay_zone_top_m": round(w.depth_m - w.pay_thickness_m - 5.0, 1),
            "pay_zone_bottom_m": round(w.depth_m - 5.0, 1),
            "pay_thickness_m": round(w.pay_thickness_m, 1),
            "porosity_fraction": round(w.porosity, 3),
            "permeability_md": round(w.permeability_md, 1),
            "initial_reservoir_temp_c": round(w.initial_temp_c, 2),
            "initial_reservoir_pressure_kpa": round(w.reservoir_pressure_kpa, 1),
            "api_gravity": round(w.api_gravity, 2),
            "rod_string_grade": "D",
            "pump_plunger_dia_mm": round(w.pump_plunger_dia_m * 1000.0, 1),
            "provenance": "LITERATURE_ASSUMPTION",
            "notes": (
                "FIELD_FACT: initial_reservoir_temp_c (46-48°C), api_gravity (17-19). "
                "All other values LITERATURE_ASSUMPTION from Jodhpur Sandstone / published heavy-oil ranges."
            ),
        })
    return pd.DataFrame(records)
