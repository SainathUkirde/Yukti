"""
backend/app/api/optimize.py
Joint CSS + SRP optimization endpoint.
Wraps JointOptimizer (Optuna TPE Bayesian, 7 decision variables) with a per-well result cache.
"""
import logging
import os
import sys
import time
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

logger = logging.getLogger("api.optimize")
router = APIRouter()

# Cache last optimization result per well (in-memory for demo)
_opt_cache: dict[str, dict] = {}


class OptimizeRequest(BaseModel):
    well_id: str
    n_trials: int = Field(60, ge=10, le=300, description="Optuna TPE trials")
    objective: str = Field("min_cost_per_bbl",
                           description="min_cost_per_bbl | max_oil | min_sor")
    apply: bool = Field(False, description="If True, apply best SRP config to simulator immediately")


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


@router.post("/")
async def optimize(body: OptimizeRequest, request: Request):
    """
    Run joint CSS+SRP Optuna optimization for the given well.
    Returns recommended CSS and SRP parameters with KPI deltas and constraint audit.
    PROVENANCE: OPTIMIZER_RECOMMENDATION
    """
    sim = _sim(request)
    state = sim.get_latest(body.well_id)
    if state is None:
        raise HTTPException(404, f"Well {body.well_id!r} not found")
    params = sim.get_well_params(body.well_id)

    t0 = time.time()
    try:
        from optimizer.joint_optimizer import JointOptimizer

        optimizer = JointOptimizer(
            params,
            n_trials=body.n_trials,
            objective=body.objective,
        )
        result = optimizer.optimize()
        elapsed = round(time.time() - t0, 2)

        resp = {
            "well_id": body.well_id,
            "status": "ok",
            "elapsed_s": elapsed,
            "n_trials": body.n_trials,
            "objective": result.objective,
            "method": result.method,

            # ── Recommended config ──────────────────────────────────────────
            "recommended_config": {
                **result.best_css,
                **result.best_srp,
            },
            "best_css": result.best_css,
            "best_srp": result.best_srp,

            # ── Predicted KPIs ──────────────────────────────────────────────
            "predicted_kpis": {
                "oil_rate_m3d": result.predicted_oil_rate_m3d,
                "sor": result.predicted_sor,
                "kwh_per_bbl": result.predicted_kwh_per_bbl,
                "pump_efficiency": result.predicted_pump_efficiency,
                "rod_float_risk": result.predicted_rod_float_risk,
                "cost_per_bbl_inr": result.predicted_cost_per_bbl_inr,
            },

            # ── Baseline KPIs ───────────────────────────────────────────────
            "baseline_kpis": {
                "oil_rate_m3d": result.baseline_oil_rate_m3d,
                "sor": result.baseline_sor,
                "kwh_per_bbl": result.baseline_kwh_per_bbl,
                "pump_efficiency": result.baseline_pump_efficiency,
                "rod_float_risk": result.baseline_rod_float_risk,
                "cost_per_bbl_inr": result.baseline_cost_per_bbl_inr,
            },

            # ── KPI deltas ──────────────────────────────────────────────────
            "kpi_deltas": {
                "oil_rate_delta_pct": result.delta_oil_pct,
                "sor_delta_pct": result.delta_sor_pct,
                "energy_delta_pct": result.delta_energy_pct,
                "cost_per_bbl_delta_pct": result.delta_cost_per_bbl_pct,
                "rod_risk_delta_pts": result.delta_risk_pts,
                "steam_tonnes_saved_per_cycle": result.steam_tonnes_saved_per_cycle,
            },

            "constraints_passed": result.constraints_passed,
            "constraint_violations": [
                {
                    "constraint_id": v["constraint_id"],
                    "name": v["name"],
                    "severity": v["severity"],
                }
                for v in (result.constraint_violations or [])
            ],
            "best_trial_value": result.best_trial_value,
            "provenance": "OPTIMIZER_RECOMMENDATION",
        }

        _opt_cache[body.well_id] = resp

        if body.apply:
            sim.apply_config(
                body.well_id,
                spm=result.best_srp["spm"],
                stroke_length_m=result.best_srp["stroke_length_m"],
                vfd_frequency_hz=result.best_srp["vfd_frequency_hz"],
            )
            resp["applied"] = True
            logger.info(f"Applied optimizer config to {body.well_id}")
        else:
            resp["applied"] = False

        return resp

    except ImportError as e:
        logger.error(f"Optimizer import failed: {e}")
        raise HTTPException(500, f"Optimizer unavailable: {e}")
    except Exception as e:
        logger.error(f"Optimization failed for {body.well_id}: {e}")
        raise HTTPException(500, f"Optimization failed: {e}")


@router.get("/{well_id}/last")
async def get_last_optimization(well_id: str):
    """Return cached result from last optimization run."""
    result = _opt_cache.get(well_id)
    if result is None:
        raise HTTPException(404, f"No optimization result cached for {well_id!r}. "
                                 "Run POST /optimize first.")
    return result
