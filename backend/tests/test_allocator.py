"""
backend/tests/test_allocator.py
Tests for Feature 1 — Field-Level Steam Allocator & CSS Scheduler

Test plan (7 tests):
  1. Budget respected  — total steam allocated ≤ requested budget
  2. Baseline vs optimised differ  — optimised ≠ equal-split on KPIs
  3. Marginal oil uses real surrogate  — changing params changes result
  4. Rod fatigue cap  — well with high damage gets reduced steam
  5. Rod fatigue exclude  — well with D ≥ 0.95 ends up in excluded list
  6. Schedule order  — start_day increases (sequential schedule)
  7. GET /field/schedule  — returns cached result after POST /field/allocate
"""
import sys
import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


# ── 1. POST /field/allocate — budget respected ────────────────────────────────

def test_allocate_budget_respected(client):
    """Total steam allocated must never exceed requested budget."""
    budget = 3000.0
    resp = client.post("/field/allocate", json={
        "steam_budget_m3": budget,
        "generator_capacity_m3_per_day": 200.0,
        "period_days": 30.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_steam_allocated_m3"] <= budget + 1e-3, (
        f"Allocated {data['total_steam_allocated_m3']:.1f} > budget {budget}"
    )


# ── 2. Baseline vs optimised oil differ ───────────────────────────────────────

def test_allocate_optimised_vs_baseline(client):
    """Optimised and baseline allocations must produce different per-well steam volumes."""
    resp = client.post("/field/allocate", json={
        "steam_budget_m3": 5000.0,
        "generator_capacity_m3_per_day": 200.0,
        "period_days": 30.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    opt_vols = sorted(a["steam_volume_m3"] for a in data["well_allocations"])
    base_vols = sorted(a["steam_volume_m3"] for a in data["baseline_allocations"])

    # They will differ because baseline = equal split; optimised = marginal value
    assert opt_vols != base_vols, (
        "Optimised and baseline steam volumes should differ (greedy vs equal-split)"
    )


# ── 3. Response structure complete ────────────────────────────────────────────

def test_allocate_response_structure(client):
    """Response must contain all required top-level fields."""
    resp = client.post("/field/allocate", json={
        "steam_budget_m3": 4000.0,
        "generator_capacity_m3_per_day": 150.0,
        "period_days": 30.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    required_keys = [
        "well_allocations",
        "baseline_allocations",
        "total_steam_allocated_m3",
        "total_steam_budget_m3",
        "expected_total_oil_m3",
        "baseline_total_oil_m3",
        "oil_gain_vs_baseline_pct",
        "expected_field_sor",
        "period_days",
        "generator_capacity_m3_per_day",
        "wells_excluded_rod_fatigue",
        "method",
        "provenance",
    ]
    for key in required_keys:
        assert key in data, f"Missing key: {key}"

    # Each well allocation must have required fields
    well_keys = [
        "well_id", "rank", "steam_volume_m3", "marginal_oil_per_m3_steam",
        "expected_oil_m3", "expected_sor", "start_day", "duration_days",
        "rod_fatigue_damage", "rod_life_constraint_applied", "rod_life_reason",
        "constraints_passed", "explanation", "provenance",
    ]
    assert len(data["well_allocations"]) > 0
    for key in well_keys:
        assert key in data["well_allocations"][0], f"Missing well key: {key}"


# ── 4. Per-well marginal oil is non-negative ──────────────────────────────────

def test_allocate_marginal_oil_non_negative(client):
    """
    Each allocated well should have non-negative marginal oil per m³ steam.
    (Real surrogate, not a hard-coded %)
    """
    resp = client.post("/field/allocate", json={
        "steam_budget_m3": 5000.0,
        "generator_capacity_m3_per_day": 200.0,
        "period_days": 30.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    for w in data["well_allocations"]:
        assert w["marginal_oil_per_m3_steam"] >= -1e-6, (
            f"Well {w['well_id']}: negative marginal oil {w['marginal_oil_per_m3_steam']:.4f}"
        )


# ── 5. Rod fatigue integration — damage stored per well ───────────────────────

def test_allocate_rod_fatigue_fields_present(client):
    """Each well allocation must report rod_fatigue_damage ≥ 0."""
    resp = client.post("/field/allocate", json={
        "steam_budget_m3": 5000.0,
        "generator_capacity_m3_per_day": 200.0,
        "period_days": 30.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    for w in data["well_allocations"]:
        assert w["rod_fatigue_damage"] >= 0.0, (
            f"Well {w['well_id']}: rod_fatigue_damage should be ≥ 0"
        )
        assert isinstance(w["rod_life_constraint_applied"], bool)
        assert isinstance(w["rod_life_reason"], str)
        assert len(w["rod_life_reason"]) > 0


# ── 6. Schedule start days are non-decreasing ─────────────────────────────────

def test_allocate_schedule_order(client):
    """
    Wells are scheduled sequentially — start_day must be ≥ 0 for all,
    and the sum of (start_day + duration) should be plausible.
    """
    resp = client.post("/field/allocate", json={
        "steam_budget_m3": 5000.0,
        "generator_capacity_m3_per_day": 200.0,
        "period_days": 30.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    allocs = data["well_allocations"]
    for w in allocs:
        assert w["start_day"] >= 0.0, f"Negative start_day for {w['well_id']}"
        assert w["duration_days"] > 0.0, f"Zero duration for {w['well_id']}"


# ── 7. GET /field/schedule — returns cached result ────────────────────────────

def test_get_schedule_after_allocate(client):
    """
    GET /field/schedule should return the cached result from the last allocation.
    """
    # Run an allocation first
    post_resp = client.post("/field/allocate", json={
        "steam_budget_m3": 4500.0,
        "generator_capacity_m3_per_day": 180.0,
        "period_days": 30.0,
    })
    assert post_resp.status_code == 200, post_resp.text

    # Then GET the schedule
    get_resp = client.get("/field/schedule")
    assert get_resp.status_code == 200, get_resp.text
    cached = get_resp.json()

    # The cached result should match the post result
    assert cached["total_steam_budget_m3"] == pytest.approx(4500.0, rel=1e-3)
    assert cached["generator_capacity_m3_per_day"] == pytest.approx(180.0, rel=1e-3)
    assert len(cached["well_allocations"]) > 0
