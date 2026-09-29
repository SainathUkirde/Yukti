"""
backend/app/services/handover_service.py
Feature 5 (Bonus) — Shift Handover Summary Generator

Builds a structured shift handover document from live simulation data:
  - Active alerts and faults
  - Rod fatigue urgency flags
  - Latest CSS cycle status per well
  - Allocation plan (if cached)
  - Carbon KPIs
  - Recommended actions for the incoming shift

PROVENANCE: SIMULATED_LIVE (state data) + OPTIMIZER_RECOMMENDATION (allocation) +
             LITERATURE_ASSUMPTION (carbon) + DEMO_RESULT (summary)
NOT a real operations handover document.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("handover_service")


def build_handover(
    sim_service,
    fatigue_reports: list[dict],
    allocation_result: Optional[dict],
    carbon_report: Optional[dict],
    shift_label: str = "Day Shift",
    outgoing_operator: str = "Operator A",
    incoming_operator: str = "Operator B",
) -> dict:
    """
    Compile a shift handover summary from all live data sources.

    Parameters
    ----------
    sim_service        : SimulationService instance
    fatigue_reports    : list of per-well fatigue dicts from fatigue_service
    allocation_result  : last AllocationResult dict (or None)
    carbon_report      : field carbon report dict (or None)
    shift_label        : e.g. "Day Shift" | "Night Shift"
    outgoing_operator  : outgoing shift operator name
    incoming_operator  : incoming shift operator name

    Returns
    -------
    Structured handover dict suitable for JSON serialization.
    PROVENANCE: DEMO_RESULT
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    well_ids = sim_service.get_all_wells()

    # ── Well status snapshot ──────────────────────────────────────────────────
    wells_summary = []
    critical_alerts: list[str] = []
    active_faults: list[dict] = []
    high_viscosity_wells: list[str] = []
    low_pump_eff_wells: list[str] = []

    for wid in well_ids:
        state = sim_service.get_latest(wid)
        if state is None:
            continue

        w_entry = {
            "well_id": wid,
            "phase": state.phase,
            "cycle_number": state.cycle_number,
            "oil_rate_m3d": round(float(state.oil_rate_m3d), 3),
            "reservoir_temp_c": round(float(state.reservoir_temp_c), 1),
            "oil_viscosity_cp": round(float(state.oil_viscosity_cp), 0),
            "sor": round(float(state.sor), 2),
            "pump_efficiency_pct": round(float(state.pump_efficiency_fraction) * 100, 1),
            "spm": round(float(state.spm), 1),
            "rod_float_risk": round(float(state.rod_float_risk_ratio), 3),
            "active_fault": state.active_fault,
            "alerts": list(state.active_alerts),
            "provenance": "SIMULATED_LIVE",
        }
        wells_summary.append(w_entry)

        if state.active_fault:
            active_faults.append({
                "well_id": wid,
                "fault": state.active_fault,
                "severity": round(float(state.fault_severity), 3),
            })
            critical_alerts.append(f"{wid}: Active fault '{state.active_fault}'")

        if state.oil_viscosity_cp > 800 and state.phase == "production":
            high_viscosity_wells.append(wid)

        if state.pump_efficiency_fraction < 0.50 and state.phase == "production":
            low_pump_eff_wells.append(wid)

    # ── Rod fatigue summary ───────────────────────────────────────────────────
    critical_rods = [r for r in fatigue_reports if r.get("urgency") == "critical"]
    high_rods = [r for r in fatigue_reports if r.get("urgency") == "high"]
    rod_summary = {
        "critical": [{"well_id": r["well_id"],
                      "damage_pct": round(r["cumulative_damage"] * 100, 2),
                      "recommended_workover": r.get("recommended_workover_window", "—")}
                     for r in critical_rods],
        "high":     [{"well_id": r["well_id"],
                      "damage_pct": round(r["cumulative_damage"] * 100, 2)}
                     for r in high_rods],
        "total_wells_tracked": len(fatigue_reports),
    }

    # ── CSS / allocation summary ──────────────────────────────────────────────
    allocation_summary: Optional[dict] = None
    if allocation_result:
        allocation_summary = {
            "budget_m3": allocation_result.get("total_steam_budget_m3"),
            "allocated_m3": allocation_result.get("total_steam_allocated_m3"),
            "expected_oil_gain_pct": allocation_result.get("oil_gain_vs_baseline_pct"),
            "field_sor": allocation_result.get("expected_field_sor"),
            "excluded_wells": allocation_result.get("wells_excluded_rod_fatigue", []),
            "provenance": "OPTIMIZER_RECOMMENDATION",
        }

    # ── Carbon KPI summary ────────────────────────────────────────────────────
    carbon_summary: Optional[dict] = None
    if carbon_report and "field_totals" in carbon_report:
        ft = carbon_report["field_totals"]
        carbon_summary = {
            "field_co2_per_bbl_kg": ft.get("field_co2_per_bbl_kg"),
            "co2_delta_vs_baseline_pct": ft.get("co2_delta_vs_baseline_pct"),
            "total_cost_inr": ft.get("total_cost_inr"),
            "field_cost_per_bbl_inr": ft.get("field_cost_per_bbl_inr"),
            "provenance": "LITERATURE_ASSUMPTION",
        }

    # ── Priority action list for incoming shift ───────────────────────────────
    priority_actions: list[dict] = []

    # Faults → immediate action
    for fa in active_faults:
        priority_actions.append({
            "priority": "critical",
            "well_id": fa["well_id"],
            "action": f"Investigate active fault '{fa['fault']}' (severity {fa['severity']:.0%}). Reduce SPM or shut in pump.",
            "source": "fault_detection",
        })

    # Critical rod fatigue → workover planning
    for r in critical_rods:
        priority_actions.append({
            "priority": "critical",
            "well_id": r["well_id"],
            "action": f"Schedule rod workover — Miner's D = {r['cumulative_damage']:.2f}. {r.get('recommended_workover_window', '')}",
            "source": "rod_fatigue",
        })

    # High viscosity → CSS pre-emptive action
    for wid in high_viscosity_wells:
        priority_actions.append({
            "priority": "high",
            "well_id": wid,
            "action": "Oil viscosity >800 cP. Consider advancing next CSS cycle to prevent productivity collapse.",
            "source": "viscosity_monitor",
        })

    # Low pump efficiency
    for wid in low_pump_eff_wells:
        priority_actions.append({
            "priority": "high",
            "well_id": wid,
            "action": "Pump efficiency <50%. Adjust SPM or stroke length. Check for gas interference.",
            "source": "pump_efficiency",
        })

    # Sort by priority
    _prio = {"critical": 0, "high": 1, "medium": 2}
    priority_actions.sort(key=lambda x: _prio.get(x["priority"], 9))

    # ── Build final handover document ─────────────────────────────────────────
    return {
        "handover_id": f"HO-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
        "generated_at": timestamp,
        "shift_label": shift_label,
        "outgoing_operator": outgoing_operator,
        "incoming_operator": incoming_operator,

        "executive_summary": {
            "total_wells": len(well_ids),
            "wells_in_production": sum(1 for w in wells_summary if w["phase"] == "production"),
            "wells_in_injection": sum(1 for w in wells_summary if w["phase"] == "injection"),
            "active_faults_count": len(active_faults),
            "critical_rod_fatigue_count": len(critical_rods),
            "high_viscosity_wells_count": len(high_viscosity_wells),
            "total_field_oil_rate_m3d": round(
                sum(w["oil_rate_m3d"] for w in wells_summary if w["phase"] == "production"), 3
            ),
        },

        "priority_actions": priority_actions,
        "active_faults": active_faults,
        "wells_summary": wells_summary,
        "rod_fatigue_summary": rod_summary,
        "allocation_summary": allocation_summary,
        "carbon_summary": carbon_summary,

        "provenance": "DEMO_RESULT",
        "disclaimer": (
            "This handover document is generated from a SIMULATED digital twin. "
            "NOT a real operations handover. All values are SIMULATED_LIVE or LITERATURE_ASSUMPTION. "
            "Verify against SCADA before taking any field action."
        ),
    }
