"""
backend/app/api/whatif.py
What-If analysis endpoint.
Accepts parameter overrides and returns physics-based KPI projections via WhatIfEngine.
PROVENANCE: DEMO_RESULT (paired surrogate runs — NOT hard-coded %)
"""
import logging
import os
import sys
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

logger = logging.getLogger("api.whatif")
router = APIRouter()


class WhatIfRequest(BaseModel):
    well_id: str
    # CSS overrides (None = keep current)
    steam_volume_cwe_m3: Optional[float] = Field(None, gt=0, le=2000)
    soak_days: Optional[float] = Field(None, gt=0, le=90)
    injection_pressure_kpa: Optional[float] = Field(None, gt=0, le=10000)
    steam_quality_fraction: Optional[float] = Field(None, ge=0.5, le=1.0)
    # SRP overrides
    spm: Optional[float] = Field(None, ge=1.0, le=15.0)
    stroke_length_m: Optional[float] = Field(None, ge=0.5, le=5.0)
    vfd_frequency_hz: Optional[float] = Field(None, ge=20.0, le=60.0)
    # Production context
    t_production_days: float = Field(15.0, ge=0, le=120)


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


@router.post("/")
async def whatif(body: WhatIfRequest, request: Request):
    """
    Compute projected KPI changes if the given parameters are applied.
    Uses WhatIfEngine with FastSurrogate physics chain.
    NOT hard-coded percentage deltas — each override propagates through the full chain.
    """
    sim = _sim(request)
    state = sim.get_latest(body.well_id)
    if state is None:
        raise HTTPException(404, f"Well {body.well_id!r} not found")
    params = sim.get_well_params(body.well_id)

    # Build override dict from non-None fields
    overrides = {}
    if body.steam_volume_cwe_m3 is not None:
        overrides["steam_volume_cwe_m3"] = body.steam_volume_cwe_m3
    if body.soak_days is not None:
        overrides["soak_days"] = body.soak_days
    if body.injection_pressure_kpa is not None:
        overrides["injection_pressure_kpa"] = body.injection_pressure_kpa
    if body.steam_quality_fraction is not None:
        overrides["steam_quality"] = body.steam_quality_fraction
    if body.spm is not None:
        overrides["spm"] = body.spm
    if body.stroke_length_m is not None:
        overrides["stroke_length_m"] = body.stroke_length_m
    if body.vfd_frequency_hz is not None:
        overrides["vfd_frequency_hz"] = body.vfd_frequency_hz

    if not overrides:
        raise HTTPException(400, "At least one parameter override is required")

    try:
        from optimizer.whatif.whatif_engine import WhatIfEngine

        engine = WhatIfEngine(params)
        result = engine.evaluate(overrides, t_production_days=body.t_production_days)

        return {
            "well_id": body.well_id,
            "overrides_applied": overrides,
            "t_production_days": body.t_production_days,

            "baseline": {
                "reservoir_temp_c": result.baseline_reservoir_temp_c,
                "viscosity_cp": result.baseline_viscosity_cp,
                "oil_rate_m3d": result.baseline_oil_rate_m3d,
                "pump_fillage": result.baseline_pump_fillage,
                "pump_efficiency": result.baseline_pump_efficiency,
                "sor": result.baseline_sor,
                "kwh_per_bbl": result.baseline_kwh_per_bbl,
                "rod_float_risk": result.baseline_rod_float_risk,
                "motor_power_kw": result.baseline_motor_power_kw,
            },
            "projected": {
                "reservoir_temp_c": result.changed_reservoir_temp_c,
                "viscosity_cp": result.changed_viscosity_cp,
                "oil_rate_m3d": result.changed_oil_rate_m3d,
                "pump_fillage": result.changed_pump_fillage,
                "pump_efficiency": result.changed_pump_efficiency,
                "sor": result.changed_sor,
                "kwh_per_bbl": result.changed_kwh_per_bbl,
                "rod_float_risk": result.changed_rod_float_risk,
                "motor_power_kw": result.changed_motor_power_kw,
            },
            "deltas": {
                "reservoir_temp_c": result.delta_reservoir_temp_c,
                "viscosity_pct": result.delta_viscosity_pct,
                "oil_rate_pct": result.delta_oil_rate_pct,
                "pump_fillage_pct": result.delta_pump_fillage_pct,
                "pump_efficiency_pct": result.delta_pump_efficiency_pct,
                "sor_pct": result.delta_sor_pct,
                "kwh_per_bbl_pct": result.delta_kwh_per_bbl_pct,
                "rod_float_risk": result.delta_rod_float_risk,
            },
            "narrative": result.propagation_chain,
            "constraint_violations": result.constraint_violations,
            "constraints_passed": result.constraints_passed,
            "rod_floating_risk_after": result.rod_floating_risk_after,
            "provenance": "DEMO_RESULT",
        }

    except ImportError as e:
        logger.error(f"WhatIf engine import error: {e}")
        raise HTTPException(500, f"What-If engine unavailable: {e}")
    except Exception as e:
        logger.error(f"WhatIf failed for {body.well_id}: {e}")
        raise HTTPException(500, f"What-If failed: {e}")
