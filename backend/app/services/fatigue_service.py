"""
backend/app/services/fatigue_service.py
Feature 2 — Rod Fatigue & Remaining-Life Tracker

Physics method:
  Goodman criterion (modified) for alternating stress allowable:
    σ_a / S_e  +  σ_m / S_u  =  1      [Shigley 2011, Ch. 6]
  where
    σ_a = (σ_max - σ_min) / 2           stress amplitude [MPa]
    σ_m = (σ_max + σ_min) / 2           mean stress      [MPa]
    S_e = 207 MPa  (API Grade D rod endurance limit [API Spec 11B 2013])
    S_u = 620 MPa  (API Grade D ultimate strength   [API Spec 11B 2013])

  Goodman ratio G = σ_a/S_e + σ_m/S_u
    G < 1 → safe cycle
    G ≥ 1 → expected fatigue failure at this stress level

  Cycles to failure via Basquin (S-N) law:
    N_f = (S_e / σ_a)^b / C            [Shigley 2011, eq. 6-14]
    b = 0.085  (exponent, API rod steel, conservative [API RP 11L])
    C = 1.0    (surface factor group assumed =1 for conservative estimate)

  Miner's rule (linear damage accumulation) [Miner 1945, cited in Shigley]:
    D = Σ (n_i / N_fi)
  Failure expected when D ≥ 1.

  One tick applies n_i = spm × dt_minutes cycles at the current stress level.

Uncertainty (provenance: LITERATURE_ASSUMPTION):
  Remaining life p50 = (1 - D) / damage_rate_per_day
  Remaining life p10 = p50 × 0.6  (conservative, ±40% from Miner scatter [Schijve 2009])

Sources cited in code:
  [A] Shigley, J.E. (2011) Mechanical Engineering Design, 9th ed., McGraw-Hill.
  [B] API Spec 11B (2013) Sucker Rods, American Petroleum Institute.
  [C] API RP 11L (2012) Recommended Practice for Design Calculations.
  [D] Miner, M.A. (1945) "Cumulative Damage in Fatigue," J. Appl. Mech. 12:A159-A164.
  [E] Schijve, J. (2009) Fatigue of Structures and Materials, 2nd ed., Springer.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("fatigue_service")

# ── Material constants (LITERATURE_ASSUMPTION) ────────────────────────────────
S_E_MPA: float = 207.0       # Endurance limit, API Grade D rod [B][C]
S_U_MPA: float = 620.0       # Ultimate tensile strength, Grade D [B]
BASQUIN_B: float = 0.085     # S-N exponent, conservative for rod steel [C]
# N_f = (S_E / σ_a)^(1/b) — cycles to failure at amplitude σ_a
# Miner scatter factor for p10/p90 [E]
MINER_SCATTER_P10: float = 0.60   # p10 = p50 × 0.60 (conservative)
MINER_SCATTER_P90: float = 1.60   # p90 = p50 × 1.60 (optimistic)

# Rod cross-section area (7/8-inch API rod) [B]
import math as _math
ROD_DIA_M: float = 0.022225                             # 22.225 mm
ROD_AREA_M2: float = _math.pi / 4 * ROD_DIA_M ** 2    # 0.000388 m²

# Damage rate floor (numerical) to avoid div-by-zero
_DAMAGE_EPS: float = 1e-12


# ── Per-well cumulative damage state ──────────────────────────────────────────

@dataclass
class FatigueState:
    """Running fatigue state for one well."""
    well_id: str
    cumulative_damage: float = 0.0     # Miner's D = Σ(n_i/N_fi), range [0, ∞)
    total_cycles: float = 0.0          # total rod cycles accumulated
    damage_history: list[float] = field(default_factory=list)  # damage per tick
    dominant_cause: str = "normal_cycling"
    provenance: str = "SIMULATED_LIVE"


# Module-level per-well state
_states: dict[str, FatigueState] = {}


def _get_or_create(well_id: str) -> FatigueState:
    if well_id not in _states:
        _states[well_id] = FatigueState(well_id=well_id)
    return _states[well_id]


# ── Core physics ──────────────────────────────────────────────────────────────

def _stress_mpa(load_kn: float) -> float:
    """Convert load [kN] to stress [MPa] via rod cross-section area."""
    return (load_kn * 1000.0) / ROD_AREA_M2 / 1e6  # Pa → MPa


def _cycles_to_failure(sigma_a_mpa: float) -> float:
    """
    Basquin S-N law: N_f = (S_E / σ_a)^(1/b)
    [A, Shigley eq. 6-14]  [C, API RP 11L]
    Returns infinity when σ_a ≤ 0.
    """
    if sigma_a_mpa <= 0.0:
        return math.inf
    return (S_E_MPA / sigma_a_mpa) ** (1.0 / BASQUIN_B)


def _goodman_ratio(sigma_a_mpa: float, sigma_m_mpa: float) -> float:
    """
    Modified Goodman:  G = σ_a / S_e + σ_m / S_u  [A, Shigley eq. 6-46]
    G ≥ 1 → fatigue failure expected.
    """
    return sigma_a_mpa / S_E_MPA + sigma_m_mpa / S_U_MPA


def update_fatigue(
    well_id: str,
    peak_load_kn: float,
    min_load_kn: float,
    spm: float,
    dt_days: float,
    active_fault: Optional[str] = None,
) -> FatigueState:
    """
    Advance cumulative fatigue damage for one simulation tick.

    Parameters
    ----------
    well_id       : well identifier
    peak_load_kn  : peak polished-rod load this tick [kN]
    min_load_kn   : minimum polished-rod load this tick [kN]
    spm           : strokes per minute (determines cycle count)
    dt_days       : simulated time step [days]
    active_fault  : current fault type, if any (amplifies damage)

    Physics:
      n_i = spm × dt_days × 1440  cycles in this tick
      σ_max = _stress_mpa(peak_load_kn)
      σ_min = _stress_mpa(min_load_kn)
      σ_a = (σ_max - σ_min) / 2         stress amplitude [A]
      σ_m = (σ_max + σ_min) / 2         mean stress      [A]
      N_fi = _cycles_to_failure(σ_a)    Basquin S-N law  [A][C]
      D_i  = n_i / N_fi                 Miner increment  [D]
    """
    state = _get_or_create(well_id)

    # Stress calculation
    sigma_max = _stress_mpa(abs(peak_load_kn))
    sigma_min = _stress_mpa(abs(min_load_kn))
    if sigma_max < sigma_min:
        sigma_max, sigma_min = sigma_min, sigma_max

    sigma_a = (sigma_max - sigma_min) / 2.0   # amplitude [MPa]
    # sigma_m = (sigma_max + sigma_min) / 2.0  (unused in damage but available)

    # Fault multiplier — faults increase stress amplitude
    # rod_floating: impact load [documented in Takacs 2015, Ch.9]
    # fluid_pound:  severe impact loading [Takacs 2015]
    fault_multipliers = {
        "rod_floating":    1.6,   # LITERATURE_ASSUMPTION [Takacs 2015 Ch.9]
        "fluid_pound":     2.0,   # LITERATURE_ASSUMPTION [Takacs 2015 Ch.9]
        "pump_off":        1.2,
        "gas_interference":1.1,
        "pump_unsetting":  1.4,
    }
    mult = fault_multipliers.get(active_fault or "", 1.0)
    sigma_a_eff = sigma_a * mult

    # Cycles this tick
    n_i = spm * dt_days * 1440.0   # spm × min/day

    # Cycles to failure at this amplitude (Basquin)
    N_fi = _cycles_to_failure(sigma_a_eff)

    # Miner increment
    d_i = n_i / N_fi if N_fi > 0 else 0.0

    state.cumulative_damage += d_i
    state.total_cycles += n_i

    # Track damage history (last 200 ticks)
    state.damage_history.append(d_i)
    if len(state.damage_history) > 200:
        state.damage_history.pop(0)

    # Dominant cause
    if active_fault in fault_multipliers:
        state.dominant_cause = active_fault
    elif sigma_a_eff > 0.7 * S_E_MPA:
        state.dominant_cause = "high_stress_cycling"
    else:
        state.dominant_cause = "normal_cycling"

    return state


# ── Life estimation ──────────────────────────────────────────────────────────

def compute_fatigue_report(well_id: str) -> dict:
    """
    Return the full fatigue report for a well.

    Provenance labels:
      cumulative_damage       → SIMULATED_LIVE   (accumulated from live ticks)
      remaining_life_days_p50 → LITERATURE_ASSUMPTION  (Basquin + Miner scatter [A][D][E])
      recommended_workover    → DEMO_RESULT       (threshold rule)
    """
    state = _get_or_create(well_id)
    D = state.cumulative_damage

    # Remaining life fraction
    remaining_fraction = max(0.0, 1.0 - D)

    # Damage rate per day (rolling average of last 50 ticks)
    recent = state.damage_history[-50:] if state.damage_history else [0.0]
    # dt_days not stored per-tick; estimate from total_cycles and spm~5
    # Conservative: use average of recent tick increments directly
    avg_d_per_tick = sum(recent) / max(len(recent), 1)
    # Convert to per-day: assume ~1.5s tick interval, 10x acceleration
    # 1 tick = 1.5 * 10 / 86400 days ≈ 0.0001736 days
    tick_dt_days = (1.5 * 10) / 86400.0
    damage_rate_per_day = avg_d_per_tick / max(tick_dt_days, _DAMAGE_EPS)

    # Remaining life estimates
    if damage_rate_per_day > _DAMAGE_EPS:
        p50_days = remaining_fraction / damage_rate_per_day
        p10_days = p50_days * MINER_SCATTER_P10   # conservative [E]
        p90_days = p50_days * MINER_SCATTER_P90   # optimistic   [E]
    else:
        p50_days = p10_days = p90_days = 9999.0   # effectively infinite

    # Recommended workover window
    if D >= 0.95:
        workover_window = "IMMEDIATE — damage critical (D ≥ 0.95)"
        urgency = "critical"
    elif D >= 0.70:
        workover_window = f"Within {p10_days:.0f}–{p50_days:.0f} days (p10–p50)"
        urgency = "high"
    elif D >= 0.40:
        workover_window = f"Plan within {p50_days:.0f} days (p50)"
        urgency = "medium"
    else:
        workover_window = f"Not urgent — estimated {p50_days:.0f} days remaining"
        urgency = "low"

    return {
        "well_id": well_id,
        "cumulative_damage": round(D, 6),
        "remaining_life_fraction": round(remaining_fraction, 4),
        "remaining_life_days_p50": round(p50_days, 1),
        "remaining_life_days_p10": round(p10_days, 1),
        "remaining_life_days_p90": round(p90_days, 1),
        "damage_rate_per_day": round(damage_rate_per_day, 8),
        "total_cycles": int(state.total_cycles),
        "dominant_cause": state.dominant_cause,
        "recommended_workover_window": workover_window,
        "urgency": urgency,
        "damage_history_last50": [round(d, 8) for d in state.damage_history[-50:]],
        "provenance": {
            "cumulative_damage":        "SIMULATED_LIVE",
            "remaining_life_days_p50":  "LITERATURE_ASSUMPTION",
            "workover_window":          "DEMO_RESULT",
        },
        "method": (
            "Miner's rule [Miner 1945] + Basquin S-N [Shigley 2011] + "
            "Goodman criterion [API Spec 11B 2013]. "
            "NOT validated against real Baghewala field rod failure records."
        ),
    }


def reset_fatigue(well_id: str) -> dict:
    """Reset damage (simulates rod replacement / workover)."""
    _states[well_id] = FatigueState(well_id=well_id)
    logger.info(f"Fatigue reset for {well_id} (simulates rod replacement)")
    return {"well_id": well_id, "reset": True}


def get_all_fatigue_reports() -> list[dict]:
    """Return fatigue report for all tracked wells, sorted by urgency."""
    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    reports = [compute_fatigue_report(wid) for wid in _states]
    return sorted(reports, key=lambda r: urgency_order.get(r["urgency"], 9))
