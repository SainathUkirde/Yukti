"""
backend/app/api/assistant.py
AI Assistant endpoint — local rule-based, no external LLM.
PROVENANCE: DEMO_RESULT
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("api.assistant")
router = APIRouter()


class AssistantRequest(BaseModel):
    query: str
    well_id: Optional[str] = None
    include_well_context: bool = True


@router.post("/")
async def ask(body: AssistantRequest, request: Request):
    """
    Answer an engineering question about CSS, SRP, or digital twin concepts.
    Uses local rule-based knowledge base — no external LLM required.
    """
    if not body.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    well_state = None
    if body.well_id and body.include_well_context:
        sim = getattr(request.app.state, "sim_service", None)
        if sim:
            state = sim.get_latest(body.well_id)
            if state:
                from backend.app.services.serializer import snapshot_to_dict
                well_state = snapshot_to_dict(state)

    from backend.app.services.assistant_service import answer
    result = answer(body.query, well_state=well_state)
    result["query"] = body.query
    result["well_id"] = body.well_id
    return result


@router.get("/topics")
async def list_topics():
    """List topics the assistant can answer."""
    return {
        "topics": [
            "CSS (Cyclic Steam Stimulation) — phases, parameters, SOR",
            "SRP (Sucker Rod Pump) — SPM, stroke length, VFD, efficiency",
            "Rod Floating — N_rf model, causes, mitigation",
            "Viscosity — Andrade equation, temperature dependence",
            "Pump Efficiency — fillage, pump-off, gas interference",
            "Goodman Criterion — rod fatigue, failure risk",
            "IPR (Inflow Performance) — Vogel model, productivity index",
            "Heated Zone — Marx-Langenheim model, radius, cooling",
            "Digital Twin — provenance system, SYNTHETIC vs SIMULATED data",
            "Joint Optimizer — Optuna TPE, decision variables, constraints",
        ]
    }
