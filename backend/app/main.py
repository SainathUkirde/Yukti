"""
backend/app/main.py
FastAPI application entry point.

Starts the live simulation engine on startup and wires all routers.
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
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
    n_wells = int(os.getenv("NUM_WELLS", "5"))
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
cors_origins_env = os.getenv("CORS_ORIGINS", "*")
if cors_origins_env == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── Routers (mounted both at root and /api for full compatibility) ─────────────
api_router = APIRouter(prefix="/api")

for r in [
    (health.router, {}),
    (wells.router, {"prefix": "/wells"}),
    (cycles.router, {"prefix": "/cycles"}),
    (predict.router, {"prefix": "/predict"}),
    (optimize.router, {"prefix": "/optimize"}),
    (whatif.router, {"prefix": "/whatif"}),
    (recommendations.router, {"prefix": "/recommendations"}),
    (faults.router, {"prefix": "/faults"}),
    (report.router, {"prefix": "/report"}),
    (assistant.router, {"prefix": "/assistant"}),
    (audit.router, {}),
    (fatigue.router, {}),
    (field.router, {}),
    (data.router, {}),
    (carbon.router, {}),
]:
    router_obj, kwargs = r
    app.include_router(router_obj, **kwargs)
    api_router.include_router(router_obj, **kwargs)

app.include_router(api_router)
app.include_router(ws_router, tags=["WebSocket"])

# ── Static Files (Frontend SPA) ───────────────────────────────────────────────
frontend_dist = os.path.join(ROOT, "frontend", "dist")
if os.path.isdir(frontend_dist):
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return {"message": "YUKTI API running"}

