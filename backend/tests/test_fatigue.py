"""
backend/tests/test_fatigue.py
Feature 2 — Rod Fatigue tests

Tests (8):
  1. Field fatigue endpoint returns all wells
  2. Single well fatigue endpoint returns required fields
  3. Damage increases with higher SPM (more cycles)
  4. Damage increases with higher stress amplitude (more load)
  5. Fault injection multiplies damage (rod_floating > normal)
  6. Reset zeroes damage
  7. Urgency is 'low' for fresh well
  8. Remaining life p10 < p50 (conservative bound respected)
"""
import pytest
from backend.app.services import fatigue_service as svc


# ── Unit tests (no HTTP client needed) ───────────────────────────────────────

def test_update_fatigue_produces_positive_damage():
    """Any production tick must produce D > 0."""
    svc.reset_fatigue("TEST_UNIT")
    state = svc.update_fatigue("TEST_UNIT", peak_load_kn=50.0, min_load_kn=10.0,
                               spm=5.0, dt_days=0.001736)
    assert state.cumulative_damage > 0


def test_damage_increases_with_spm():
    """Higher SPM = more cycles per tick = higher damage increment."""
    svc.reset_fatigue("TEST_SPM_A"); svc.reset_fatigue("TEST_SPM_B")
    svc.update_fatigue("TEST_SPM_A", 50, 10, spm=3.0, dt_days=0.001736)
    svc.update_fatigue("TEST_SPM_B", 50, 10, spm=9.0, dt_days=0.001736)
    da = svc.compute_fatigue_report("TEST_SPM_A")["cumulative_damage"]
    db = svc.compute_fatigue_report("TEST_SPM_B")["cumulative_damage"]
    assert db > da, f"Higher SPM should give more damage: {db} > {da}"


def test_damage_increases_with_stress():
    """Higher load amplitude → higher stress → damage increases faster."""
    svc.reset_fatigue("TEST_STRESS_A"); svc.reset_fatigue("TEST_STRESS_B")
    for _ in range(10):
        svc.update_fatigue("TEST_STRESS_A", peak_load_kn=30, min_load_kn=15, spm=5, dt_days=0.001736)
        svc.update_fatigue("TEST_STRESS_B", peak_load_kn=80, min_load_kn=5,  spm=5, dt_days=0.001736)
    da = svc.compute_fatigue_report("TEST_STRESS_A")["cumulative_damage"]
    db = svc.compute_fatigue_report("TEST_STRESS_B")["cumulative_damage"]
    assert db > da, f"Higher stress should accumulate more damage: {db} > {da}"


def test_rod_floating_fault_increases_damage():
    """rod_floating fault multiplier (1.6x) must produce more damage than normal."""
    svc.reset_fatigue("TEST_FAULT_NORMAL"); svc.reset_fatigue("TEST_FAULT_FLOAT")
    for _ in range(5):
        svc.update_fatigue("TEST_FAULT_NORMAL", 50, 10, 5, 0.001736, active_fault=None)
        svc.update_fatigue("TEST_FAULT_FLOAT",  50, 10, 5, 0.001736, active_fault="rod_floating")
    dn = svc.compute_fatigue_report("TEST_FAULT_NORMAL")["cumulative_damage"]
    df = svc.compute_fatigue_report("TEST_FAULT_FLOAT")["cumulative_damage"]
    assert df > dn, f"rod_floating should damage more: {df} > {dn}"


def test_fluid_pound_highest_damage():
    """fluid_pound (2.0x) must produce more damage than rod_floating (1.6x)."""
    svc.reset_fatigue("TEST_FP"); svc.reset_fatigue("TEST_RF")
    for _ in range(5):
        svc.update_fatigue("TEST_FP", 50, 10, 5, 0.001736, active_fault="fluid_pound")
        svc.update_fatigue("TEST_RF", 50, 10, 5, 0.001736, active_fault="rod_floating")
    dfp = svc.compute_fatigue_report("TEST_FP")["cumulative_damage"]
    drf = svc.compute_fatigue_report("TEST_RF")["cumulative_damage"]
    assert dfp > drf, f"fluid_pound should be worse than rod_floating"


def test_reset_zeroes_damage():
    """After reset, cumulative_damage must be 0."""
    svc.update_fatigue("TEST_RESET", 50, 10, 5, 0.001736)
    svc.reset_fatigue("TEST_RESET")
    r = svc.compute_fatigue_report("TEST_RESET")
    assert r["cumulative_damage"] == 0.0


def test_fresh_well_urgency_is_low():
    """A new well with zero damage must have urgency='low'."""
    svc.reset_fatigue("TEST_FRESH")
    r = svc.compute_fatigue_report("TEST_FRESH")
    assert r["urgency"] == "low"


def test_p10_less_than_p50():
    """Conservative p10 remaining life must be ≤ p50."""
    svc.reset_fatigue("TEST_LIFE")
    for _ in range(20):
        svc.update_fatigue("TEST_LIFE", 60, 5, 6, 0.001736)
    r = svc.compute_fatigue_report("TEST_LIFE")
    assert r["remaining_life_days_p10"] <= r["remaining_life_days_p50"]


# ── Integration tests (HTTP client) ──────────────────────────────────────────

def test_field_fatigue_endpoint(client):
    """GET /field/fatigue must return all wells."""
    resp = client.get("/field/fatigue")
    assert resp.status_code == 200
    body = resp.json()
    assert "wells" in body
    assert "count" in body
    assert body["count"] > 0
    w = body["wells"][0]
    assert "cumulative_damage" in w
    assert "remaining_life_days_p50" in w
    assert "urgency" in w
    assert "recommended_workover_window" in w


def test_single_well_fatigue_endpoint(client, first_well_id):
    """GET /wells/{id}/fatigue must return required fields."""
    resp = client.get(f"/wells/{first_well_id}/fatigue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["well_id"] == first_well_id
    assert "cumulative_damage" in body
    assert "remaining_life_fraction" in body
    assert "remaining_life_days_p10" in body
    assert "remaining_life_days_p50" in body
    assert "recommended_workover_window" in body
    assert "provenance" in body
    assert "method" in body
    # p10 ≤ p50 via API
    assert body["remaining_life_days_p10"] <= body["remaining_life_days_p50"]


def test_fatigue_reset_endpoint(client, first_well_id):
    """POST /wells/{id}/fatigue/reset must zero the damage."""
    resp = client.post(f"/wells/{first_well_id}/fatigue/reset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reset"] is True
    # After reset, damage should be 0
    r2 = client.get(f"/wells/{first_well_id}/fatigue").json()
    assert r2["cumulative_damage"] == 0.0


def test_fatigue_not_found(client):
    resp = client.get("/wells/NOPE_XYZ/fatigue")
    assert resp.status_code == 404
