"""
simulator/srp/faults.py
Fault injection API for the SRP simulator.

Supports injecting faults at a chosen simulation time:
  - rod_floating
  - pump_off
  - gas_interference
  - fluid_pound
  - pump_unsetting

Each fault has:
  - A trigger condition (time-based or state-based)
  - A severity that ramps up from 0 to 1 over a configurable period
  - A card distortion signature (delegated to wave_equation._apply_fault)
  - An auto-recovery option (fault clears after N strokes if SPM is reduced)

References:
  [1] Takacs, G. (2015) Sucker-Rod Pumping Handbook, Ch. 5-6.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


VALID_FAULTS = {
    "rod_floating",
    "pump_off",
    "gas_interference",
    "fluid_pound",
    "pump_unsetting",
}


@dataclass
class ActiveFault:
    """
    An active fault injection on a well.

    severity : 0.0 → 1.0, ramps over ramp_ticks ticks
    auto_recover : if True, fault clears when the triggering condition resolves
    """
    fault_type: str
    inject_tick: int           # simulation tick at which fault was injected
    ramp_ticks: int = 30       # ticks to ramp severity from 0 to 1
    auto_recover: bool = True  # recover when condition resolves
    resolved: bool = False
    resolve_tick: Optional[int] = None

    def severity_at(self, current_tick: int) -> float:
        """Linearly ramp severity from 0 → 1 over ramp_ticks."""
        if self.resolved:
            return 0.0
        elapsed = current_tick - self.inject_tick
        return float(np.clip(elapsed / max(self.ramp_ticks, 1), 0.0, 1.0))

    def resolve(self, current_tick: int) -> None:
        """Mark fault as resolved."""
        self.resolved = True
        self.resolve_tick = current_tick


class FaultInjector:
    """
    Manages active fault injections for one well.
    At most one fault of each type is active at a time.
    """

    def __init__(self) -> None:
        self._faults: dict[str, ActiveFault] = {}

    def inject(
        self,
        fault_type: str,
        current_tick: int,
        ramp_ticks: int = 30,
        auto_recover: bool = True,
    ) -> None:
        """
        Inject a fault starting at current_tick.

        Parameters
        ----------
        fault_type    : str   One of VALID_FAULTS
        current_tick  : int   Current simulation tick
        ramp_ticks    : int   Ticks to reach full severity
        auto_recover  : bool  Clear fault when condition resolves
        """
        if fault_type not in VALID_FAULTS:
            raise ValueError(f"Unknown fault type: {fault_type!r}. "
                             f"Valid: {sorted(VALID_FAULTS)}")
        self._faults[fault_type] = ActiveFault(
            fault_type=fault_type,
            inject_tick=current_tick,
            ramp_ticks=ramp_ticks,
            auto_recover=auto_recover,
        )

    def resolve(self, fault_type: str, current_tick: int) -> None:
        """Manually resolve a fault."""
        if fault_type in self._faults:
            self._faults[fault_type].resolve(current_tick)

    def active_fault(self, current_tick: int) -> tuple[Optional[str], float]:
        """
        Return the most severe active fault and its severity.
        Returns (None, 0.0) if no faults are active.
        """
        best_type: Optional[str] = None
        best_sev = 0.0
        for ft, af in self._faults.items():
            if af.resolved:
                continue
            sev = af.severity_at(current_tick)
            if sev > best_sev:
                best_sev = sev
                best_type = ft
        return best_type, best_sev

    def auto_resolve_rod_float(
        self,
        current_tick: int,
        rf_ratio: float,
        threshold: float = 0.8,
    ) -> None:
        """
        Auto-resolve rod_floating fault when RF ratio drops below threshold.
        Called each tick by WellSystem when auto_recover=True.
        """
        if "rod_floating" in self._faults:
            af = self._faults["rod_floating"]
            if af.auto_recover and not af.resolved and rf_ratio < threshold:
                af.resolve(current_tick)

    def all_active(self, current_tick: int) -> list[str]:
        """Return list of currently active (non-resolved) fault names."""
        return [
            ft for ft, af in self._faults.items()
            if not af.resolved and af.severity_at(current_tick) > 0
        ]

    def clear_all(self) -> None:
        """Clear all faults (e.g. on new CSS cycle start)."""
        self._faults.clear()
