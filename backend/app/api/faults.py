"""
backend/app/api/faults.py
Fault injection / resolution endpoints for demo and testing.
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("api.faults")
router = APIRouter()

VALID_FAULTS = {"rod_floating", "pump_off", "gas_interference", "fluid_pound", "pump_unsetting"}


class FaultRequest(BaseModel):
    well_id: str
    fault_type: str
    ramp_ticks: int = 30


class FaultResolveRequest(BaseModel):
    well_id: str
    fault_type: Optional[str] = None


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


@router.post("/inject")
async def inject_fault(body: FaultRequest, request: Request):
    """Inject a fault into a running well simulation."""
    if body.fault_type not in VALID_FAULTS:
        raise HTTPException(400, f"Unknown fault type {body.fault_type!r}. "
                                 f"Valid: {sorted(VALID_FAULTS)}")
    sim = _sim(request)
    ok = sim.inject_fault(body.well_id, body.fault_type, ramp_ticks=body.ramp_ticks)
    if not ok:
        raise HTTPException(404, f"Well {body.well_id!r} not found")
    logger.info(f"Injected {body.fault_type} → {body.well_id}")
    return {
        "status": "injected",
        "well_id": body.well_id,
        "fault_type": body.fault_type,
        "ramp_ticks": body.ramp_ticks,
        "provenance": "DEMO_RESULT",
    }


@router.post("/resolve")
async def resolve_fault(body: FaultResolveRequest, request: Request):
    """Resolve an active fault on a well."""
    sim = _sim(request)
    fault_type = body.fault_type or "all"
    if fault_type == "all":
        for ft in VALID_FAULTS:
            sim.resolve_fault(body.well_id, ft)
        resolved = list(VALID_FAULTS)
    else:
        ok = sim.resolve_fault(body.well_id, fault_type)
        if not ok:
            raise HTTPException(404, f"Well {body.well_id!r} not found")
        resolved = [fault_type]
    return {
        "status": "resolved",
        "well_id": body.well_id,
        "resolved_faults": resolved,
        "provenance": "DEMO_RESULT",
    }


@router.get("/types")
async def list_fault_types():
    """List all injectable fault types with descriptions."""
    return {
        "fault_types": [
            {"id": "rod_floating",     "description": "Rod string floats on downstroke due to high viscosity (N_rf > 1)"},
            {"id": "pump_off",         "description": "Fluid level drops below pump intake — fluid pound imminent"},
            {"id": "gas_interference", "description": "Gas breaks out above pump, reduces fillage"},
            {"id": "fluid_pound",      "description": "Pump hits fluid violently — impact loading on rod"},
            {"id": "pump_unsetting",   "description": "Pump anchor releases, pump moves off-bottom"},
        ]
    }
