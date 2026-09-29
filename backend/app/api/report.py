"""
backend/app/api/report.py
PDF report download endpoint.
"""
import logging
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger("api.report")
router = APIRouter()


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


@router.get("/{well_id}")
async def download_report(well_id: str, request: Request):
    """Generate and download a PDF well performance report."""
    sim = _sim(request)
    state = sim.get_latest(well_id)
    if state is None:
        raise HTTPException(404, f"Well {well_id!r} not found")

    from backend.app.services.serializer import snapshot_to_dict
    from backend.app.services.report_service import generate_well_report

    # Check optimizer cache
    try:
        from backend.app.api.optimize import _opt_cache
        opt_result = _opt_cache.get(well_id)
    except Exception:
        opt_result = None

    state_dict = snapshot_to_dict(state)
    try:
        pdf_bytes = generate_well_report(state_dict, opt_result=opt_result)
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(500, f"Report generation failed: {e}")

    filename = f"baghewala_{well_id}_report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{well_id}/json")
async def get_report_json(well_id: str, request: Request):
    """Return report data as JSON (for frontend rendering)."""
    sim = _sim(request)
    state = sim.get_latest(well_id)
    if state is None:
        raise HTTPException(404, f"Well {well_id!r} not found")

    from backend.app.services.serializer import snapshot_to_dict
    try:
        from backend.app.api.optimize import _opt_cache
        opt_result = _opt_cache.get(well_id)
    except Exception:
        opt_result = None

    return {
        "well_state": snapshot_to_dict(state),
        "optimizer_recommendation": opt_result,
        "provenance": "SIMULATED_LIVE",
    }
