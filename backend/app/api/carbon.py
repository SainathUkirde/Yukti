"""
backend/app/api/carbon.py
Feature 5 — Carbon & Energy Tracker + Shift Handover API

Endpoints:
  GET  /wells/{id}/carbon   — per-well carbon + energy report
  GET  /field/carbon        — field-level carbon aggregate (replaces stub in field.py)
  GET  /carbon/assumptions  — view current editable assumptions
  PUT  /carbon/assumptions  — update emission factors / prices
  GET  /handover            — generate shift handover summary
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel

from backend.app.services import carbon_service as carbon_svc
from backend.app.services import handover_service as handover_svc
from backend.app.services import fatigue_service as fatigue_svc

logger = logging.getLogger("api.carbon")
router = APIRouter()


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


class AssumptionsUpdate(BaseModel):
    boiler_efficiency: Optional[float] = None
    emission_factor_gas_kg_per_gj: Optional[float] = None
    grid_emission_factor_kg_per_kwh: Optional[float] = None
    steam_density_kg_per_m3: Optional[float] = None
    gas_price_inr_per_gj: Optional[float] = None
    elec_price_inr_per_kwh: Optional[float] = None
    cp_water_kj_per_kg_k: Optional[float] = None
    steam_temp_c: Optional[float] = None
    water_inlet_temp_c: Optional[float] = None
    latent_heat_kj_per_kg: Optional[float] = None


@router.get("/wells/{well_id}/carbon")
async def get_well_carbon(
    well_id: str,
    request: Request,
    period_days: float = Query(1.0, ge=0.1, le=365.0,
                               description="Period over which to compute motor energy [days]"),
):
    """
    Carbon and energy intensity report for a single well.

    All emission factors are LITERATURE_ASSUMPTION.
    NOT validated against real Baghewala field emissions data.
    Edit assumptions via PUT /carbon/assumptions.
    """
    sim = _sim(request)
    state = sim.get_latest(well_id)
    if state is None:
        raise HTTPException(404, f"Well {well_id!r} not found or no data yet")
    params = sim.get_well_params(well_id)
    if params is None:
        raise HTTPException(404, f"Well {well_id!r} params not found")

    return carbon_svc.compute_well_carbon(well_id, state, params, period_days)


@router.get("/field/carbon")
async def get_field_carbon(
    request: Request,
    period_days: float = Query(1.0, ge=0.1, le=365.0,
                               description="Period over which to compute motor energy [days]"),
):
    """
    Field-level carbon aggregate across all active wells.

    PROVENANCE: LITERATURE_ASSUMPTION
    NOT validated against real Baghewala field emissions records.
    """
    sim = _sim(request)
    well_reports = []
    for wid in sim.get_all_wells():
        state = sim.get_latest(wid)
        params = sim.get_well_params(wid)
        if state is None or params is None:
            continue
        try:
            r = carbon_svc.compute_well_carbon(wid, state, params, period_days)
            well_reports.append(r)
        except Exception as e:
            logger.warning(f"Carbon calc failed for {wid}: {e}")

    return carbon_svc.compute_field_carbon(well_reports)


@router.get("/carbon/assumptions")
async def get_assumptions():
    """
    Return current carbon emission factor and price assumptions.
    All defaults are LITERATURE_ASSUMPTION — editable via PUT.
    """
    return carbon_svc.get_assumptions()


@router.put("/carbon/assumptions")
async def update_assumptions(body: AssumptionsUpdate):
    """
    Update carbon emission factors and energy prices in-memory.

    Changes take effect immediately for all subsequent carbon calculations.
    Restarting the process resets to LITERATURE_ASSUMPTION defaults.

    PROVENANCE: USER_UPLOADED (when updated by user)
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No valid fields to update")
    return carbon_svc.update_assumptions(updates)


@router.get("/handover")
async def get_handover(
    request: Request,
    shift_label: str = Query("Day Shift", description="e.g. 'Day Shift', 'Night Shift'"),
    outgoing_operator: str = Query("Operator A"),
    incoming_operator: str = Query("Operator B"),
    period_days: float = Query(1.0, ge=0.1, le=30.0),
):
    """
    Generate a shift handover summary document combining:
    - Live well status (phases, faults, viscosity, pump efficiency)
    - Rod fatigue urgency (critical/high wells)
    - Latest allocation plan (if any)
    - Carbon KPIs
    - Priority action list for incoming shift

    PROVENANCE: DEMO_RESULT
    NOT a real operations handover — all data is from simulated digital twin.
    """
    sim = _sim(request)

    # Gather fatigue reports
    fatigue_reports = []
    for wid in sim.get_all_wells():
        try:
            r = fatigue_svc.compute_fatigue_report(wid)
            fatigue_reports.append(r)
        except Exception:
            pass

    # Get last allocation result (if any)
    allocation_result = None
    try:
        from backend.app.api.field import _alloc_cache
        if _alloc_cache is not None:
            from backend.app.api.field import _result_to_dict
            allocation_result = _result_to_dict(_alloc_cache)
    except Exception:
        pass

    # Compute field carbon report
    carbon_report = None
    try:
        well_reports = []
        for wid in sim.get_all_wells():
            state = sim.get_latest(wid)
            params = sim.get_well_params(wid)
            if state and params:
                r = carbon_svc.compute_well_carbon(wid, state, params, period_days)
                well_reports.append(r)
        carbon_report = carbon_svc.compute_field_carbon(well_reports)
    except Exception as e:
        logger.warning(f"Carbon report for handover failed: {e}")

    return handover_svc.build_handover(
        sim_service=sim,
        fatigue_reports=fatigue_reports,
        allocation_result=allocation_result,
        carbon_report=carbon_report,
        shift_label=shift_label,
        outgoing_operator=outgoing_operator,
        incoming_operator=incoming_operator,
    )
