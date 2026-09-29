"""
optimizer/tests/test_constraints.py
Tests for the constraint engine.

Expected behavior:
  1. Injection pressure above fracture pressure → critical violation
  2. Safe injection pressure → no violation
  3. SPM outside [1, 12] → critical violation
  4. Rod floating N_rf >= 1.0 → critical violation
  5. All constraints pass for a valid well configuration
  6. Violations are returned with correct structure (id, severity, unit)
"""
import pytest
import sys, os
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from optimizer.constraints.constraint_engine import ConstraintEngine, ConstraintViolation


@pytest.fixture
def engine():
    return ConstraintEngine(well_depth_m=800.0, rod_diameter_m=0.022225)


SAFE_PARAMS = dict(
    injection_pressure_kpa=4000.0,
    steam_volume_cwe_m3=500.0,
    soak_days=14.0,
    steam_quality=0.75,
    production_cutoff_wor=10.0,
    spm=5.0,
    stroke_length_m=2.4,
    vfd_frequency_hz=45.0,
    peak_load_kn=20.0,
    min_load_kn=5.0,
    pump_fillage=0.75,
    oil_viscosity_cp=80.0,
    rod_string_length_m=800.0,
)


class TestConstraintEngine:

    def test_all_safe_params_pass(self, engine):
        """A valid well configuration must pass all constraints."""
        result = engine.check(**SAFE_PARAMS)
        assert result.passed, (
            f"Expected all constraints to pass for safe params, "
            f"but got violations: {[v.name for v in result.violations]}"
        )

    def test_fracture_pressure_violation(self, engine):
        """Injection pressure above fracture pressure → critical violation."""
        params = dict(SAFE_PARAMS)
        params["injection_pressure_kpa"] = engine.fracture_pressure_kpa + 500.0
        result = engine.check(**params)
        assert not result.passed
        c1_violations = [v for v in result.violations if v.constraint_id == "C1"]
        assert len(c1_violations) == 1
        assert c1_violations[0].severity == "critical"

    def test_safe_injection_pressure_passes(self, engine):
        """Injection pressure well below fracture → C1 passes."""
        params = dict(SAFE_PARAMS)
        params["injection_pressure_kpa"] = engine.fracture_pressure_kpa * 0.7
        result = engine.check(**params)
        c1_checks = [c for c in result.checks if c.constraint_id == "C1"]
        assert c1_checks[0].passed

    def test_spm_too_high_violates(self, engine):
        """SPM > 12 must trigger a critical violation (C6)."""
        params = dict(SAFE_PARAMS)
        params["spm"] = 15.0
        result = engine.check(**params)
        c6 = [v for v in result.violations if v.constraint_id == "C6"]
        assert len(c6) == 1
        assert c6[0].severity == "critical"

    def test_rod_floating_violation(self, engine):
        """High viscosity + high SPM → rod floating violation (C11)."""
        params = dict(SAFE_PARAMS)
        params["spm"] = 9.0
        params["oil_viscosity_cp"] = 2000.0  # high viscosity → N_rf >> 1
        result = engine.check(**params)
        c11 = [v for v in result.violations if v.constraint_id == "C11"]
        assert len(c11) == 1, (
            "Expected C11 rod floating violation at μ=2000 cP, SPM=9"
        )
        assert c11[0].severity == "critical"

    def test_violation_structure(self, engine):
        """Each violation has required fields."""
        params = dict(SAFE_PARAMS)
        params["injection_pressure_kpa"] = engine.fracture_pressure_kpa + 1000.0
        result = engine.check(**params)
        for v in result.violations:
            assert hasattr(v, "constraint_id")
            assert hasattr(v, "name")
            assert hasattr(v, "severity")
            assert v.severity in ("critical", "warning")
            assert hasattr(v, "recommended_value")
            assert hasattr(v, "limit_value")
            assert hasattr(v, "unit")

    def test_11_constraints_checked(self, engine):
        """All 11 constraints must be checked (some may skip if peak_load=0)."""
        result = engine.check(**SAFE_PARAMS)
        # At minimum C1-C8, C10, C11 are always checked (C9 if peak_load>0)
        assert len(result.checks) >= 10

    def test_critical_violations_separate_from_warnings(self, engine):
        """critical_violations and warning_violations are correctly separated."""
        params = dict(SAFE_PARAMS)
        params["injection_pressure_kpa"] = engine.fracture_pressure_kpa + 500.0
        params["soak_days"] = 100.0  # too long → warning
        result = engine.check(**params)
        assert len(result.critical_violations) >= 1
        crits = {v.constraint_id for v in result.critical_violations}
        warns = {v.constraint_id for v in result.warning_violations}
        assert len(crits & warns) == 0  # no overlap
