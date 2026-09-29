"""
backend/app/api/data.py
Feature 3 — Data Upload & Calibration Wizard API

Endpoints:
  POST /data/upload              — upload CSV/Excel, map columns, create profile
  POST /data/calibrate           — run SciPy curve_fit on uploaded profile
  GET  /data/profiles            — list all stored profiles
  GET  /data/profiles/{id}       — full profile including fit result + residuals
  POST /data/profiles/{id}/activate — apply fitted params to simulator config
  GET  /data/sample              — download a synthetic sample CSV template
"""
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.services import calibration_service as svc

logger = logging.getLogger("api.data")
router = APIRouter()


# ── Request / response schemas ────────────────────────────────────────────────

class CalibrateRequest(BaseModel):
    profile_id: str


class ActivateRequest(BaseModel):
    pass  # no body needed


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/data/upload")
async def upload_data(
    file: UploadFile = File(...),
    calibration_target: str = Form(...),
    column_map_json: str = Form(...),
):
    """
    Upload a CSV or Excel file and map its columns.

    Form fields:
      - file               : CSV or .xlsx file
      - calibration_target : "viscosity_andrade" or "ipr_vogel"
      - column_map_json    : JSON string, e.g.
          {"temperature_c": "Temp_degC", "viscosity_cp": "Visc_cP"}

    Returns the new profile metadata.
    PROVENANCE: USER_UPLOADED
    """
    import json
    try:
        column_map = json.loads(column_map_json)
    except Exception:
        raise HTTPException(400, "column_map_json must be valid JSON")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Uploaded file is empty")
    if len(file_bytes) > 5_000_000:
        raise HTTPException(413, "File too large (max 5 MB)")

    try:
        profile = svc.upload(
            filename=file.filename or "upload.csv",
            file_bytes=file_bytes,
            calibration_target=calibration_target,
            column_map=column_map,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, f"Upload failed: {e}")

    return profile


@router.post("/data/calibrate")
async def run_calibration(body: CalibrateRequest):
    """
    Run SciPy curve_fit on a previously uploaded profile.
    Returns full fit result including parameters, R², RMSE, residuals.
    PROVENANCE: CALIBRATED_MODEL
    """
    try:
        result = svc.calibrate(body.profile_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Calibration failed: {e}")
        raise HTTPException(500, f"Calibration failed: {e}")

    return result


@router.get("/data/profiles")
async def list_profiles():
    """
    List all uploaded profiles (metadata only, no data arrays).
    PROVENANCE: USER_UPLOADED | CALIBRATED_MODEL (depending on state)
    """
    profiles = svc.list_profiles()
    return {
        "profiles": profiles,
        "count": len(profiles),
        "active_profiles": {
            target: pid
            for target, pid in svc._active_profile.items()
            if pid is not None
        },
    }


@router.get("/data/profiles/{profile_id}")
async def get_profile(profile_id: str):
    """
    Full profile including fit result (params + residuals + predicted values).
    PROVENANCE: USER_UPLOADED | CALIBRATED_MODEL
    """
    try:
        return svc.get_profile(profile_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/data/profiles/{profile_id}/activate")
async def activate_profile(profile_id: str):
    """
    Apply the calibrated profile's parameters to the simulator config (in-memory).

    This updates ANDRADE_A/ANDRADE_B (viscosity) or PI_REFERENCE (IPR) live,
    without requiring a restart. Restarting the process resets to file defaults.

    PROVENANCE: CALIBRATED_MODEL
    NOT validated against real Baghewala field lab data.
    """
    try:
        result = svc.activate_profile(profile_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Activation failed: {e}")
        raise HTTPException(500, f"Activation failed: {e}")

    return result


@router.get("/data/sample")
async def get_sample(target: str = "viscosity_andrade"):
    """
    Download a synthetic sample CSV for the given calibration target.
    Use this to understand the expected column format.
    PROVENANCE: SYNTHETIC_HISTORICAL
    """
    from fastapi.responses import PlainTextResponse
    valid = {"viscosity_andrade", "ipr_vogel"}
    if target not in valid:
        raise HTTPException(400, f"Invalid target. Valid: {sorted(valid)}")
    try:
        csv_text = svc.make_sample_csv(target)
    except Exception as e:
        raise HTTPException(500, str(e))
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="sample_{target}.csv"'},
    )
