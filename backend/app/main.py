"""
backend/app/main.py
FastAPI application entry point.

Starts the live simulation engine on startup and wires all routers.
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Make sure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backend.app.services.simulation_service import SimulationService
from backend.app.api import wells, cycles, predict, optimize, whatif, recommendations, faults, report, assistant, health
from backend.app.api import audit, fatigue, field, data, carbon
from backend.app.ws.stream import router as ws_router
from backend.app.db.database import init_db

# ── Logging ──────────────────────────────────────────────────────────────────
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("digital_twin")

# ── Global simulation service (shared across requests) ────────────────────────
sim_service: SimulationService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize DB and start simulator. Shutdown: stop simulator."""
    global sim_service
    logger.info("Initializing database...")
    await init_db()

    logger.info("Starting simulation service...")
    n_wells = int(os.getenv("NUM_WELLS", "10"))
    time_accel = int(os.getenv("TIME_ACCELERATION", "10"))
    sim_service = SimulationService(n_wells=n_wells, time_acceleration=time_accel)
    sim_service.start()
    app.state.sim_service = sim_service

    logger.info(f"Digital Twin ready: {n_wells} wells, {time_accel}x time acceleration")
    yield

    logger.info("Shutting down simulation service...")
    if sim_service:
        sim_service.stop()


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="YUKTI API",
    description=(
        "YUKTI — AI-Powered Well-to-Surface Digital Twin for Optimized CSS & SRP Operations. "
        "All data is SYNTHETIC_HISTORICAL — physics-based simulator. "
        "NOT validated on real Baghewala field operations."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router,           tags=["Health"])
app.include_router(wells.router,            prefix="/wells",           tags=["Wells"])
app.include_router(cycles.router,           prefix="/cycles",          tags=["CSS Cycles"])
app.include_router(predict.router,          prefix="/predict",         tags=["Predictions"])
app.include_router(optimize.router,         prefix="/optimize",        tags=["Optimization"])
app.include_router(whatif.router,           prefix="/whatif",          tags=["What-If"])
app.include_router(recommendations.router,  prefix="/recommendations", tags=["Recommendations"])
app.include_router(faults.router,           prefix="/faults",          tags=["Faults"])
app.include_router(report.router,           prefix="/report",          tags=["Reports"])
app.include_router(assistant.router,        prefix="/assistant",       tags=["AI Assistant"])
app.include_router(audit.router,                                       tags=["Trust Layer"])
app.include_router(fatigue.router,                                     tags=["Rod Fatigue"])
app.include_router(field.router,                                       tags=["Field Planner"])
app.include_router(data.router,                                        tags=["Calibration"])
app.include_router(carbon.router,                                      tags=["Carbon & Handover"])
app.include_router(ws_router,                                          tags=["WebSocket"])
