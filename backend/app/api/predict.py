"""
backend/app/api/predict.py
Prediction endpoint — combines production forecast + fault classification + risk score.
Accepts a WellStateSnapshot-derived feature vector and returns ML predictions.
"""
import logging
import os
import sys
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

logger = logging.getLogger("api.predict")
router = APIRouter()


def _trapz(y, x=None):
    import numpy as np
    if hasattr(np, "trapezoid"):
        return np.trapezoid(y, x)
    return np.trapz(y, x)


def _ml(request: Request):
    from backend.app.services.ml_service import ml_service
    return ml_service


def _sim(request: Request):
    sim = getattr(request.app.state, "sim_service", None)
    if sim is None:
        raise HTTPException(503, "Simulation service not ready")
    return sim


def _build_production_features(state) -> list[float]:
    """
    Build a feature vector from a WellStateSnapshot for production forecasting.
    Matches the 42 lag/rolling features from ml/features/production_features.py.
    For live use, we build a single-row feature from current snapshot values.
    """
    import numpy as np
    # Use available live values; zeros for lags we can't compute from a single snapshot
    feats = [
        state.reservoir_temp_c,
        state.oil_viscosity_cp,
        state.oil_rate_m3d,
        state.water_rate_m3d,
        state.water_cut_fraction,
        state.spm,
        state.stroke_length_m,
        state.pump_efficiency_fraction,
        state.motor_power_kw,
        state.sor,
        state.reservoir_pressure_kpa,
        state.heated_zone_radius_m,
        state.rod_float_risk_ratio,
        state.pump_fillage_fraction,
        state.time_in_phase_days,
        state.cycle_number,
        float(state.phase == "production"),
        float(state.phase == "injection"),
        float(state.phase == "soak"),
        state.peak_load_kn,
        state.min_load_kn,
        state.goodman_ratio,
        state.kwh_per_bbl,
        state.fault_severity,
    ]
    # Pad to 42 features with zeros (lags not available from single snapshot)
    while len(feats) < 42:
        feats.append(0.0)
    return feats[:42]


def _build_dyno_features(state) -> list[float]:
    """
    Build a 31-feature dyno card feature vector from the current snapshot.
    """
    import numpy as np
    pos = np.array(state.surface_position_m)
    load = np.array(state.surface_load_kn)
    dpos = np.array(state.downhole_position_m)
    dload = np.array(state.downhole_load_kn)

    def safe(arr): return arr if len(arr) > 0 else np.array([0.0])

    sp, sl = safe(pos), safe(load)
    dp, dl = safe(dpos), safe(dload)

    feats = [
        float(np.max(sl) - np.min(sl)),        # load_range
        float(np.max(sl)),                       # peak_load
        float(np.min(sl)),                       # min_load
        float(np.mean(sl)),                      # mean_load
        float(np.std(sl)),                       # std_load
        float(np.max(sp) - np.min(sp)),          # stroke_length
        float(_trapz(sl, sp)) if len(sp)>1 else 0.0,  # area_surface
        float(np.max(dl) - np.min(dl)),          # downhole_load_range
        float(np.max(dl)),                       # downhole_peak
        float(np.min(dl)),                       # downhole_min
        float(np.mean(dl)),                      # downhole_mean
        float(np.std(dl)),                       # downhole_std
        float(_trapz(dl, dp)) if len(dp)>1 else 0.0,  # area_downhole
        state.spm,
        state.stroke_length_m,
        state.pump_fillage_fraction,
        state.pump_efficiency_fraction,
        state.oil_viscosity_cp,
        state.reservoir_temp_c,
        state.rod_float_risk_ratio,
        state.rod_float_risk_score,
        state.peak_load_kn,
        state.min_load_kn,
        state.goodman_ratio,
        state.fault_severity,
        float(state.phase == "production"),
        state.motor_power_kw,
        state.vfd_frequency_hz,
        state.oil_rate_m3d,
        state.water_cut_fraction,
        state.time_in_phase_days,
    ]
    return feats[:31]


@router.post("/")
async def predict(well_id: str, request: Request):
    """
    Run all three ML models on the current well state.
    Returns: production forecast, fault classification, failure risk score.
    """
    sim = _sim(request)
    state = sim.get_latest(well_id)
    if state is None:
        raise HTTPException(404, f"Well {well_id!r} not found or no data yet")

    ml = _ml(request)

    # 1. Fault classification (dyno card features)
    dyno_feats = _build_dyno_features(state)
    fault_result = ml.classify_fault(dyno_feats)

    # 2. Failure risk score (same dyno + production features)
    risk_score, risk_factors = ml.score_risk(dyno_feats)

    # 3. Production forecast (production features)
    prod_feats = _build_production_features(state)
    forecast = ml.forecast([prod_feats])

    return {
        "well_id": well_id,
        "fault_classification": {
            **fault_result,
            "provenance": "ML_PREDICTION",
        },
        "failure_risk": {
            "risk_score": round(risk_score, 1),
            "risk_level": "high" if risk_score >= 70 else ("medium" if risk_score >= 40 else "low"),
            "top_factors": risk_factors,
            "provenance": "ML_PREDICTION",
        },
        "production_forecast": {
            "forecasts": forecast,
            "horizon_days": 14,
            "note": "Single-step forecast from current state (not multi-step rollout)",
            "provenance": "ML_PREDICTION",
        },
    }


@router.get("/{well_id}/risk")
async def quick_risk(well_id: str, request: Request):
    """Quick risk score for a single well (lightweight)."""
    sim = _sim(request)
    state = sim.get_latest(well_id)
    if state is None:
        raise HTTPException(404, f"Well {well_id!r} not found")
    ml = _ml(request)
    dyno_feats = _build_dyno_features(state)
    score, factors = ml.score_risk(dyno_feats)
    return {
        "well_id": well_id,
        "risk_score": round(score, 1),
        "risk_level": "high" if score >= 70 else ("medium" if score >= 40 else "low"),
        "top_factors": factors[:3],
        "provenance": "ML_PREDICTION",
    }
