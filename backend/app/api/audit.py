"""
backend/app/api/audit.py
Feature 4 — Trust Layer API

Endpoints:
  GET  /audit                          — list audit log entries
  GET  /audit/verify                   — verify hash chain integrity
  GET  /audit/status                   — current role, safe mode, pending count
  POST /audit/role                     — switch demo role (Operator/Engineer/Viewer)
  POST /audit/safe-mode                — toggle safe-mode on/off
  POST /recommendations/{id}/propose   — register rec in approval flow
  POST /recommendations/{id}/approve   — approve (Engineer only)
  POST /recommendations/{id}/reject    — reject any state
  POST /recommendations/{id}/apply     — apply approved rec to simulator
  GET  /recommendations/{id}/state     — get approval state
  GET  /audit/recommendations          — list all recommendation states
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel

from backend.app.services import audit_service as svc

logger = logging.getLogger("api.audit")
router = APIRouter()


# ── Request models ────────────────────────────────────────────────────────────

class ProposeRequest(BaseModel):
    well_id: str
    recommendation: dict
    confidence_low: float = 0.0
    confidence_high: float = 0.0
    constraint_result: str = "SAFE"


class ApproveRequest(BaseModel):
    approver: str = "Engineer"
    reason: str = ""


class RejectRequest(BaseModel):
    approver: str = "Engineer"
    reason: str = ""


class ApplyRequest(BaseModel):
    approver: str = "Operator"


class RoleRequest(BaseModel):
    role: str   # Operator | Engineer | Viewer


class SafeModeRequest(BaseModel):
    active: bool


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit_log(
    well_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Return audit log entries, optionally filtered."""
    entries = svc.get_audit_log(well_id=well_id, action=action, limit=limit)
    return {
        "entries": entries,
        "count": len(entries),
        "total": len(svc._audit_log),
        "provenance": "DEMO_RESULT",
    }


@router.get("/audit/verify")
async def verify_chain():
    """Verify the SHA-256 hash chain. Returns valid=True if untampered."""
    result = svc.verify_chain()
    return {**result, "provenance": "DEMO_RESULT"}


@router.get("/audit/status")
async def audit_status():
    """Return current role, safe-mode state, pending recommendation count."""
    return svc.get_status()


@router.post("/audit/role")
async def set_role(body: RoleRequest):
    """Switch the demo role. DEMO ONLY — no real authentication."""
    try:
        return svc.set_role(body.role)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/audit/safe-mode")
async def set_safe_mode(body: SafeModeRequest):
    """Toggle safe-mode. In safe-mode, step sizes are clamped and UNSAFE recs are blocked."""
    return svc.set_safe_mode(body.active)


# ── Recommendation approval flow ──────────────────────────────────────────────

@router.post("/recommendations/{rec_id}/propose")
async def propose(rec_id: str, body: ProposeRequest):
    """Register a recommendation in the approval flow (state=proposed)."""
    rec = {**body.recommendation, "id": rec_id}
    state = svc.propose_recommendation(
        well_id=body.well_id,
        recommendation=rec,
        confidence_low=body.confidence_low,
        confidence_high=body.confidence_high,
        constraint_result=body.constraint_result,
    )
    return state


@router.post("/recommendations/{rec_id}/approve")
async def approve(rec_id: str, body: ApproveRequest):
    """Approve a proposed recommendation (Engineer role required)."""
    try:
        return svc.approve_recommendation(rec_id, approver=body.approver, reason=body.reason)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/recommendations/{rec_id}/reject")
async def reject(rec_id: str, body: RejectRequest):
    """Reject a recommendation."""
    try:
        return svc.reject_recommendation(rec_id, approver=body.approver, reason=body.reason)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/recommendations/{rec_id}/apply")
async def apply(rec_id: str, body: ApplyRequest, request: Request):
    """Apply an approved recommendation to the live simulator."""
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    try:
        return svc.apply_recommendation(rec_id, sim_service=sim, approver=body.approver)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/recommendations/{rec_id}/state")
async def get_rec_state(rec_id: str):
    """Get the approval state of a recommendation."""
    state = svc.get_recommendation_state(rec_id)
    if state is None:
        raise HTTPException(404, f"Recommendation {rec_id!r} not in approval flow")
    return state


@router.get("/audit/recommendations")
async def list_rec_states(
    well_id: Optional[str] = Query(None),
):
    """List all recommendation states."""
    return {
        "states": svc.list_recommendation_states(well_id=well_id),
        "provenance": "DEMO_RESULT",
    }
