"""
backend/app/api/recommendations.py
Recommendations endpoint — rule-based + optimizer-derived action cards.
Combines ML risk scores with optimizer cache and physics thresholds.
"""
import logging
from fastapi import APIRouter, Request, Query
from typing import Optional

logger = logging.getLogger("api.recommendations")
router = APIRouter()

# Priority thresholds (physics-calibrated)
RISK_HIGH = 70.0
RISK_MED = 40.0
ROD_FLOAT_HIGH = 0.85
PUMP_EFF_LOW = 0.50
SOR_HIGH = 5.0
VISCOSITY_HIGH = 800.0


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    return sim


def _build_recommendations(well_id: str, state, opt_cache: dict) -> list[dict]:
    """
    Generate action recommendations from well state.
    Priority: critical > high > medium > info.
    """
    recs = []
    rid = 0

    def add(priority, category, title, action, rationale, kpi_impact=None):
        nonlocal rid
        recs.append({
            "id": f"rec-{well_id}-{rid}",
            "well_id": well_id,
            "priority": priority,
            "category": category,
            "title": title,
            "action": action,
            "rationale": rationale,
            "kpi_impact": kpi_impact or {},
            "provenance": "ML_PREDICTION",
        })
        rid += 1

    # Rod floating risk
    if state.rod_float_risk_ratio >= ROD_FLOAT_HIGH:
        add("critical", "SRP",
            "Rod Float Risk Critical",
            f"Reduce SPM from {state.spm:.1f} to {max(1.5, state.spm * 0.7):.1f}",
            f"N_rf = {state.rod_float_risk_ratio:.2f} ≥ 0.85 threshold. "
            f"Viscosity {state.oil_viscosity_cp:.0f} cP causing buoyancy reversal.",
            {"rod_risk_pct": -30, "pump_eff_pct": +5})
    elif state.rod_float_risk_ratio >= 0.65:
        add("high", "SRP",
            "Rod Float Risk Elevated",
            f"Consider reducing SPM to {max(1.5, state.spm * 0.85):.1f}",
            f"N_rf = {state.rod_float_risk_ratio:.2f}. Monitor rod load pattern.",
            {"rod_risk_pct": -15})

    # High viscosity (Andrade equation driven)
    if state.oil_viscosity_cp >= VISCOSITY_HIGH and state.phase == "production":
        add("high", "CSS",
            "High Viscosity — Consider Early Re-Steam",
            "Advance next CSS injection cycle by 5–7 days",
            f"Reservoir cooled to {state.reservoir_temp_c:.1f}°C, viscosity "
            f"{state.oil_viscosity_cp:.0f} cP. Productivity collapsing.",
            {"oil_rate_pct": +20, "sor_pct": -8})

    # Low pump efficiency
    if state.pump_efficiency_fraction < PUMP_EFF_LOW and state.phase == "production":
        add("high", "SRP",
            "Pump Efficiency Below 50%",
            f"Increase stroke length to {min(4.8, state.stroke_length_m + 0.3):.2f} m "
            f"or reduce SPM to {max(1.5, state.spm - 0.5):.1f}",
            f"Pump fillage {state.pump_fillage_fraction:.0%}, efficiency "
            f"{state.pump_efficiency_fraction:.0%}. Likely gas interference or fluid pound.",
            {"pump_eff_pct": +15, "energy_pct": -10})

    # High SOR
    if state.sor > SOR_HIGH and state.phase == "production":
        add("medium", "CSS",
            "Steam-Oil Ratio Exceeds Target (5:1)",
            "Review steam volume for next cycle. Target ≤4.5 bbl/bbl.",
            f"Current SOR = {state.sor:.2f}. Consider reducing steam volume by 10–15%.",
            {"sor_pct": -12})

    # Active fault
    if state.active_fault:
        fault_actions = {
            "rod_floating":    "Reduce SPM immediately. Check rod loading diagram.",
            "pump_off":        "Shut in pump for 2–4 hours. Allow fluid level to recover.",
            "gas_interference":"Install or check gas separator. Reduce SPM.",
            "fluid_pound":     "Reduce pump speed. Check fluid level sensor.",
            "pump_unsetting":  "Pull pump for inspection. Check anchor.",
        }
        add("critical", "Fault",
            f"Active Fault: {state.active_fault.replace('_', ' ').title()}",
            fault_actions.get(state.active_fault, "Investigate immediately"),
            f"Fault severity {state.fault_severity:.0%}. Immediate action required.",
            {})

    # Optimizer recommendation (if cached)
    cached_opt = opt_cache.get(well_id)
    if cached_opt and cached_opt.get("kpi_deltas", {}).get("oil_rate_delta_pct", 0) > 3:
        delta = cached_opt["kpi_deltas"]
        cfg = cached_opt["recommended_config"]
        add("medium", "Optimizer",
            "Optimizer: Apply Recommended Settings",
            f"SPM→{cfg['spm']:.1f}, SL→{cfg['stroke_length_m']:.2f}m, "
            f"Steam→{cfg['steam_volume_cwe_m3']:.0f}m³",
            f"Joint optimizer projects +{delta['oil_rate_delta_pct']:.1f}% oil rate, "
            f"{delta['sor_delta_pct']:.1f}% SOR change.",
            {"oil_rate_pct": delta["oil_rate_delta_pct"],
             "sor_pct": delta["sor_delta_pct"],
             "energy_pct": delta["energy_delta_pct"]})

    # Sort: critical first
    priority_order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 9))
    return recs


# Shared optimizer cache reference (populated by /optimize endpoint)
try:
    from backend.app.api.optimize import _opt_cache
except ImportError:
    _opt_cache = {}


@router.get("/")
async def get_recommendations(
    request: Request,
    well_id: Optional[str] = Query(None, description="Filter by well ID"),
    priority: Optional[str] = Query(None, description="Filter: critical|high|medium|info"),
):
    """Return action recommendations for all wells (or a specific one)."""
    sim = _sim(request)
    if sim is None:
        return {"recommendations": [], "count": 0}

    all_recs = []
    wells = [well_id] if well_id else sim.get_all_wells()
    for wid in wells:
        state = sim.get_latest(wid)
        if state is None:
            continue
        recs = _build_recommendations(wid, state, _opt_cache)
        all_recs.extend(recs)

    if priority:
        all_recs = [r for r in all_recs if r["priority"] == priority]

    return {
        "recommendations": all_recs,
        "count": len(all_recs),
        "critical_count": sum(1 for r in all_recs if r["priority"] == "critical"),
        "provenance": "ML_PREDICTION",
    }
