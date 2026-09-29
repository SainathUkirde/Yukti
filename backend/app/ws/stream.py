"""
backend/app/ws/stream.py
WebSocket endpoint — streams live well state ticks to connected frontend clients.
One WebSocket connection per well; clients subscribe by well_id.
Message format: JSON with provenance tags, ~1.5s interval.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.services.serializer import snapshot_to_dict

logger = logging.getLogger("ws.stream")
router = APIRouter()

# Max time to wait for next tick before sending a keepalive ping
TICK_TIMEOUT_S = 3.0
KEEPALIVE_INTERVAL_S = 10.0


@router.websocket("/ws/stream/{well_id}")
async def well_stream(websocket: WebSocket, well_id: str):
    """
    Stream live well state for a specific well.
    Client connects, receives ticks as JSON until disconnect.
    
    Message types:
      {"type": "tick",      "data": <WellStateSnapshot as dict>}
      {"type": "error",     "message": <str>}
      {"type": "keepalive", "tick": <int>}
    """
    await websocket.accept()
    logger.info(f"WS client connected: {well_id}")

    # Access app state via scope (standard FastAPI WebSocket pattern)
    _app = websocket.scope.get("app")
    sim = getattr(getattr(_app, "state", None), "sim_service", None)
    if sim is None:
        await websocket.send_json({"type": "error", "message": "Simulation not ready"})
        await websocket.close(code=1011)
        return

    # Check well exists
    if well_id not in sim.get_all_wells():
        await websocket.send_json({"type": "error", "message": f"Well {well_id!r} not found"})
        await websocket.close(code=1008)
        return

    # Create a per-client asyncio queue; register with simulation service
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    sim.subscribe(well_id, queue)

    # Send current state immediately on connect
    current = sim.get_latest(well_id)
    if current:
        await websocket.send_json({
            "type": "tick",
            "data": snapshot_to_dict(current),
        })

    keepalive_counter = 0
    try:
        while True:
            try:
                # Wait for next tick from the simulation loop
                state = await asyncio.wait_for(queue.get(), timeout=TICK_TIMEOUT_S)
                msg = {
                    "type": "tick",
                    "data": snapshot_to_dict(state),
                }
                await websocket.send_json(msg)
                keepalive_counter = 0

            except asyncio.TimeoutError:
                # Send keepalive to prevent proxy timeouts
                keepalive_counter += 1
                state = sim.get_latest(well_id)
                tick = state.tick if state else -1
                await websocket.send_json({
                    "type": "keepalive",
                    "tick": tick,
                    "well_id": well_id,
                })

    except WebSocketDisconnect:
        logger.info(f"WS client disconnected: {well_id}")
    except Exception as e:
        logger.error(f"WS error for {well_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        sim.unsubscribe(well_id, queue)


@router.websocket("/ws/fleet")
async def fleet_stream(websocket: WebSocket):
    """
    Stream a lightweight summary of all wells (for the multi-well overview grid).
    Pushes one update per second with [well_id, phase, oil_rate, risk_score, fault].
    """
    await websocket.accept()
    logger.info("Fleet WS client connected")

    _app = websocket.scope.get("app")
    sim = getattr(getattr(_app, "state", None), "sim_service", None)
    if sim is None:
        await websocket.send_json({"type": "error", "message": "Simulation not ready"})
        await websocket.close(code=1011)
        return

    try:
        while True:
            summaries = []
            for wid in sim.get_all_wells():
                state = sim.get_latest(wid)
                if state is None:
                    continue
                risk = state.rod_float_risk_score
                summaries.append({
                    "well_id": wid,
                    "phase": state.phase,
                    "oil_rate_m3d": round(state.oil_rate_m3d, 3),
                    "reservoir_temp_c": round(state.reservoir_temp_c, 2),
                    "risk_score": round(risk, 1),
                    "active_fault": state.active_fault or None,
                    "status_color": "red" if risk >= 70 else ("amber" if risk >= 40 else "green"),
                    "cycle_number": state.cycle_number,
                    "tick": state.tick,
                })
            await websocket.send_json({
                "type": "fleet",
                "wells": summaries,
                "count": len(summaries),
            })
            await asyncio.sleep(1.5)

    except WebSocketDisconnect:
        logger.info("Fleet WS client disconnected")
    except Exception as e:
        logger.error(f"Fleet WS error: {e}")
