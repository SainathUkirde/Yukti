"""
backend/app/api/fatigue.py
Feature 2 — Rod Fatigue & Remaining-Life Tracker API

Endpoints:
  GET /wells/{id}/fatigue      — full fatigue report for one well
  GET /field/fatigue           — fleet-level fatigue, sorted by urgency
  POST /wells/{id}/fatigue/reset  — simulate rod replacement (workover)
"""
import logging
from fastapi import APIRouter, HTTPException, Request

from backend.app.services import fatigue_service as svc

logger = logging.getLogger("api.fatigue")
router = APIRouter()


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


@router.get("/wells/{well_id}/fatigue")
async def get_fatigue(well_id: str, request: Request):
    """
    Return rod fatigue report for a single well.
    Damage accumulates from production-phase ticks via Miner's rule.
    PROVENANCE: SIMULATED_LIVE (damage) + LITERATURE_ASSUMPTION (life estimates)
    """
    sim = _sim(request)
    if well_id not in sim.get_all_wells():
        raise HTTPException(404, f"Well {well_id!r} not found")

    # Ensure state exists (creates default if well hasn't produced yet)
    report = svc.compute_fatigue_report(well_id)

    # Attach current live KPIs for context
    state = sim.get_latest(well_id)
    if state:
        report["current_goodman_ratio"] = round(state.goodman_ratio, 4)
        report["current_spm"] = round(state.spm, 2)
        report["current_viscosity_cp"] = round(state.oil_viscosity_cp, 1)
        report["current_peak_load_kn"] = round(state.peak_load_kn, 3)
        report["current_active_fault"] = state.active_fault

    return report


@router.get("/field/fatigue")
async def get_field_fatigue(request: Request):
    """
    Return fatigue reports for all wells, sorted by urgency (critical first).
    Use for fleet-level workover planning.
    PROVENANCE: SIMULATED_LIVE + LITERATURE_ASSUMPTION
    """
    sim = _sim(request)
    reports = []
    for well_id in sim.get_all_wells():
        r = svc.compute_fatigue_report(well_id)
        state = sim.get_latest(well_id)
        if state:
            r["current_goodman_ratio"] = round(state.goodman_ratio, 4)
            r["phase"] = state.phase
        reports.append(r)

    # Sort: critical → high → medium → low
    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    reports.sort(key=lambda r: urgency_order.get(r["urgency"], 9))

    return {
        "wells": reports,
        "count": len(reports),
        "critical_count": sum(1 for r in reports if r["urgency"] == "critical"),
        "high_count": sum(1 for r in reports if r["urgency"] == "high"),
        "provenance": "SIMULATED_LIVE",
    }


@router.post("/wells/{well_id}/fatigue/reset")
async def reset_fatigue(well_id: str, request: Request):
    """
    Reset cumulative fatigue damage — simulates a rod replacement / workover.
    Appends an audit entry.
    """
    sim = _sim(request)
    if well_id not in sim.get_all_wells():
        raise HTTPException(404, f"Well {well_id!r} not found")

    result = svc.reset_fatigue(well_id)

    # Audit the workover event
    try:
        from backend.app.services import audit_service as audit_svc
        audit_svc.append_audit(
            well_id=well_id,
            recommendation_id=f"workover-{well_id}",
            action="workover_applied",
            before_values={},
            after_values={"cumulative_damage": 0.0},
            constraint_result="SAFE",
            approver="system",
            reason="Rod replacement / workover — fatigue reset",
        )
    except Exception:
        pass

    return result
