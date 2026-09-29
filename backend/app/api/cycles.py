"""
backend/app/api/cycles.py
CSS cycle records — GET history, POST to log a completed cycle.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("api.cycles")
router = APIRouter()

# In-memory cycle log (keyed by well_id) — persisted to SQLite in full deploy
_cycle_log: dict[str, list[dict]] = {}


class CycleRecord(BaseModel):
    well_id: str
    cycle_number: int
    steam_volume_cwe_m3: float = Field(..., gt=0)
    injection_pressure_kpa: float = Field(..., gt=0)
    soak_days: float = Field(..., gt=0)
    peak_temp_c: float
    heated_zone_radius_m: float
    cum_oil_m3: float
    cum_steam_m3: float
    sor: float
    duration_days: float
    notes: Optional[str] = None


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


@router.get("/")
async def list_cycles(request: Request, well_id: Optional[str] = None):
    """Return all CSS cycle records, optionally filtered by well."""
    sim = _sim(request)
    # Auto-build cycle records from live simulation state
    cycles = []
    wells = [well_id] if well_id else sim.get_all_wells()
    for wid in wells:
        records = _cycle_log.get(wid, [])
        # If no manual records, synthesise from history
        if not records:
            history = sim.get_history(wid, n=200)
            current_cycle = None
            for snap in history:
                if snap.cycle_number != current_cycle:
                    current_cycle = snap.cycle_number
                    cycles.append({
                        "well_id": wid,
                        "cycle_number": snap.cycle_number,
                        "phase": snap.phase,
                        "steam_volume_cwe_m3": snap.config.steam_volume_cwe_m3,
                        "soak_days": snap.config.soak_days,
                        "peak_temp_c": round(snap.T_peak_c, 2),
                        "cum_oil_m3": round(snap.cum_oil_m3, 2),
                        "sor": round(snap.sor, 3),
                        "provenance": "SIMULATED_LIVE",
                    })
        else:
            cycles.extend(records)
    return {"cycles": cycles, "count": len(cycles)}


@router.get("/{well_id}/latest")
async def get_latest_cycle(well_id: str, request: Request):
    """Return stats for the current active cycle."""
    sim = _sim(request)
    state = sim.get_latest(well_id)
    if state is None:
        raise HTTPException(404, f"Well {well_id!r} not found")
    return {
        "well_id": well_id,
        "cycle_number": state.cycle_number,
        "phase": state.phase,
        "time_in_phase_days": round(state.time_in_phase_days, 2),
        "T_peak_c": round(state.T_peak_c, 2),
        "reservoir_temp_c": round(state.reservoir_temp_c, 2),
        "heated_zone_radius_m": round(state.heated_zone_radius_m, 2),
        "cum_oil_m3": round(state.cum_oil_m3, 2),
        "cum_water_m3": round(state.cum_water_m3, 2),
        "sor": round(state.sor, 4),
        "steam_volume_cwe_m3": state.config.steam_volume_cwe_m3,
        "soak_days": state.config.soak_days,
        "provenance": "SIMULATED_LIVE",
    }


@router.post("/")
async def log_cycle(record: CycleRecord):
    """Manually log a completed CSS cycle record."""
    entry = record.model_dump()
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()
    entry["provenance"] = "SYNTHETIC_HISTORICAL"
    _cycle_log.setdefault(record.well_id, []).append(entry)
    logger.info(f"Logged cycle {record.cycle_number} for {record.well_id}")
    return {"status": "logged", "entry": entry}
