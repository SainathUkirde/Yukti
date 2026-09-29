"""
CSS Cycle schemas.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .provenance import ProvenanceTag, ProvenancedFloat


class CyclePhase(str):
    INJECTION = "injection"
    SOAK = "soak"
    PRODUCTION = "production"
    IDLE = "idle"


class CSSCycle(BaseModel):
    """Full record of one CSS cycle."""
    well_id: str
    cycle_number: int
    injection_start: datetime
    soak_start: Optional[datetime] = None
    production_start: Optional[datetime] = None
    cycle_end: Optional[datetime] = None

    # Inputs
    steam_volume_cwe_m3: ProvenancedFloat
    injection_pressure_kpa: ProvenancedFloat
    steam_quality_fraction: ProvenancedFloat
    soak_days: ProvenancedFloat

    # Outcomes
    peak_reservoir_temp_c: ProvenancedFloat
    cycle_oil_m3: ProvenancedFloat
    cycle_water_m3: ProvenancedFloat
    cycle_sor: ProvenancedFloat
    production_cutoff_wor: ProvenancedFloat
    cycle_duration_days: Optional[float] = None

    provenance: ProvenanceTag = ProvenanceTag.SYNTHETIC_HISTORICAL


class CycleCreateRequest(BaseModel):
    """Request body to start a new simulated CSS cycle."""
    well_id: str
    steam_volume_cwe_m3: float = Field(..., gt=0.0)
    injection_pressure_kpa: float = Field(..., gt=0.0)
    steam_quality_fraction: float = Field(..., ge=0.5, le=1.0)
    soak_days: float = Field(..., gt=0.0, le=90.0)
    production_cutoff_wor: float = Field(..., gt=1.0)
