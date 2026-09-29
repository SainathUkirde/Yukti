"""
backend/app/services/calibration_service.py
Feature 3 — Data Upload & Calibration Wizard

Supports two calibration targets:
  1. viscosity_andrade : fit ln(μ) = A + B/T_K  [Andrade 1930; ASTM D341-20]
  2. ipr_vogel         : fit q = q_max*(1 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)²) [Vogel 1968]

Workflow:
  upload()      — parse CSV/Excel → validate columns → store in _profiles
  calibrate()   — run SciPy curve_fit on the uploaded data → store fitted params
  list_profiles()    — return all stored profiles (metadata only)
  get_profile()      — return one profile including fitted params + residuals
  activate_profile() — write fitted params into simulator.config live constants

PROVENANCE: USER_UPLOADED (when data comes from user), CALIBRATED_MODEL (fitted output)
All numbers carry explicit provenance. NOT validated against real Baghewala lab data.

References:
  [A] Andrade, E.N.C. (1930) Nature 125, 309.
  [B] ASTM D341-20 "Standard Practice for Viscosity-Temperature Charts."
  [C] Vogel, J.V. (1968) JPT 83-92.
  [D] Scipy docs: scipy.optimize.curve_fit
"""
from __future__ import annotations

import io
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger("calibration_service")

# ── In-memory profile store ───────────────────────────────────────────────────
# Maps profile_id → profile dict (never persisted to disk in demo)
_profiles: dict[str, dict] = {}

# Active profile IDs per calibration target
_active_profile: dict[str, Optional[str]] = {
    "viscosity_andrade": None,
    "ipr_vogel": None,
}

# ── Column requirements per calibration target ────────────────────────────────
REQUIRED_COLUMNS = {
    "viscosity_andrade": {"temperature_c", "viscosity_cp"},
    "ipr_vogel":         {"pwf_kpa", "oil_rate_m3d"},
}

OPTIONAL_COLUMNS = {
    "viscosity_andrade": {"well_id", "date", "source"},
    "ipr_vogel":         {"well_id", "date", "reservoir_pressure_kpa"},
}


# ── Calibration models ────────────────────────────────────────────────────────

def _andrade_model(T_K: np.ndarray, A: float, B: float) -> np.ndarray:
    """ln(μ) = A + B/T_K  →  μ = exp(A + B/T_K)"""
    return np.exp(A + B / T_K)


def _vogel_model(pwf_pr: np.ndarray, q_max: float) -> np.ndarray:
    """Vogel: q = q_max * (1 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)²)"""
    return q_max * (1.0 - 0.2 * pwf_pr - 0.8 * pwf_pr ** 2)


def _fit_andrade(temperature_c: list[float], viscosity_cp: list[float]) -> dict:
    """
    Fit Andrade viscosity model: ln(μ) = A + B/T_K.
    Returns fitted A, B, R², RMSE.
    PROVENANCE: CALIBRATED_MODEL
    """
    from scipy.optimize import curve_fit  # type: ignore

    T_K = np.array(temperature_c) + 273.15
    mu  = np.array(viscosity_cp)

    if len(T_K) < 3:
        raise ValueError("Need at least 3 temperature-viscosity pairs for Andrade fit.")
    if np.any(mu <= 0):
        raise ValueError("Viscosity values must be positive (> 0 cP).")
    if np.any(T_K <= 0):
        raise ValueError("Temperature values must be above absolute zero.")

    # Initial guess from current defaults
    p0 = [-14.17, 6968.65]
    popt, pcov = curve_fit(
        lambda T, A, B: _andrade_model(T, A, B),
        T_K, mu,
        p0=p0,
        maxfev=5000,
    )
    A_fit, B_fit = float(popt[0]), float(popt[1])

    mu_pred = _andrade_model(T_K, A_fit, B_fit)
    ss_res = float(np.sum((mu - mu_pred) ** 2))
    ss_tot = float(np.sum((mu - mu.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 1.0
    rmse = float(np.sqrt(np.mean((mu - mu_pred) ** 2)))
    perr = np.sqrt(np.diag(pcov))

    residuals = (mu - mu_pred).tolist()
    predicted = mu_pred.tolist()

    return {
        "model": "viscosity_andrade",
        "equation": "ln(μ) = A + B/T_K   →   μ = exp(A + B/T_K)",
        "params": {"A": round(A_fit, 6), "B": round(B_fit, 4)},
        "param_std_err": {"A": round(float(perr[0]), 6), "B": round(float(perr[1]), 4)},
        "r_squared": round(r2, 6),
        "rmse_cp": round(rmse, 4),
        "n_points": len(T_K),
        "temperature_c_range": [round(float(min(temperature_c)), 1), round(float(max(temperature_c)), 1)],
        "viscosity_cp_range": [round(float(min(viscosity_cp)), 2), round(float(max(viscosity_cp)), 2)],
        "predicted": [round(v, 4) for v in predicted],
        "residuals": [round(v, 4) for v in residuals],
        "reference": "[A] Andrade 1930; [B] ASTM D341-20",
        "provenance": "CALIBRATED_MODEL",
    }


def _fit_vogel(pwf_kpa: list[float], oil_rate_m3d: list[float],
               reservoir_pressure_kpa: Optional[float] = None) -> dict:
    """
    Fit Vogel IPR: q = q_max * (1 - 0.2*Pwf/Pr - 0.8*(Pwf/Pr)²).
    If reservoir_pressure_kpa not provided, uses max(pwf_kpa)*1.1 as estimate.
    PROVENANCE: CALIBRATED_MODEL
    """
    from scipy.optimize import curve_fit  # type: ignore

    pwf = np.array(pwf_kpa)
    q   = np.array(oil_rate_m3d)

    if len(pwf) < 3:
        raise ValueError("Need at least 3 (Pwf, q) pairs for Vogel IPR fit.")
    if np.any(q < 0):
        raise ValueError("Oil rate values must be non-negative.")

    Pr = reservoir_pressure_kpa if (reservoir_pressure_kpa and reservoir_pressure_kpa > 0) \
         else float(np.max(pwf)) * 1.1
    if Pr <= 0:
        raise ValueError("Reservoir pressure must be positive.")

    pwf_pr = pwf / Pr

    popt, pcov = curve_fit(
        lambda x, q_max: _vogel_model(x, q_max),
        pwf_pr, q,
        p0=[float(np.max(q)) * 1.2],
        bounds=([0.0], [np.inf]),
        maxfev=5000,
    )
    q_max_fit = float(popt[0])

    q_pred = _vogel_model(pwf_pr, q_max_fit)
    ss_res = float(np.sum((q - q_pred) ** 2))
    ss_tot = float(np.sum((q - q.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 1.0
    rmse = float(np.sqrt(np.mean((q - q_pred) ** 2)))
    perr = np.sqrt(np.diag(pcov))

    residuals = (q - q_pred).tolist()
    predicted = q_pred.tolist()

    return {
        "model": "ipr_vogel",
        "equation": "q = q_max * (1 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)²)",
        "params": {"q_max_m3d": round(q_max_fit, 4), "reservoir_pressure_kpa": round(Pr, 1)},
        "param_std_err": {"q_max_m3d": round(float(perr[0]), 6)},
        "r_squared": round(r2, 6),
        "rmse_m3d": round(rmse, 6),
        "n_points": len(pwf),
        "pwf_kpa_range": [round(float(min(pwf_kpa)), 1), round(float(max(pwf_kpa)), 1)],
        "q_range_m3d": [round(float(min(oil_rate_m3d)), 4), round(float(max(oil_rate_m3d)), 4)],
        "predicted": [round(v, 6) for v in predicted],
        "residuals": [round(v, 6) for v in residuals],
        "reference": "[C] Vogel 1968",
        "provenance": "CALIBRATED_MODEL",
    }


# ── Public API ────────────────────────────────────────────────────────────────

def upload(
    filename: str,
    file_bytes: bytes,
    calibration_target: str,
    column_map: dict[str, str],
) -> dict:
    """
    Parse CSV or Excel file, validate mapped columns, store profile.

    Parameters
    ----------
    filename          : original filename (used to infer format)
    file_bytes        : raw file contents
    calibration_target: "viscosity_andrade" or "ipr_vogel"
    column_map        : maps required logical name → actual CSV column name
                        e.g. {"temperature_c": "Temp_degC", "viscosity_cp": "Visc_cP"}

    Returns profile metadata dict.
    PROVENANCE: USER_UPLOADED
    """
    if calibration_target not in REQUIRED_COLUMNS:
        raise ValueError(
            f"Unknown calibration target {calibration_target!r}. "
            f"Valid: {list(REQUIRED_COLUMNS.keys())}"
        )

    # Parse CSV or Excel
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "csv"
    try:
        if ext in ("xlsx", "xls"):
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            headers = [str(c).strip() if c is not None else "" for c in rows[0]]
            data_rows = rows[1:]
            raw_data: dict[str, list] = {h: [] for h in headers}
            for row in data_rows:
                for h, v in zip(headers, row):
                    raw_data[h].append(v)
        else:
            import csv
            reader = csv.DictReader(io.StringIO(file_bytes.decode("utf-8", errors="replace")))
            raw_data = {k: [] for k in (reader.fieldnames or [])}
            for row in reader:
                for k, v in row.items():
                    raw_data[k].append(v)
    except Exception as e:
        raise ValueError(f"Failed to parse file: {e}") from e

    # Validate column_map
    required = REQUIRED_COLUMNS[calibration_target]
    for logical_col in required:
        if logical_col not in column_map:
            raise ValueError(
                f"Missing column mapping for required column {logical_col!r}. "
                f"Required: {sorted(required)}"
            )
        actual_col = column_map[logical_col]
        if actual_col not in raw_data:
            raise ValueError(
                f"Mapped column {actual_col!r} not found in file. "
                f"Available columns: {list(raw_data.keys())}"
            )

    # Extract numeric data for required columns
    extracted: dict[str, list[float]] = {}
    for logical_col in required:
        actual_col = column_map[logical_col]
        values = []
        for raw_v in raw_data[actual_col]:
            try:
                v = float(raw_v)
                if not math.isfinite(v):
                    continue
                values.append(v)
            except (TypeError, ValueError):
                continue
        if len(values) < 3:
            raise ValueError(
                f"Column {actual_col!r} → {logical_col!r}: "
                f"only {len(values)} valid numeric values found (need ≥ 3)."
            )
        extracted[logical_col] = values

    # Also extract optional reservoir_pressure_kpa if available (for IPR)
    opt_extra: dict[str, float] = {}
    if calibration_target == "ipr_vogel" and "reservoir_pressure_kpa" in column_map:
        act = column_map["reservoir_pressure_kpa"]
        if act in raw_data:
            vals = [float(v) for v in raw_data[act]
                    if v is not None and str(v).strip() != "" and math.isfinite(float(str(v)))]
            if vals:
                opt_extra["reservoir_pressure_kpa"] = float(np.median(vals))

    profile_id = str(uuid.uuid4())[:8]
    profile = {
        "profile_id": profile_id,
        "filename": filename,
        "calibration_target": calibration_target,
        "column_map": column_map,
        "extracted_data": extracted,
        "opt_extra": opt_extra,
        "n_rows": min(len(v) for v in extracted.values()),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "fit_result": None,
        "active": False,
        "provenance": "USER_UPLOADED",
    }
    _profiles[profile_id] = profile
    logger.info(f"Uploaded profile {profile_id}: target={calibration_target}, n={profile['n_rows']}")
    return _profile_meta(profile)


def calibrate(profile_id: str) -> dict:
    """
    Run SciPy curve_fit on a previously uploaded profile.
    Stores fit result in the profile; returns full fit report.
    PROVENANCE: CALIBRATED_MODEL
    """
    if profile_id not in _profiles:
        raise KeyError(f"Profile {profile_id!r} not found. Upload data first.")

    p = _profiles[profile_id]
    target = p["calibration_target"]
    data = p["extracted_data"]
    opt_extra = p.get("opt_extra", {})

    try:
        if target == "viscosity_andrade":
            fit = _fit_andrade(data["temperature_c"], data["viscosity_cp"])
        elif target == "ipr_vogel":
            fit = _fit_vogel(
                data["pwf_kpa"],
                data["oil_rate_m3d"],
                opt_extra.get("reservoir_pressure_kpa"),
            )
        else:
            raise ValueError(f"Unknown calibration target: {target!r}")
    except Exception as e:
        raise ValueError(f"Curve fit failed: {e}") from e

    p["fit_result"] = fit
    logger.info(
        f"Calibrated profile {profile_id}: R²={fit['r_squared']:.4f}"
    )
    return {**_profile_meta(p), "fit_result": fit}


def list_profiles() -> list[dict]:
    """Return metadata for all stored profiles (no data arrays)."""
    return [_profile_meta(p) for p in _profiles.values()]


def get_profile(profile_id: str) -> dict:
    """Return full profile including fit result if available."""
    if profile_id not in _profiles:
        raise KeyError(f"Profile {profile_id!r} not found.")
    p = _profiles[profile_id]
    return {**_profile_meta(p), "fit_result": p["fit_result"]}


def activate_profile(profile_id: str) -> dict:
    """
    Mark a calibrated profile as active and apply its parameters to the
    simulator config live constants (in-process, not persisted to disk).

    PROVENANCE: CALIBRATED_MODEL
    NOTE: Affects ANDRADE_A/ANDRADE_B or PI_REFERENCE constants in memory only.
    Restarting the process resets them to file defaults.
    """
    if profile_id not in _profiles:
        raise KeyError(f"Profile {profile_id!r} not found.")

    p = _profiles[profile_id]
    if p["fit_result"] is None:
        raise ValueError(f"Profile {profile_id!r} has not been calibrated yet. "
                         "Call /data/calibrate first.")

    target = p["calibration_target"]
    fit = p["fit_result"]

    # Deactivate previous active profile for this target
    prev = _active_profile.get(target)
    if prev and prev in _profiles:
        _profiles[prev]["active"] = False

    # Activate this one
    p["active"] = True
    p["activated_at"] = datetime.now(timezone.utc).isoformat()
    _active_profile[target] = profile_id

    # Apply to simulator config (in-memory)
    applied: dict[str, float] = {}
    try:
        import simulator.config as cfg  # type: ignore
        if target == "viscosity_andrade":
            cfg.ANDRADE_A = fit["params"]["A"]
            cfg.ANDRADE_B = fit["params"]["B"]
            cfg.WALTHER_A = fit["params"]["A"]
            cfg.WALTHER_B = fit["params"]["B"]
            applied = {"ANDRADE_A": fit["params"]["A"], "ANDRADE_B": fit["params"]["B"]}
        elif target == "ipr_vogel":
            # Update PI reference from calibrated q_max
            cfg.PI_REFERENCE_M3_DAY_KPA = fit["params"]["q_max_m3d"] / max(
                fit["params"]["reservoir_pressure_kpa"], 1.0
            )
            applied = {"PI_REFERENCE_M3_DAY_KPA": cfg.PI_REFERENCE_M3_DAY_KPA}
    except Exception as e:
        logger.warning(f"Could not apply profile to config: {e}")

    logger.info(f"Activated profile {profile_id} for {target}: {applied}")
    return {
        **_profile_meta(p),
        "applied_params": applied,
        "fit_result": fit,
        "provenance": "CALIBRATED_MODEL",
        "note": (
            "Parameters applied in-memory. Restart process to reset to file defaults. "
            "NOT validated against real Baghewala lab data."
        ),
    }


# ── Sample data generator (used for /data/sample endpoint) ───────────────────

def make_sample_csv(target: str) -> str:
    """
    Generate a small synthetic CSV file for the given calibration target.
    Used by GET /data/sample to let users download a template.
    PROVENANCE: SYNTHETIC_HISTORICAL
    """
    import simulator.config as cfg  # type: ignore

    if target == "viscosity_andrade":
        temps = [40, 50, 60, 80, 100, 120, 150, 180]
        lines = ["temperature_c,viscosity_cp,source"]
        for t in temps:
            T_K = t + 273.15
            mu = math.exp(cfg.ANDRADE_A + cfg.ANDRADE_B / T_K)
            # Add small noise
            rng = np.random.default_rng(42 + int(t))
            mu_noisy = mu * (1 + rng.normal(0, 0.03))
            lines.append(f"{t},{mu_noisy:.2f},synthetic_lab")
        return "\n".join(lines)

    elif target == "ipr_vogel":
        lines = ["pwf_kpa,oil_rate_m3d,reservoir_pressure_kpa"]
        Pr = 4500.0
        q_max = 1.5
        pwfs = [500, 900, 1300, 1800, 2400, 3000, 3600, 4000]
        rng = np.random.default_rng(99)
        for pwf in pwfs:
            ratio = pwf / Pr
            q = q_max * (1 - 0.2 * ratio - 0.8 * ratio**2) * (1 + rng.normal(0, 0.02))
            q = max(0.0, q)
            lines.append(f"{pwf},{q:.4f},{Pr:.0f}")
        return "\n".join(lines)

    else:
        raise ValueError(f"Unknown target: {target!r}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _profile_meta(p: dict) -> dict:
    """Return metadata dict (no raw data arrays, no full fit residuals)."""
    fit = p["fit_result"]
    fit_summary = None
    if fit:
        fit_summary = {
            "model": fit["model"],
            "params": fit["params"],
            "r_squared": fit["r_squared"],
            "n_points": fit["n_points"],
            "provenance": fit["provenance"],
        }
        if "rmse_cp" in fit:
            fit_summary["rmse_cp"] = fit["rmse_cp"]
        if "rmse_m3d" in fit:
            fit_summary["rmse_m3d"] = fit["rmse_m3d"]

    return {
        "profile_id": p["profile_id"],
        "filename": p["filename"],
        "calibration_target": p["calibration_target"],
        "n_rows": p["n_rows"],
        "uploaded_at": p["uploaded_at"],
        "calibrated": fit is not None,
        "active": p.get("active", False),
        "activated_at": p.get("activated_at"),
        "fit_summary": fit_summary,
        "provenance": p["provenance"],
    }
