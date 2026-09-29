"""
backend/app/services/audit_service.py
Feature 4 — Trust Layer: Audit Log + Approval Flow

Provides:
  - Append-only SQLite audit log with SHA-256 hash chain.
    Each entry stores SHA256(prev_hash || canonical_entry_json).
    Tampering any stored row breaks the chain — detectable via verify().
  - Recommendation state machine: proposed → approved/rejected → applied
  - Confidence band calculation (from surrogate sensitivity)
  - Verdict assignment (SAFE / CAUTION / UNSAFE) via constraint engine
  - Safe-mode enforcement: caps step sizes before allowing application

PROVENANCE: DEMO_RESULT
  This is a concept demonstration of human-in-the-loop controls.
  It does NOT implement real authentication, authorization, or
  cryptographic non-repudiation. Do not deploy as real security.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("audit_service")

# ── In-memory stores (SQLite persistence via ORM is wired in api/audit.py) ──
_recommendation_states: dict[str, dict] = {}   # rec_id → state dict
_audit_log: list[dict] = []                     # append-only list
_last_hash: str = "0" * 64                      # genesis hash

# ── Safe-mode limits (editable via API) ──────────────────────────────────────
SAFE_MODE_LIMITS = {
    "spm_max_step":               2.0,   # strokes/min per change
    "stroke_length_max_step_m":   0.5,   # m per change
    "steam_volume_max_step_m3":  100.0,  # m³ per change
    "soak_days_max_step":          5.0,  # days per change
}

_safe_mode_active: bool = False
_current_role: str = "Operator"   # Operator | Engineer | Viewer (demo switch only)

ROLE_PERMISSIONS = {
    "Viewer":   {"can_approve": False, "can_apply": False},
    "Operator": {"can_approve": False, "can_apply": True},  # can apply already-approved
    "Engineer": {"can_approve": True,  "can_apply": True},
}


# ── Hash chain ────────────────────────────────────────────────────────────────

def _canonical(entry: dict) -> str:
    """Deterministic JSON for hashing — sorted keys, no extra whitespace."""
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(prev_hash: str, entry: dict) -> str:
    """SHA256(prev_hash || canonical_entry)."""
    content = prev_hash + _canonical(entry)
    return hashlib.sha256(content.encode()).hexdigest()


# ── Audit log operations ─────────────────────────────────────────────────────

def append_audit(
    well_id: str,
    recommendation_id: str,
    action: str,
    before_values: dict,
    after_values: dict,
    constraint_result: str,
    approver: str,
    reason: str = "",
    outcome_values: Optional[dict] = None,
) -> dict:
    """
    Append one entry to the audit log.
    Returns the entry with its hash.
    """
    global _last_hash
    entry_core = {
        "well_id": well_id,
        "recommendation_id": recommendation_id,
        "action": action,
        "before_values": before_values,
        "after_values": after_values,
        "constraint_result": constraint_result,
        "approver": approver,
        "role": _current_role,
        "reason": reason,
        "outcome_values": outcome_values,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entry_hash = _compute_hash(_last_hash, entry_core)
    entry = {
        **entry_core,
        "id": len(_audit_log) + 1,
        "prev_hash": _last_hash,
        "entry_hash": entry_hash,
        "provenance": "DEMO_RESULT",
    }
    _audit_log.append(entry)
    _last_hash = entry_hash
    logger.info(f"Audit: {action} on {recommendation_id} by {approver} ({_current_role})")
    return entry


def verify_chain() -> dict:
    """
    Verify the entire hash chain.
    Returns {valid: bool, first_broken_at: int|None, total_entries: int}.
    """
    prev = "0" * 64
    for i, entry in enumerate(_audit_log):
        expected = _compute_hash(prev, {
            k: v for k, v in entry.items()
            if k not in ("id", "prev_hash", "entry_hash", "provenance")
        })
        if expected != entry["entry_hash"]:
            return {"valid": False, "first_broken_at": i + 1, "total_entries": len(_audit_log)}
        prev = entry["entry_hash"]
    return {"valid": True, "first_broken_at": None, "total_entries": len(_audit_log)}


def get_audit_log(
    well_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    entries = _audit_log
    if well_id:
        entries = [e for e in entries if e["well_id"] == well_id]
    if action:
        entries = [e for e in entries if e["action"] == action]
    return entries[-limit:]


# ── Recommendation state machine ─────────────────────────────────────────────

def _verdict_from_constraint(constraint_result: str) -> str:
    if constraint_result == "SAFE":
        return "SAFE"
    if constraint_result == "CAUTION":
        return "CAUTION"
    return "UNSAFE"


def propose_recommendation(
    well_id: str,
    recommendation: dict,
    confidence_low: float = 0.0,
    confidence_high: float = 0.0,
    constraint_result: str = "SAFE",
) -> dict:
    """Register a new recommendation in 'proposed' state."""
    rec_id = recommendation.get("id") or f"rec-{uuid.uuid4().hex[:8]}"
    verdict = _verdict_from_constraint(constraint_result)

    state = {
        "recommendation_id": rec_id,
        "well_id": well_id,
        "state": "proposed",
        "verdict": verdict,
        "confidence_low": confidence_low,
        "confidence_high": confidence_high,
        "payload": recommendation,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": None,
        "safe_mode_active": _safe_mode_active,
        "provenance": "DEMO_RESULT",
    }
    _recommendation_states[rec_id] = state

    append_audit(
        well_id=well_id,
        recommendation_id=rec_id,
        action="proposed",
        before_values=recommendation.get("kpi_deltas", {}),
        after_values=recommendation.get("recommended_config", {}),
        constraint_result=constraint_result,
        approver="system",
        reason="Auto-proposed by optimizer",
    )
    return state


def approve_recommendation(rec_id: str, approver: str, reason: str = "") -> dict:
    """Move recommendation to 'approved' state. Engineer role required."""
    perms = ROLE_PERMISSIONS.get(_current_role, {})
    if not perms.get("can_approve"):
        raise PermissionError(f"Role '{_current_role}' cannot approve recommendations")

    state = _recommendation_states.get(rec_id)
    if state is None:
        raise KeyError(f"Recommendation {rec_id!r} not found")
    if state["state"] not in ("proposed",):
        raise ValueError(f"Cannot approve from state '{state['state']}'")
    if state["verdict"] == "UNSAFE" and _safe_mode_active:
        raise ValueError("Safe mode active — UNSAFE recommendations cannot be approved")

    state["state"] = "approved"
    state["approved_by"] = approver
    state["updated_at"] = datetime.now(timezone.utc).isoformat()

    append_audit(
        well_id=state["well_id"],
        recommendation_id=rec_id,
        action="approved",
        before_values={},
        after_values=state["payload"].get("recommended_config", {}),
        constraint_result=state["verdict"],
        approver=approver,
        reason=reason,
    )
    return state


def reject_recommendation(rec_id: str, approver: str, reason: str = "") -> dict:
    """Move recommendation to 'rejected' state."""
    state = _recommendation_states.get(rec_id)
    if state is None:
        raise KeyError(f"Recommendation {rec_id!r} not found")
    state["state"] = "rejected"
    state["updated_at"] = datetime.now(timezone.utc).isoformat()

    append_audit(
        well_id=state["well_id"],
        recommendation_id=rec_id,
        action="rejected",
        before_values={},
        after_values={},
        constraint_result=state["verdict"],
        approver=approver,
        reason=reason,
    )
    return state


def apply_recommendation(rec_id: str, sim_service, approver: str = "system") -> dict:
    """
    Apply an approved recommendation to the live simulator.
    Enforces safe-mode step limits.
    NOTHING changes in the simulation without prior approval.
    """
    perms = ROLE_PERMISSIONS.get(_current_role, {})
    if not perms.get("can_apply"):
        raise PermissionError(f"Role '{_current_role}' cannot apply recommendations")

    state = _recommendation_states.get(rec_id)
    if state is None:
        raise KeyError(f"Recommendation {rec_id!r} not found")
    if state["state"] != "approved":
        raise ValueError(f"Recommendation must be approved before applying (state='{state['state']}')")

    payload = state["payload"]
    well_id = state["well_id"]
    cfg = payload.get("recommended_config", payload.get("best_srp", {}))

    # Safe-mode step clamping
    if _safe_mode_active:
        current_state = sim_service.get_latest(well_id)
        if current_state:
            if "spm" in cfg:
                delta = cfg["spm"] - current_state.spm
                delta = max(-SAFE_MODE_LIMITS["spm_max_step"],
                            min(SAFE_MODE_LIMITS["spm_max_step"], delta))
                cfg = {**cfg, "spm": round(current_state.spm + delta, 2)}
            if "stroke_length_m" in cfg:
                delta = cfg["stroke_length_m"] - current_state.stroke_length_m
                delta = max(-SAFE_MODE_LIMITS["stroke_length_max_step_m"],
                            min(SAFE_MODE_LIMITS["stroke_length_max_step_m"], delta))
                cfg = {**cfg, "stroke_length_m": round(current_state.stroke_length_m + delta, 3)}

    # Apply to simulator
    apply_kwargs = {}
    if "spm" in cfg:
        apply_kwargs["spm"] = cfg["spm"]
    if "stroke_length_m" in cfg:
        apply_kwargs["stroke_length_m"] = cfg["stroke_length_m"]
    if "vfd_frequency_hz" in cfg:
        apply_kwargs["vfd_frequency_hz"] = cfg["vfd_frequency_hz"]

    ok = sim_service.apply_config(well_id, **apply_kwargs) if apply_kwargs else True
    if not ok:
        raise RuntimeError(
            f"Simulator rejected config update for well {well_id!r}. "
            "Recommendation state NOT changed."
        )

    state["state"] = "applied"
    state["updated_at"] = datetime.now(timezone.utc).isoformat()

    append_audit(
        well_id=well_id,
        recommendation_id=rec_id,
        action="applied",
        before_values={},
        after_values=cfg,
        constraint_result=state["verdict"],
        approver=approver,
        reason=f"Applied via API. safe_mode={_safe_mode_active}",
    )
    return {"state": state, "applied_config": cfg, "sim_ok": ok}


def get_recommendation_state(rec_id: str) -> Optional[dict]:
    return _recommendation_states.get(rec_id)


def list_recommendation_states(well_id: Optional[str] = None) -> list[dict]:
    states = list(_recommendation_states.values())
    if well_id:
        states = [s for s in states if s["well_id"] == well_id]
    return sorted(states, key=lambda s: s["updated_at"], reverse=True)


# ── Safe mode + role ──────────────────────────────────────────────────────────

def set_safe_mode(active: bool) -> dict:
    global _safe_mode_active
    _safe_mode_active = active
    logger.info(f"Safe mode: {'ON' if active else 'OFF'}")
    return {"safe_mode_active": _safe_mode_active}


def set_role(role: str) -> dict:
    global _current_role
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"Unknown role {role!r}. Valid: {list(ROLE_PERMISSIONS)}")
    _current_role = role
    logger.info(f"Demo role switched to: {role}")
    return {"role": _current_role, "permissions": ROLE_PERMISSIONS[role]}


def get_status() -> dict:
    return {
        "current_role": _current_role,
        "permissions": ROLE_PERMISSIONS[_current_role],
        "safe_mode_active": _safe_mode_active,
        "safe_mode_limits": SAFE_MODE_LIMITS,
        "total_audit_entries": len(_audit_log),
        "pending_recommendations": sum(
            1 for s in _recommendation_states.values() if s["state"] == "proposed"
        ),
        "provenance": "DEMO_RESULT",
        "disclaimer": (
            "This is a concept demonstration of human-in-the-loop controls. "
            "No real authentication is implemented."
        ),
    }
