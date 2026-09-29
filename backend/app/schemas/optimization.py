"""
Optimization request/response schemas — joint CSS + SRP optimizer.
"""
from typing import Optional
from pydantic import BaseModel, Field
from .provenance import ProvenanceTag, ProvenancedFloat


class OptimizationRequest(BaseModel):
    """
    Request the joint CSS+SRP optimizer for a specific well.
    Optionally constrain the search space.
    """
    well_id: str
    horizon_days: int = Field(30, ge=1, le=365, description="Optimization horizon")
    objective: str = Field(
        "min_cost_per_bbl",
        description="min_cost_per_bbl | max_oil | min_sor"
    )
    # Optional bounds override (uses defaults from constraint engine if not set)
    max_steam_volume_m3: Optional[float] = None
    max_injection_pressure_kpa: Optional[float] = None
    min_soak_days: Optional[float] = None
    max_spm: Optional[float] = None


class ConstraintViolation(BaseModel):
    """A single constraint violation in the recommended parameters."""
    constraint_name: str
    description: str
    recommended_value: float
    limit_value: float
    severity: str = Field(..., description="warning | critical")


class RecommendedCSS(BaseModel):
    """Recommended CSS cycle parameters from the joint optimizer."""
    steam_volume_cwe_m3: ProvenancedFloat
    injection_pressure_kpa: ProvenancedFloat
    steam_quality_fraction: ProvenancedFloat
    soak_days: ProvenancedFloat
    production_cutoff_wor: ProvenancedFloat


class RecommendedSRP(BaseModel):
    """Recommended SRP operating parameters from the joint optimizer."""
    spm: ProvenancedFloat
    stroke_length_m: ProvenancedFloat
    vfd_frequency_hz: ProvenancedFloat


class BaselineVsOptimized(BaseModel):
    """
    Side-by-side comparison of current-practice heuristics vs AI-optimized settings.
    Method is documented; results are labeled DEMO_RESULT.
    """
    method: str = Field(
        ...,
        description="Description of how both scenarios were run (e.g. 'Paired simulator runs over 30-day horizon')"
    )

    # Baseline (current heuristics)
    baseline_oil_m3: ProvenancedFloat
    baseline_sor: ProvenancedFloat
    baseline_kwh_per_bbl: ProvenancedFloat
    baseline_pump_efficiency: ProvenancedFloat
    baseline_failure_risk: ProvenancedFloat
    baseline_cost_per_bbl_inr: ProvenancedFloat

    # Optimized
    optimized_oil_m3: ProvenancedFloat
    optimized_sor: ProvenancedFloat
    optimized_kwh_per_bbl: ProvenancedFloat
    optimized_pump_efficiency: ProvenancedFloat
    optimized_failure_risk: ProvenancedFloat
    optimized_cost_per_bbl_inr: ProvenancedFloat

    # Deltas (all DEMO_RESULT)
    delta_oil_pct: ProvenancedFloat
    delta_sor_pct: ProvenancedFloat
    delta_energy_pct: ProvenancedFloat
    delta_risk_pct: ProvenancedFloat
    delta_cost_inr_per_day: ProvenancedFloat
    steam_tonnes_saved_per_cycle: ProvenancedFloat


class OptimizationResult(BaseModel):
    """Full response from the joint optimizer endpoint."""
    well_id: str
    recommended_css: RecommendedCSS
    recommended_srp: RecommendedSRP
    baseline_vs_optimized: BaselineVsOptimized
    constraint_violations: list[ConstraintViolation] = []
    provenance: ProvenanceTag = ProvenanceTag.OPTIMIZER_RECOMMENDATION
