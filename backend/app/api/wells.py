"""
backend/app/api/wells.py
Wells endpoints — list, get state, get history.
"""
import logging
from fastapi import APIRouter, HTTPException, Request, Query

from backend.app.services.serializer import snapshot_to_dict

logger = logging.getLogger("api.wells")
router = APIRouter()


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


@router.get("/")
async def list_wells(request: Request):
    """Return summary for all active wells."""
    sim = _sim(request)
    summaries = []
    for well_id in sim.get_all_wells():
        state = sim.get_latest(well_id)
        params = sim.get_well_params(well_id)
        if state is None:
            continue
        risk = state.rod_float_risk_score
        if risk >= 70:
            color = "red"
        elif risk >= 40:
            color = "amber"
        else:
            color = "green"
        summaries.append({
            "well_id": well_id,
            "well_name": params.well_name if params else well_id,
            "phase": state.phase,
            "oil_rate_m3d": round(state.oil_rate_m3d, 3),
            "reservoir_temp_c": round(state.reservoir_temp_c, 2),
            "rod_failure_risk_score": round(risk, 1),
            "active_fault": state.active_fault or None,
            "status_color": color,
            "cycle_number": state.cycle_number,
            "provenance": "SIMULATED_LIVE",
        })
    return {"wells": summaries, "count": len(summaries)}


@router.get("/{well_id}")
async def get_well(well_id: str, request: Request):
    """Return full live state for one well."""
    sim = _sim(request)
    state = sim.get_latest(well_id)
    if state is None:
        raise HTTPException(404, f"Well {well_id!r} not found or not yet ticked")
    return snapshot_to_dict(state)


@router.get("/{well_id}/history")
async def get_well_history(
    well_id: str,
    request: Request,
    n: int = Query(100, ge=1, le=200, description="Number of ticks to return"),
):
    """Return last n ticks for a well (for sparklines and trend charts)."""
    sim = _sim(request)
    history = sim.get_history(well_id, n=n)
    if not history:
        raise HTTPException(404, f"Well {well_id!r} not found or no history yet")
    # Lightweight serialisation — only the fields needed for trend charts
    rows = []
    for s in history:
        rows.append({
            "tick": s.tick,
            "sim_time_days": round(s.sim_time_days, 3),
            "phase": s.phase,
            "reservoir_temp_c": round(s.reservoir_temp_c, 2),
            "oil_rate_m3d": round(s.oil_rate_m3d, 4),
            "oil_viscosity_cp": round(s.oil_viscosity_cp, 1),
            "spm": round(s.spm, 2),
            "pump_efficiency_fraction": round(s.pump_efficiency_fraction, 4),
            "motor_power_kw": round(s.motor_power_kw, 2),
            "rod_float_risk_score": round(s.rod_float_risk_score, 1),
            "sor": round(s.sor, 4),
            "active_fault": s.active_fault or None,
        })
    return {"well_id": well_id, "ticks": rows, "count": len(rows)}


@router.get("/{well_id}/params")
async def get_well_params(well_id: str, request: Request):
    """Return static WellParameters for a well."""
    sim = _sim(request)
    params = sim.get_well_params(well_id)
    if params is None:
        raise HTTPException(404, f"Well {well_id!r} not found")
    return {
        "well_id": params.well_id,
        "well_name": params.well_name,
        "permeability_md": params.permeability_md,
        "porosity": params.porosity,
        "pay_thickness_m": params.pay_thickness_m,
        "depth_m": params.depth_m,
        "initial_temp_c": params.initial_temp_c,
        "initial_pressure_kpa": params.reservoir_pressure_kpa,
        "api_gravity": params.api_gravity,
        "steam_volume_cwe_m3": params.steam_volume_cwe_m3,
        "soak_days": params.soak_days,
        "spm": params.spm,
        "stroke_length_m": params.stroke_length_m,
        "vfd_frequency_hz": params.vfd_frequency_hz,
        "rod_diameter_m": params.rod_diameter_m,
        "rod_string_length_m": params.rod_string_length_m,
        "provenance": "SYNTHETIC_HISTORICAL",
    }
