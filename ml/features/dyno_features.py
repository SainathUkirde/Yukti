"""
ml/features/dyno_features.py
Feature extraction from dynamometer card (position, load) arrays.

These features replace raw card arrays for the fault classifier.
They are physics-meaningful and interpretable (used in Explainable AI output).

Feature groups:
  1. Load statistics  — peak, min, range, mean, std of surface and downhole loads
  2. Card area        — area of surface card (proportional to energy input per stroke)
  3. Shape features   — peak-to-peak asymmetry, load at mid-stroke, curvature
  4. Fillage proxy    — estimated from downhole card shape
  5. Rod float proxy  — ratio of downstroke mean load to upstroke mean load
  6. Pattern features — correlation between surface and downhole cards

References:
  Takacs, G. (2015) Sucker-Rod Pumping Handbook, Ch. 5-6.
  Lea, J.F. et al. (2008) Gas Well Deliquification, Elsevier.
"""
import numpy as np
from typing import Union


FEATURE_NAMES = [
    # Surface load stats
    "surf_peak_load_kn",
    "surf_min_load_kn",
    "surf_load_range_kn",
    "surf_load_mean_kn",
    "surf_load_std_kn",
    # Downhole load stats
    "dh_peak_load_kn",
    "dh_min_load_kn",
    "dh_load_range_kn",
    "dh_load_mean_kn",
    "dh_load_std_kn",
    # Card area (energy proxy)
    "surf_card_area",
    "dh_card_area",
    # Shape / asymmetry
    "load_at_mid_upstroke",
    "load_at_mid_downstroke",
    "upstroke_downstroke_ratio",
    "top_load_flatness",       # std of top 20% of loads (rod float flattens this)
    "bottom_load_variance",    # variance of bottom 20% of loads (gas/pound spikes)
    # Stroke geometry
    "stroke_range_m",
    "dh_stroke_range_m",
    "stroke_attenuation",      # dh_range / surf_range (wave damping)
    # Load gradient features
    "max_load_gradient",       # max d(load)/d(position) — fluid pound spike
    "min_load_gradient",       # most negative — impact spike
    # Cross-card correlation
    "surf_dh_correlation",
    # Scalar inputs (pass-through from operating conditions)
    "fillage_fraction",
    "peak_load_kn",
    "min_load_kn",
    "pump_efficiency_fraction",
    "rod_float_risk_ratio",
    "oil_viscosity_cp",
    "spm",
    "stroke_length_m",
]


def extract_features(
    surface_position_m: Union[list, np.ndarray],
    surface_load_kn: Union[list, np.ndarray],
    downhole_position_m: Union[list, np.ndarray],
    downhole_load_kn: Union[list, np.ndarray],
    fillage_fraction: float = 0.8,
    peak_load_kn: float = 0.0,
    min_load_kn: float = 0.0,
    pump_efficiency_fraction: float = 0.7,
    rod_float_risk_ratio: float = 0.5,
    oil_viscosity_cp: float = 100.0,
    spm: float = 5.0,
    stroke_length_m: float = 2.4,
) -> np.ndarray:
    """
    Extract a fixed-length feature vector from a dynamometer card.

    Returns
    -------
    np.ndarray  shape (len(FEATURE_NAMES),)  — all features in order of FEATURE_NAMES
    """
    sp = np.asarray(surface_position_m, dtype=float)
    sl = np.asarray(surface_load_kn, dtype=float)
    dp = np.asarray(downhole_position_m, dtype=float)
    dl = np.asarray(downhole_load_kn, dtype=float)
    n = len(sp)

    # Split into upstroke / downstroke halves
    half = n // 2
    up_load = sl[:half]
    dn_load = sl[half:]

    # ── Surface load stats ────────────────────────────────────────────────
    surf_peak = float(sl.max())
    surf_min = float(sl.min())
    surf_range = surf_peak - surf_min
    surf_mean = float(sl.mean())
    surf_std = float(sl.std())

    # ── Downhole load stats ───────────────────────────────────────────────
    dh_peak = float(dl.max())
    dh_min = float(dl.min())
    dh_range = dh_peak - dh_min
    dh_mean = float(dl.mean())
    dh_std = float(dl.std())

    # ── Card areas (shoelace / trapezoid) ─────────────────────────────────
    _trapz = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    surf_area = float(abs(_trapz(sl, sp)))
    dh_area = float(abs(_trapz(dl, dp)))

    # ── Shape features ────────────────────────────────────────────────────
    mid_up = float(up_load[len(up_load) // 2]) if len(up_load) > 0 else surf_mean
    mid_dn = float(dn_load[len(dn_load) // 2]) if len(dn_load) > 0 else surf_mean
    up_dn_ratio = float(up_load.mean() / max(abs(dn_load.mean()), 1e-6))

    # Top 20% of loads — rod floating flattens the top (load drops mid-upstroke)
    top_thresh = np.percentile(sl, 80)
    top_loads = sl[sl >= top_thresh]
    top_flatness = float(top_loads.std()) if len(top_loads) > 0 else 0.0

    # Bottom 20% of loads — gas interference and fluid pound add variance here
    bot_thresh = np.percentile(sl, 20)
    bot_loads = sl[sl <= bot_thresh]
    bot_variance = float(bot_loads.var()) if len(bot_loads) > 0 else 0.0

    # ── Stroke geometry ───────────────────────────────────────────────────
    stroke_range = float(sp.max() - sp.min())
    dh_stroke_range = float(dp.max() - dp.min()) if len(dp) > 0 else stroke_range
    stroke_atten = dh_stroke_range / max(stroke_range, 1e-6)

    # ── Load gradient (fluid pound → sharp negative gradient at bottom) ───
    if len(sl) > 1:
        grad = np.gradient(sl)
        max_grad = float(grad.max())
        min_grad = float(grad.min())
    else:
        max_grad = 0.0
        min_grad = 0.0

    # ── Cross-card correlation ────────────────────────────────────────────
    if len(sl) == len(dl) and sl.std() > 1e-9 and dl.std() > 1e-9:
        corr = float(np.corrcoef(sl, dl)[0, 1])
    else:
        corr = 1.0

    return np.array([
        surf_peak, surf_min, surf_range, surf_mean, surf_std,
        dh_peak, dh_min, dh_range, dh_mean, dh_std,
        surf_area, dh_area,
        mid_up, mid_dn, up_dn_ratio,
        top_flatness, bot_variance,
        stroke_range, dh_stroke_range, stroke_atten,
        max_grad, min_grad,
        corr,
        fillage_fraction, peak_load_kn, min_load_kn,
        pump_efficiency_fraction, rod_float_risk_ratio,
        oil_viscosity_cp, spm, stroke_length_m,
    ], dtype=float)


def extract_features_batch(df) -> np.ndarray:
    """
    Extract features from a DataFrame of dyno card records.
    Expected columns match dyno_cards_labeled.parquet schema.
    Returns ndarray shape (n_rows, n_features).
    """
    import pandas as pd
    rows = []
    for _, row in df.iterrows():
        feat = extract_features(
            surface_position_m=row["surface_position_m"],
            surface_load_kn=row["surface_load_kn"],
            downhole_position_m=row["downhole_position_m"],
            downhole_load_kn=row["downhole_load_kn"],
            fillage_fraction=float(row.get("fillage_fraction", 0.8)),
            peak_load_kn=float(row.get("peak_load_kn", 0.0)),
            min_load_kn=float(row.get("min_load_kn", 0.0)),
            pump_efficiency_fraction=float(row.get("pump_efficiency_fraction", 0.7)),
            rod_float_risk_ratio=float(row.get("rod_float_risk_ratio", 0.5)),
            oil_viscosity_cp=float(row.get("oil_viscosity_cp", 100.0)),
            spm=float(row.get("spm", 5.0)),
            stroke_length_m=float(row.get("stroke_length_m", 2.4)),
        )
        rows.append(feat)
    return np.vstack(rows)
