"""
ml/features/production_features.py
Feature engineering for the production forecaster.

Creates lag features, rolling statistics, and physics-derived inputs
from the daily production history + SRP operating data.
"""
import numpy as np
import pandas as pd
from typing import Optional


TARGET_COLS = ["reservoir_temp_c", "oil_viscosity_cp", "oil_rate_m3d"]

LAG_DAYS = [1, 3, 7, 14]
ROLL_WINDOWS = [3, 7, 14]


def build_forecaster_features(
    prod_df: pd.DataFrame,
    srp_df: Optional[pd.DataFrame] = None,
    horizon: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build (X, y) feature and target DataFrames for the forecaster.

    Parameters
    ----------
    prod_df  : DataFrame   production_history with columns:
                           well_id, date, phase, oil_rate_m3d, water_cut_fraction,
                           reservoir_temp_c, sor, bottomhole_pressure_kpa, cycle_number
    srp_df   : DataFrame   srp_operating_data (optional, joined on well_id + date)
    horizon  : int         forecast horizon in days

    Returns
    -------
    X : pd.DataFrame  feature matrix
    y : pd.DataFrame  targets [reservoir_temp_c, oil_viscosity_cp, oil_rate_m3d]
                      shifted by `horizon` days (predict horizon days ahead)
    """
    # Only use production phase rows for training
    df = prod_df[prod_df["phase"] == "production"].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["well_id", "date"])

    # Add viscosity from physics (needed as target and feature)
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from simulator.wellbore.viscosity import viscosity_cp as _visc
    df["oil_viscosity_cp"] = df["reservoir_temp_c"].apply(lambda T: _visc(T))

    # Optionally join SRP data
    if srp_df is not None:
        srp = srp_df[["well_id", "timestamp", "spm", "kwh_per_bbl",
                       "pump_efficiency_fraction", "rod_float_risk_ratio"]].copy()
        srp["date"] = pd.to_datetime(srp["timestamp"]).dt.date
        srp["date"] = pd.to_datetime(srp["date"])
        srp_daily = srp.groupby(["well_id", "date"]).mean(numeric_only=True).reset_index()
        df = df.merge(srp_daily, on=["well_id", "date"], how="left")

    feature_rows = []
    target_rows = []

    for well_id, wdf in df.groupby("well_id"):
        wdf = wdf.sort_values("date").reset_index(drop=True)

        # Lag features
        for col in ["oil_rate_m3d", "reservoir_temp_c", "oil_viscosity_cp",
                    "water_cut_fraction", "sor"]:
            for lag in LAG_DAYS:
                wdf[f"{col}_lag{lag}"] = wdf[col].shift(lag)

        # Rolling statistics
        for col in ["oil_rate_m3d", "reservoir_temp_c", "oil_viscosity_cp"]:
            for window in ROLL_WINDOWS:
                wdf[f"{col}_roll{window}_mean"] = wdf[col].rolling(window).mean()
                wdf[f"{col}_roll{window}_std"] = wdf[col].rolling(window).std().fillna(0)

        # Physics-derived features
        wdf["t_prod_days"] = (wdf["date"] - wdf["date"].min()).dt.days
        wdf["cycle_number"] = wdf["cycle_number"].fillna(1)

        # SRP features (if available)
        for col in ["spm", "kwh_per_bbl", "pump_efficiency_fraction", "rod_float_risk_ratio"]:
            if col not in wdf.columns:
                wdf[col] = np.nan

        # Target: values at t + horizon
        for col in TARGET_COLS:
            wdf[f"target_{col}"] = wdf[col].shift(-horizon)

        # Drop rows without full context (first max_lag rows and last horizon rows)
        max_lag = max(LAG_DAYS)
        wdf = wdf.iloc[max_lag:].dropna(subset=[f"target_{c}" for c in TARGET_COLS])

        feat_cols = (
            [f"{c}_lag{l}" for c in ["oil_rate_m3d", "reservoir_temp_c",
                                      "oil_viscosity_cp", "water_cut_fraction"]
             for l in LAG_DAYS]
            + [f"{c}_roll{w}_{s}" for c in ["oil_rate_m3d", "reservoir_temp_c",
                                              "oil_viscosity_cp"]
               for w in ROLL_WINDOWS for s in ["mean", "std"]]
            + ["t_prod_days", "cycle_number", "bottomhole_pressure_kpa",
               "spm", "kwh_per_bbl", "pump_efficiency_fraction", "rod_float_risk_ratio"]
        )
        # Keep only columns that exist
        feat_cols = [c for c in feat_cols if c in wdf.columns]
        sub_X = wdf[feat_cols].copy()
        sub_X["well_id"] = well_id

        target_cols_full = [f"target_{c}" for c in TARGET_COLS]
        sub_y = wdf[target_cols_full].copy()
        sub_y.columns = TARGET_COLS

        feature_rows.append(sub_X)
        target_rows.append(sub_y)

    X = pd.concat(feature_rows, ignore_index=True)
    y = pd.concat(target_rows, ignore_index=True)
    X = X.fillna(X.median(numeric_only=True))
    return X, y


def get_feature_names(X: pd.DataFrame) -> list[str]:
    """Return feature column names excluding well_id."""
    return [c for c in X.columns if c != "well_id"]
