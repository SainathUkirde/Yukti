"""
Provenance model — shared across all API schemas.
Every number returned by the API carries a provenance tag.
"""
from enum import Enum
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ProvenanceTag(str, Enum):
    """
    FIELD_FACT           — Real, verifiable value from the problem statement or published field data.
    LITERATURE_ASSUMPTION— Parameter taken from published petroleum engineering literature.
    SYNTHETIC_HISTORICAL — Pre-generated synthetic history from the physics simulator.
    SIMULATED_LIVE       — Live tick produced by the running simulator.
    ML_PREDICTION        — Output of an ML model; carries uncertainty bounds.
    OPTIMIZER_RECOMMENDATION — Output of the joint CSS+SRP optimizer.
    DEMO_RESULT          — Baseline vs optimized comparison from paired simulator runs.
    """
    FIELD_FACT = "FIELD_FACT"
    LITERATURE_ASSUMPTION = "LITERATURE_ASSUMPTION"
    SYNTHETIC_HISTORICAL = "SYNTHETIC_HISTORICAL"
    SIMULATED_LIVE = "SIMULATED_LIVE"
    ML_PREDICTION = "ML_PREDICTION"
    OPTIMIZER_RECOMMENDATION = "OPTIMIZER_RECOMMENDATION"

    USER_UPLOADED = "USER_UPLOADED"

    DEMO_RESULT = "DEMO_RESULT"


# Badge colors for the frontend (also exported in /api response metadata)
PROVENANCE_COLORS: dict[ProvenanceTag, str] = {
    ProvenanceTag.FIELD_FACT: "#22C55E",
    ProvenanceTag.LITERATURE_ASSUMPTION: "#3B82F6",
    ProvenanceTag.SYNTHETIC_HISTORICAL: "#A855F7",
    ProvenanceTag.SIMULATED_LIVE: "#F59E0B",
    ProvenanceTag.USER_UPLOADED: "#14B8A6",

    ProvenanceTag.ML_PREDICTION: "#06B6D4",
    ProvenanceTag.OPTIMIZER_RECOMMENDATION: "#F97316",
    ProvenanceTag.DEMO_RESULT: "#EF4444",
}


class UncertaintyBounds(BaseModel):
    """Prediction interval for ML outputs."""
    low: float = Field(..., description="Lower bound (e.g. 10th percentile)")
    high: float = Field(..., description="Upper bound (e.g. 90th percentile)")


class ProvenancedFloat(BaseModel):
    """A float value with full provenance metadata."""
    value: float
    provenance: ProvenanceTag
    unit: Optional[str] = None
    uncertainty: Optional[UncertaintyBounds] = None
    method: Optional[str] = Field(
        None,
        description="For DEMO_RESULT: description of the method used to produce this value."
    )
    source: Optional[str] = Field(
        None,
        description="For FIELD_FACT / LITERATURE_ASSUMPTION: citation."
    )


class ProvenancedStr(BaseModel):
    """A string value with full provenance metadata."""
    value: str
    provenance: ProvenanceTag
    source: Optional[str] = None
