"""
Well schemas — configuration, state, completion data.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .provenance import ProvenanceTag, ProvenancedFloat


class WellCompletion(BaseModel):
    """Static well completion and reservoir data."""
    well_id: str
    well_name: str
    latitude: float
    longitude: float
    total_depth_m: float = Field(..., description="Total well depth [m]")
    pay_zone_top_m: float
    pay_zone_bottom_m: float
    pay_thickness_m: float
    porosity_fraction: float = Field(..., ge=0.0, le=1.0)
    permeability_md: float = Field(..., gt=0.0)
    initial_reservoir_temp_c: float = Field(..., description="T_initial, FIELD_FACT: 46-48 C")
    initial_reservoir_pressure_kpa: float
    api_gravity: float = Field(..., description="API gravity, FIELD_FACT: 17-19")
    rod_string_grade: str = Field("D", description="API rod grade")
    pump_plunger_dia_mm: float
    provenance: ProvenanceTag = ProvenanceTag.LITERATURE_ASSUMPTION


class WellConfig(BaseModel):
    """
    Operating configuration for one well — passed to the simulator.
    All numeric ranges validated against engineering limits.
    """
    well_id: str
    # CSS parameters
    steam_volume_cwe_m3: float = Field(..., gt=0.0, description="Steam volume, cold-water-equivalent [m3]")
    injection_pressure_kpa: float = Field(..., gt=0.0)
    steam_quality_fraction: float = Field(..., ge=0.5, le=1.0)
    soak_days: float = Field(..., gt=0.0, le=90.0)
    production_cutoff_wor: float = Field(..., gt=0.0, description="Water-oil ratio cut-off to end cycle")
    # SRP parameters
    spm: float = Field(..., ge=1.0, le=15.0, description="Strokes per minute")
    stroke_length_m: float = Field(..., ge=0.5, le=5.0)
    vfd_frequency_hz: float = Field(..., ge=20.0, le=60.0)


class WellState(BaseModel):
    """
    Complete live state of one well — pushed over WebSocket every tick.
    Every numeric field carries provenance.
    """
    # Identity / timing
    well_id: str
    timestamp: datetime
    cycle_number: int
    phase: str = Field(..., description="injection | soak | production | idle")
    time_in_phase_days: float

    # Reservoir
    reservoir_temp_c: ProvenancedFloat
    heated_zone_radius_m: ProvenancedFloat
    reservoir_pressure_kpa: ProvenancedFloat
    oil_viscosity_cp: ProvenancedFloat

    # Production
    oil_rate_m3d: ProvenancedFloat
    water_rate_m3d: ProvenancedFloat
    gas_rate_m3d: ProvenancedFloat
    water_cut_fraction: ProvenancedFloat
    sor: ProvenancedFloat                     # Steam-Oil Ratio
    cum_oil_m3: ProvenancedFloat

    # SRP
    spm: ProvenancedFloat
    stroke_length_m: ProvenancedFloat
    vfd_frequency_hz: ProvenancedFloat
    polished_rod_load_kn: ProvenancedFloat
    peak_load_kn: ProvenancedFloat
    min_load_kn: ProvenancedFloat
    pump_fillage_fraction: ProvenancedFloat
    pump_efficiency_fraction: ProvenancedFloat
    motor_power_kw: ProvenancedFloat
    kwh_per_bbl: ProvenancedFloat

    # Risk & faults
    rod_failure_risk_score: ProvenancedFloat  # 0-100
    goodman_ratio: ProvenancedFloat           # ≤1.0 = safe
    active_fault: Optional[str] = None       # null | rod_floating | pump_off | ...
    active_alerts: list[str] = []

    # Dyno card (sampled 100-200 points)
    surface_position_m: list[float]
    surface_load_kn: list[float]
    downhole_position_m: list[float]
    downhole_load_kn: list[float]

    # Twin vs sensor deviation
    twin_sensor_deviation_pct: ProvenancedFloat

    # Config in use
    config: WellConfig


class WellSummary(BaseModel):
    """Lightweight summary for the multi-well overview grid."""
    well_id: str
    well_name: str
    phase: str
    oil_rate_m3d: float
    reservoir_temp_c: float
    rod_failure_risk_score: float
    active_fault: Optional[str]
    status_color: str = Field(..., description="green | amber | red")
    provenance: ProvenanceTag
