"""
backend/app/services/simulation_service.py
Background simulation service — runs all well simulators in a thread,
publishes state ticks to in-memory queues consumed by WebSocket clients.
"""
import threading
import time
import asyncio
import logging
from collections import defaultdict, deque
from typing import Optional
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, ROOT)

from simulator.config import make_well_fleet, WellParameters
from simulator.well_system import WellSystem, WellStateSnapshot

logger = logging.getLogger("sim_service")

TICK_INTERVAL_S = float(os.getenv("TICK_INTERVAL_S", "1.5"))


class SimulationService:
    """
    Runs all WellSystem simulators in a background thread.
    Maintains a per-well ring buffer of recent ticks.
    WebSocket clients subscribe to per-well queues.
    """

    def __init__(self, n_wells: int = 10, time_acceleration: int = 10, seed: int = 42):
        self.n_wells = n_wells
        self.time_acceleration = time_acceleration
        self._fleet: list[WellSystem] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Per-well ring buffer of last 200 ticks
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))

        # Per-well latest snapshot
        self._latest: dict[str, WellStateSnapshot] = {}

        # WebSocket subscriber queues: well_id → list of asyncio.Queue
        self._subscribers: dict[str, list] = defaultdict(list)

        self._init_wells(n_wells, time_acceleration, seed)

    def _init_wells(self, n_wells: int, time_acceleration: int, seed: int):
        """Initialize the well fleet and start each well in CSS cycle 1."""
        fleet_params = make_well_fleet(n_wells, seed)
        for p in fleet_params:
            ws = WellSystem(p, time_acceleration=time_acceleration)
            ws.start_cycle(cycle_number=1)
            self._fleet.append(ws)
        logger.info(f"Initialized {len(self._fleet)} wells")

    def start(self):
        """Start the background simulation thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="SimLoop")
        self._thread.start()
        logger.info("Simulation loop started")

    def stop(self):
        """Stop the simulation loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_loop(self):
        """Main simulation tick loop — runs in background thread."""
        # Import fatigue service lazily to avoid circular import
        try:
            from backend.app.services import fatigue_service as _fatigue
        except Exception:
            _fatigue = None  # graceful degradation

        while self._running:
            t0 = time.monotonic()
            for ws in self._fleet:
                try:
                    state = ws.tick()
                    wid = ws.params.well_id
                    with self._lock:
                        self._latest[wid] = state
                        self._history[wid].append(state)
                    # Auto-start next cycle when production ends
                    if state.phase == "idle" and state.time_in_phase_days > 0.5:
                        ws.start_cycle()
                    # Accumulate rod fatigue damage (Feature 2)
                    if _fatigue is not None and state.phase == "production":
                        try:
                            _fatigue.update_fatigue(
                                well_id=wid,
                                peak_load_kn=state.peak_load_kn,
                                min_load_kn=state.min_load_kn,
                                spm=state.spm,
                                dt_days=ws._dt_days,
                                active_fault=state.active_fault,
                            )
                        except Exception as fe:
                            logger.debug(f"Fatigue update skipped for {wid}: {fe}")
                    # Publish to WebSocket subscribers (schedule on event loop)
                    self._publish(wid, state)
                except Exception as e:
                    logger.error(f"Sim error on {ws.params.well_id}: {e}")

            elapsed = time.monotonic() - t0
            sleep_time = max(0.0, TICK_INTERVAL_S - elapsed)
            time.sleep(sleep_time)

    def _publish(self, well_id: str, state: WellStateSnapshot):
        """Push snapshot to all WebSocket queues for this well."""
        subs = self._subscribers.get(well_id, [])
        for q in list(subs):
            try:
                q.put_nowait(state)
            except Exception:
                pass  # queue full or closed — subscriber will be cleaned up

    def subscribe(self, well_id: str, queue) -> None:
        """Register a WebSocket client queue for a well."""
        self._subscribers[well_id].append(queue)

    def unsubscribe(self, well_id: str, queue) -> None:
        """Remove a WebSocket client queue."""
        try:
            self._subscribers[well_id].remove(queue)
        except ValueError:
            pass

    def get_latest(self, well_id: str) -> Optional[WellStateSnapshot]:
        """Return the most recent snapshot for a well."""
        return self._latest.get(well_id)

    def get_history(self, well_id: str, n: int = 100) -> list[WellStateSnapshot]:
        """Return last n snapshots for a well."""
        with self._lock:
            buf = self._history.get(well_id, deque())
            return list(buf)[-n:]

    def get_all_wells(self) -> list[str]:
        """Return all well IDs."""
        return [ws.params.well_id for ws in self._fleet]

    def get_well_params(self, well_id: str) -> Optional[WellParameters]:
        """Return WellParameters for a well."""
        for ws in self._fleet:
            if ws.params.well_id == well_id:
                return ws.params
        return None

    def inject_fault(self, well_id: str, fault_type: str, ramp_ticks: int = 30) -> bool:
        """Inject a fault into a well. Returns True if well found."""
        for ws in self._fleet:
            if ws.params.well_id == well_id:
                ws.inject_fault(fault_type, ramp_ticks=ramp_ticks)
                return True
        return False

    def resolve_fault(self, well_id: str, fault_type: str) -> bool:
        """Resolve a fault on a well."""
        for ws in self._fleet:
            if ws.params.well_id == well_id:
                ws.resolve_fault(fault_type)
                return True
        return False

    def apply_config(self, well_id: str, **kwargs) -> bool:
        """Apply optimizer recommendation to a well."""
        for ws in self._fleet:
            if ws.params.well_id == well_id:
                ws.apply_config(**kwargs)
                return True
        return False
