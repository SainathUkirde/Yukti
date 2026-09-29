"""
backend/app/db/models.py
SQLAlchemy ORM models for persisting simulation snapshots and alerts.
"""
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.database import Base


class WellRecord(Base):
    """Hourly snapshot of a well's state (persisted from live stream)."""
    __tablename__ = "well_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    well_id: Mapped[str] = mapped_column(String(20), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, default=datetime.utcnow)
    phase: Mapped[str] = mapped_column(String(20))
    cycle_number: Mapped[int] = mapped_column(Integer)
    reservoir_temp_c: Mapped[float] = mapped_column(Float)
    oil_viscosity_cp: Mapped[float] = mapped_column(Float)
    oil_rate_m3d: Mapped[float] = mapped_column(Float)
    water_cut_fraction: Mapped[float] = mapped_column(Float)
    sor: Mapped[float] = mapped_column(Float)
    spm: Mapped[float] = mapped_column(Float)
    pump_efficiency: Mapped[float] = mapped_column(Float)
    kwh_per_bbl: Mapped[float] = mapped_column(Float)
    rod_float_risk: Mapped[float] = mapped_column(Float)
    goodman_ratio: Mapped[float] = mapped_column(Float)
    active_fault: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provenance: Mapped[str] = mapped_column(String(30), default="SIMULATED_LIVE")


class CycleRecord(Base):
    """CSS cycle summary."""
    __tablename__ = "cycle_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    well_id: Mapped[str] = mapped_column(String(20), index=True)
    cycle_number: Mapped[int] = mapped_column(Integer)
    injection_start: Mapped[datetime] = mapped_column(DateTime)
    peak_temp_c: Mapped[float] = mapped_column(Float)
    steam_volume_m3: Mapped[float] = mapped_column(Float)
    cycle_oil_m3: Mapped[float] = mapped_column(Float)
    cycle_sor: Mapped[float] = mapped_column(Float)
    provenance: Mapped[str] = mapped_column(String(30), default="SIMULATED_LIVE")


class AlertRecord(Base):
    """Alert event log."""
    __tablename__ = "alert_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    well_id: Mapped[str] = mapped_column(String(20), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    severity: Mapped[str] = mapped_column(String(20))   # critical | warning | info
    message: Mapped[str] = mapped_column(Text)
    fault_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


# ── Feature 4: Trust Layer tables ────────────────────────────────────────────

class AuditRecord(Base):
    """
    Append-only audit log for recommendation approvals.
    Hash-chained: each entry stores SHA256(prev_hash || entry_content).
    Tampering with any row breaks the chain (detectable via GET /audit/verify).
    PROVENANCE: DEMO_RESULT — concept demonstration, not real authentication.
    """
    __tablename__ = "audit_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, default=datetime.utcnow)
    well_id: Mapped[str] = mapped_column(String(20), index=True)
    role: Mapped[str] = mapped_column(String(30))           # Operator | Engineer | Viewer
    recommendation_id: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(30))         # proposed|approved|rejected|applied|outcome_evaluated
    before_values: Mapped[str] = mapped_column(Text)        # JSON
    after_values: Mapped[str] = mapped_column(Text)         # JSON
    constraint_result: Mapped[str] = mapped_column(String(20))  # SAFE|CAUTION|UNSAFE
    approver: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text, default="")
    outcome_values: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON, filled later
    entry_hash: Mapped[str] = mapped_column(String(64))     # SHA256 hex
    prev_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)
    provenance: Mapped[str] = mapped_column(String(30), default="DEMO_RESULT")


class RecommendationState(Base):
    """
    Approval state machine for optimizer recommendations.
    States: proposed → approved/rejected → applied → outcome_evaluated
    No live simulation change is made without explicit approval.
    """
    __tablename__ = "recommendation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    well_id: Mapped[str] = mapped_column(String(20), index=True)
    state: Mapped[str] = mapped_column(String(30), default="proposed")
    verdict: Mapped[str] = mapped_column(String(20), default="SAFE")    # SAFE|CAUTION|UNSAFE
    confidence_low: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_high: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[str] = mapped_column(Text)               # full recommendation JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    safe_mode_active: Mapped[bool] = mapped_column(Boolean, default=False)
    provenance: Mapped[str] = mapped_column(String(30), default="DEMO_RESULT")
