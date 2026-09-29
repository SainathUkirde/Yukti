"""
backend/app/api/field.py
Feature 1 — Field-Level Steam Allocator & CSS Scheduler API

Endpoints:
  POST /field/allocate   — run greedy marginal-value allocator, return AllocationResult
  GET  /field/schedule   — return last cached allocation result
  GET  /field/carbon     — stub (full implementation in Feature 5 / Phase A6)
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.services.allocator_service import allocate, AllocationResult, WellAllocation

logger = logging.getLogger("api.field")
router = APIRouter()

# In-memory cache for last allocation result
_alloc_cache: Optional[AllocationResult] = None


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


class AllocateRequest(BaseModel):
    steam_budget_m3: float = Field(
        5000.0, ge=100.0, le=50000.0,
        description="Total steam budget for the planning period [m³ CWE]",
    )
    generator_capacity_m3_per_day: float = Field(
        200.0, ge=10.0, le=2000.0,
        description="Maximum steam generation rate [m³ CWE/day]",
    )
    period_days: float = Field(
        30.0, ge=7.0, le=90.0,
        description="Planning horizon [days]",
    )
    well_ids: Optional[list[str]] = Field(
        None,
        description="Subset of well IDs to include. Omit or null to include all wells.",
    )


def _well_alloc_to_dict(wa: WellAllocation) -> dict:
    return {
        "well_id": wa.well_id,
        "rank": wa.rank,
        "steam_volume_m3": wa.steam_volume_m3,
        "marginal_oil_per_m3_steam": wa.marginal_oil_per_m3_steam,
        "expected_oil_m3": wa.expected_oil_m3,
        "expected_sor": wa.expected_sor,
        "expected_kwh_per_bbl": wa.expected_kwh_per_bbl,
        "start_day": wa.start_day,
        "duration_days": wa.duration_days,
        "rod_fatigue_damage": wa.rod_fatigue_damage,
        "rod_life_constraint_applied": wa.rod_life_constraint_applied,
        "rod_life_reason": wa.rod_life_reason,
        "constraints_passed": wa.constraints_passed,
        "constraint_violations": wa.constraint_violations,
        "explanation": wa.explanation,
        "provenance": wa.provenance,
    }


def _result_to_dict(result: AllocationResult) -> dict:
    return {
        "well_allocations": [_well_alloc_to_dict(w) for w in result.well_allocations],
        "baseline_allocations": [_well_alloc_to_dict(w) for w in result.baseline_allocations],
        "total_steam_allocated_m3": result.total_steam_allocated_m3,
        "total_steam_budget_m3": result.total_steam_budget_m3,
        "expected_total_oil_m3": result.expected_total_oil_m3,
        "baseline_total_oil_m3": result.baseline_total_oil_m3,
        "oil_gain_vs_baseline_pct": result.oil_gain_vs_baseline_pct,
        "expected_field_sor": result.expected_field_sor,
        "period_days": result.period_days,
        "generator_capacity_m3_per_day": result.generator_capacity_m3_per_day,
        "wells_excluded_rod_fatigue": result.wells_excluded_rod_fatigue,
        "method": result.method,
        "provenance": result.provenance,
    }


@router.post("/field/allocate")
async def run_allocation(body: AllocateRequest, request: Request):
    """
    Run greedy marginal-value steam allocation across all (or selected) wells.

    Algorithm: evaluates each well's marginal oil gain per m³ steam via the real
    physics surrogate (NOT hard-coded %). Rod-fatigue integration: wells with
    Miner's D ≥ 0.70 are capped at 60% steam; D ≥ 0.95 are excluded.

    PROVENANCE: OPTIMIZER_RECOMMENDATION (optimized) | DEMO_RESULT (baseline)
    NOT validated against real Baghewala field steam allocation records.
    """
    global _alloc_cache

    sim = _sim(request)
    all_well_ids = list(sim.get_all_wells())
    if not all_well_ids:
        raise HTTPException(503, "No active wells in simulation")

    # Collect WellParameters for all (or requested) wells
    req_ids = set(body.well_ids) if body.well_ids else None
    params_list = []
    missing = []
    for wid in all_well_ids:
        if req_ids and wid not in req_ids:
            continue
        p = sim.get_well_params(wid)
        if p is None:
            missing.append(wid)
        else:
            params_list.append(p)

    if missing:
        raise HTTPException(404, f"Wells not found: {missing}")
    if not params_list:
        raise HTTPException(400, "No matching wells found for allocation")

    try:
        result = allocate(
            well_params_list=params_list,
            steam_budget_m3=body.steam_budget_m3,
            generator_capacity_m3_per_day=body.generator_capacity_m3_per_day,
            period_days=body.period_days,
        )
    except Exception as e:
        logger.error(f"Allocation failed: {e}")
        raise HTTPException(500, f"Allocation failed: {e}")

    _alloc_cache = result
    logger.info(
        f"Allocation complete: {len(result.well_allocations)} wells, "
        f"{result.total_steam_allocated_m3:.0f} m³ steam, "
        f"+{result.oil_gain_vs_baseline_pct:.1f}% vs baseline"
    )
    return _result_to_dict(result)


@router.get("/field/schedule")
async def get_schedule(request: Request):
    """
    Return the last cached allocation/schedule result.
    Call POST /field/allocate first to generate one.
    PROVENANCE: OPTIMIZER_RECOMMENDATION
    """
    _sim(request)  # ensure service is ready
    if _alloc_cache is None:
        raise HTTPException(404, "No allocation result cached yet. Run POST /field/allocate first.")
    return _result_to_dict(_alloc_cache)


