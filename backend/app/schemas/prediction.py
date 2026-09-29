"""
Prediction / ML model output schemas.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .provenance import ProvenanceTag, ProvenancedFloat


class FaultClass(str):
    NORMAL = "normal"
    ROD_FLOATING = "rod_floating"
    PUMP_OFF = "pump_off"
    GAS_INTERFERENCE = "gas_interference"
    FLUID_POUND = "fluid_pound"
    PUMP_UNSETTING = "pump_unsetting"


class FaultClassification(BaseModel):
    """Output of the dyno-card fault classifier."""
    well_id: str
    timestamp: datetime
    predicted_fault: str = Field(..., description="normal | rod_floating | pump_off | gas_interference | fluid_pound | pump_unsetting")
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_probabilities: dict[str, float] = Field(..., description="Probability for each fault class")
    top_features: list[dict] = Field(..., description="Top contributing card features")
    provenance: ProvenanceTag = ProvenanceTag.ML_PREDICTION


class ForecastPoint(BaseModel):
    """One point in the forecast horizon."""
    timestamp: datetime
    reservoir_temp_c: ProvenancedFloat
    oil_viscosity_cp: ProvenancedFloat
    oil_rate_m3d: ProvenancedFloat


class ForecastResult(BaseModel):
    """N-day ahead forecast from the gradient boosting forecaster."""
    well_id: str
    forecast_generated_at: datetime
    horizon_days: int
    points: list[ForecastPoint]
    model_version: str
    provenance: ProvenanceTag = ProvenanceTag.ML_PREDICTION


class FailureRiskScore(BaseModel):
    """Rod failure risk score from the risk model."""
    well_id: str
    timestamp: datetime
    risk_score: float = Field(..., ge=0.0, le=100.0, description="0=safe, 100=imminent failure")
    risk_level: str = Field(..., description="low | medium | high | critical")
    top_contributing_factors: list[dict] = Field(
        ...,
        description="Top factors with SHAP-style attribution"
    )
    goodman_ratio: float = Field(..., description="Goodman criterion ratio; >1.0 = violation")
    provenance: ProvenanceTag = ProvenanceTag.ML_PREDICTION


class WhatIfRequest(BaseModel):
    """Request body for the /whatif endpoint."""
    well_id: str
    # Any subset of these overrides the current well config
    steam_volume_cwe_m3: Optional[float] = None
    injection_pressure_kpa: Optional[float] = None
    steam_quality_fraction: Optional[float] = None
    soak_days: Optional[float] = None
    production_cutoff_wor: Optional[float] = None
    spm: Optional[float] = None
    stroke_length_m: Optional[float] = None
    vfd_frequency_hz: Optional[float] = None
    horizon_days: int = Field(7, ge=1, le=90)


class WhatIfResult(BaseModel):
    """
    Result of propagating a parameter change through the full model chain.
    Changes flow: input change -> reservoir T -> viscosity -> IPR -> pump behavior -> KPIs.
    """
    well_id: str
    changed_parameters: dict
    # Full model chain outputs
    delta_reservoir_temp_c: float
    delta_viscosity_pct: float
    delta_oil_rate_pct: float
    delta_pump_fillage_pct: float
    delta_pump_efficiency_pct: float
    delta_sor_pct: float
    delta_kwh_per_bbl_pct: float
    delta_failure_risk_pts: float
    rod_floating_risk_after: bool
    constraint_violations: list[dict] = []
    propagation_chain: list[str] = Field(
        ...,
        description="Step-by-step chain showing how the change propagated"
    )
    provenance: ProvenanceTag = ProvenanceTag.DEMO_RESULT
    method: str = "Fast surrogate physics propagation"
