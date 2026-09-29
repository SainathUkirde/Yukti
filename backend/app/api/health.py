"""
backend/app/api/health.py
Health check endpoints — used by Docker, Kubernetes probes, and frontend offline detection.
"""
import time
import os
from fastapi import APIRouter, Request

router = APIRouter()
_start_time = time.time()


@router.get("/health")
async def health(request: Request):
    """Basic liveness probe."""
    sim = getattr(request.app.state, "sim_service", None)
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _start_time, 1),
        "wells_active": len(sim.get_all_wells()) if sim else 0,
        "version": "1.0.0",
        "env": os.getenv("ENV", "development"),
    }


@router.get("/health/ready")
async def readiness(request: Request):
    """Readiness probe — checks if simulation is running."""
    sim = getattr(request.app.state, "sim_service", None)
    ready = sim is not None and sim._running
    return {"ready": ready}


@router.get("/offline-check")
async def offline_check():
    """Frontend uses this to detect if backend is reachable."""
    return {"online": True, "timestamp": time.time()}
