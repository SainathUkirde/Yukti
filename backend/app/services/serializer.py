"""
backend/app/services/serializer.py
Converts WellStateSnapshot to JSON-serializable dict with provenance tags.
All numeric values wrapped in {value, provenance, unit} objects.
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from simulator.well_system import WellStateSnapshot
from datetime import datetime, timezone


def _pf(value: float, unit: str = "", source: str = None) -> dict:
    """ProvenancedFloat for SIMULATED_LIVE values."""
    d = {"value": round(float(value), 5), "provenance": "SIMULATED_LIVE", "unit": unit}
    if source:
        d["source"] = source
    return d


def snapshot_to_dict(state: WellStateSnapshot) -> dict:
    """
    Serialize a WellStateSnapshot to a JSON-compatible dict.
    Every numeric field carries provenance = SIMULATED_LIVE.
    """
    return {
        # Identity
        "well_id": state.well_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tick": state.tick,
        "sim_time_days": round(state.sim_time_days, 3),
        "cycle_number": state.cycle_number,
        "phase": state.phase,
        "time_in_phase_days": round(state.time_in_phase_days, 3),

        # Reservoir
        "reservoir_temp_c":         _pf(state.reservoir_temp_c, "°C"),
        "heated_zone_radius_m":     _pf(state.heated_zone_radius_m, "m"),
        "reservoir_pressure_kpa":   _pf(state.reservoir_pressure_kpa, "kPa"),
        "oil_viscosity_cp":         _pf(state.oil_viscosity_cp, "cP"),
        "T_peak_c":                 _pf(state.T_peak_c, "°C"),

        # Production
        "oil_rate_m3d":             _pf(state.oil_rate_m3d, "m³/day"),
        "water_rate_m3d":           _pf(state.water_rate_m3d, "m³/day"),
        "water_cut_fraction":       _pf(state.water_cut_fraction, ""),
        "cum_oil_m3":               _pf(state.cum_oil_m3, "m³"),
        "cum_water_m3":             _pf(state.cum_water_m3, "m³"),
        "sor":                      _pf(state.sor, "bbl/bbl"),

        # SRP
        "spm":                      _pf(state.spm, "strokes/min"),
        "stroke_length_m":          _pf(state.stroke_length_m, "m"),
        "vfd_frequency_hz":         _pf(state.vfd_frequency_hz, "Hz"),
        "peak_load_kn":             _pf(state.peak_load_kn, "kN"),
        "min_load_kn":              _pf(state.min_load_kn, "kN"),
        "pump_fillage_fraction":    _pf(state.pump_fillage_fraction, ""),
        "pump_efficiency_fraction": _pf(state.pump_efficiency_fraction, ""),
        "motor_power_kw":           _pf(state.motor_power_kw, "kW"),
        "kwh_per_bbl":              _pf(state.kwh_per_bbl, "kWh/bbl"),

        # Risk
        "rod_float_risk_ratio":     _pf(state.rod_float_risk_ratio, ""),
        "rod_float_risk_score":     _pf(state.rod_float_risk_score, "0-100"),
        "goodman_ratio":            _pf(state.goodman_ratio, ""),

        # Faults & alerts
        "active_fault": state.active_fault,
        "fault_severity": round(state.fault_severity, 3),
        "active_alerts": state.active_alerts,

        # Dyno card (round to 4dp to reduce payload size)
        "surface_position_m":  [round(v, 4) for v in state.surface_position_m],
        "surface_load_kn":     [round(v, 4) for v in state.surface_load_kn],
        "downhole_position_m": [round(v, 4) for v in state.downhole_position_m],
        "downhole_load_kn":    [round(v, 4) for v in state.downhole_load_kn],

        # Sensor deviation
        "twin_sensor_deviation_pct": _pf(state.twin_sensor_deviation_pct, "%"),

        # Config in use
        "config": {
            "well_id": state.config.well_id,
            "spm": state.config.spm,
            "stroke_length_m": state.config.stroke_length_m,
            "vfd_frequency_hz": state.config.vfd_frequency_hz,
            "steam_volume_cwe_m3": state.config.steam_volume_cwe_m3,
            "soak_days": state.config.soak_days,
        },

        "provenance": "SIMULATED_LIVE",
    }
