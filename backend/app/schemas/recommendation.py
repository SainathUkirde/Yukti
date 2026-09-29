"""
Recommendation & Explanation schemas.
Every recommendation includes a structured explanation (Explainable AI).
"""
from typing import Optional
from pydantic import BaseModel, Field
from .provenance import ProvenanceTag


class TopFactor(BaseModel):
    """One contributing factor in the explanation."""
    factor_name: str
    value: float
    unit: str
    direction: str = Field(..., description="increasing | decreasing | stable")
    impact: str = Field(..., description="How this factor drives the recommendation")


class ConstraintChecked(BaseModel):
    """Result of checking one engineering constraint."""
    name: str
    passed: bool
    value: float
    limit: float
    unit: str


class Explanation(BaseModel):
    """
    Structured explainability output for a recommendation.
    Example: "Viscosity up 18% over 6 h -> reduce SPM 6 -> 4.8 to avoid rod floating;
               expected +4% pump efficiency."
    """
    reason_text: str = Field(..., description="Human-readable reason for the recommendation")
    top_factors: list[TopFactor]
    constraints_checked: list[ConstraintChecked]
    method: str = Field(..., description="Physics chain / model used to derive this")


class Recommendation(BaseModel):
    """
    A single actionable recommendation from the optimizer or rule engine.
    Carries full explainability and before/after context.
    """
    recommendation_id: str
    well_id: str
    action: str = Field(..., description="Short action description, e.g. 'Reduce SPM from 6 to 4.8'")
    category: str = Field(..., description="css | srp | joint")
    priority: str = Field(..., description="critical | high | medium | low")

    # Before/After
    before: dict = Field(..., description="Current parameter values")
    after: dict = Field(..., description="Recommended parameter values")
    expected_gain: dict = Field(..., description="Expected KPI changes, e.g. {pump_efficiency: +4%}")

    # Explainability
    explanation: Explanation

    # Status
    status: str = Field("pending", description="pending | applied | ignored")
    provenance: ProvenanceTag = ProvenanceTag.OPTIMIZER_RECOMMENDATION

    class Config:
        json_schema_extra = {
            "example": {
                "recommendation_id": "rec_001",
                "well_id": "W01",
                "action": "Reduce SPM from 6.0 to 4.8",
                "category": "srp",
                "priority": "high",
                "before": {"spm": 6.0, "oil_rate_m3d": 12.3, "pump_efficiency": 0.61},
                "after": {"spm": 4.8, "oil_rate_m3d": 13.1, "pump_efficiency": 0.68},
                "expected_gain": {"pump_efficiency": "+11%", "kwh_per_bbl": "-8%", "rod_float_risk": "-45%"},
                "explanation": {
                    "reason_text": (
                        "Viscosity increased 18% over the last 6 hours as reservoir cools. "
                        "At current SPM=6, rod fall speed (0.31 m/s) is below plunger demand (0.38 m/s), "
                        "indicating imminent rod floating. Reducing SPM to 4.8 restores safety margin. "
                        "Expected pump efficiency gain: +11%."
                    ),
                    "top_factors": [
                        {"factor_name": "oil_viscosity_cp", "value": 850, "unit": "cP",
                         "direction": "increasing", "impact": "Increases rod drag, reduces fall speed"},
                        {"factor_name": "reservoir_temp_c", "value": 62, "unit": "C",
                         "direction": "decreasing", "impact": "Cooling drives viscosity rise"},
                        {"factor_name": "rod_fall_speed_ms", "value": 0.31, "unit": "m/s",
                         "direction": "decreasing", "impact": "Approaching plunger demand threshold"}
                    ],
                    "constraints_checked": [
                        {"name": "rod_allowable_stress", "passed": True, "value": 0.72, "limit": 1.0, "unit": "Goodman ratio"},
                        {"name": "vfd_frequency", "passed": True, "value": 35.0, "limit": 60.0, "unit": "Hz"},
                        {"name": "min_fillage", "passed": True, "value": 0.72, "limit": 0.60, "unit": "fraction"}
                    ],
                    "method": "Viscosity-SPM coupling via Gibbs wave equation + Stokes rod drag"
                },
                "status": "pending",
                "provenance": "OPTIMIZER_RECOMMENDATION"
            }
        }
