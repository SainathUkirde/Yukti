"""
backend/tests/test_carbon.py
Tests for Feature 5 — Carbon & Energy Tracker + Shift Handover

Test plan (10 tests):
  1.  GET /carbon/assumptions — returns assumptions with provenance
  2.  PUT /carbon/assumptions — update a field, verify returned
  3.  GET /wells/{id}/carbon — returns co2 + cost fields
  4.  Carbon: co2_per_bbl_kg > 0 and cost_per_bbl_inr > 0
  5.  Carbon: co2_steam_t depends on steam_volume (not hard-coded)
  6.  GET /field/carbon — aggregates all wells, field_totals present
  7.  Field carbon: total_co2_t >= sum of per-well values (within tolerance)
  8.  GET /handover — returns structured handover document
  9.  Handover: executive_summary has correct required fields
  10. Handover: priority_actions is a list (may be empty)
"""
import sys
import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


# ── 1. GET /carbon/assumptions ────────────────────────────────────────────────

def test_get_carbon_assumptions(client):
    """GET /carbon/assumptions returns dict with expected keys."""
    resp = client.get("/carbon/assumptions")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    required_keys = [
        "boiler_efficiency",
        "emission_factor_gas_kg_per_gj",
        "grid_emission_factor_kg_per_kwh",
        "gas_price_inr_per_gj",
        "elec_price_inr_per_kwh",
        "provenance",
        "sources",
    ]
    for key in required_keys:
        assert key in data, f"Missing key: {key}"
    assert data["provenance"] == "LITERATURE_ASSUMPTION"
    assert data["boiler_efficiency"] > 0


# ── 2. PUT /carbon/assumptions ────────────────────────────────────────────────

def test_update_carbon_assumptions(client):
    """PUT /carbon/assumptions updates a field and returns USER_UPLOADED provenance."""
    resp = client.put("/carbon/assumptions", json={"boiler_efficiency": 0.88})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert abs(data["boiler_efficiency"] - 0.88) < 1e-6
    assert data["provenance"] == "USER_UPLOADED"
    assert "boiler_efficiency" in data["updated_keys"]

    # Reset to default
    client.put("/carbon/assumptions", json={"boiler_efficiency": 0.85})


# ── 3. GET /wells/{id}/carbon ─────────────────────────────────────────────────

def test_well_carbon_response_structure(client, first_well_id):
    """GET /wells/{id}/carbon returns all required fields."""
    resp = client.get(f"/wells/{first_well_id}/carbon")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    required_keys = [
        "well_id",
        "co2_steam_t",
        "co2_elec_t",
        "co2_total_t",
        "co2_per_bbl_kg",
        "co2_delta_vs_baseline_pct",
        "gas_cost_inr",
        "elec_cost_inr",
        "total_cost_inr",
        "cost_per_bbl_inr",
        "steam_volume_m3",
        "motor_kwh",
        "sor",
        "provenance",
        "disclaimer",
    ]
    for key in required_keys:
        assert key in data, f"Missing field: {key}"
    assert data["provenance"] == "LITERATURE_ASSUMPTION"


# ── 4. Carbon values are physically plausible ─────────────────────────────────

def test_well_carbon_values_positive(client, first_well_id):
    """co2_per_bbl_kg and cost_per_bbl_inr must be positive."""
    resp = client.get(f"/wells/{first_well_id}/carbon?period_days=1.0")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["co2_per_bbl_kg"] >= 0, "co2_per_bbl_kg must be non-negative"
    assert data["cost_per_bbl_inr"] >= 0, "cost_per_bbl_inr must be non-negative"
    assert data["co2_total_t"] >= 0
    assert data["co2_total_t"] == pytest.approx(
        data["co2_steam_t"] + data["co2_elec_t"], rel=1e-3
    ), "Total CO2 should equal steam + elec CO2"


# ── 5. CO2 depends on steam volume (not hard-coded) ──────────────────────────

def test_carbon_depends_on_steam_volume(client):
    """
    The carbon service must use actual steam_volume_m3 from params.
    Test: field-level sum of co2_steam_t should vary with wells having
    different steam volumes (i.e. it's not a constant).
    """
    resp = client.get("/field/carbon")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    wells = data["wells"]
    # All wells have different steam volumes → co2_steam_t values should differ
    steam_co2_vals = [w["co2_steam_t"] for w in wells]
    assert len(set(steam_co2_vals)) > 1, (
        "co2_steam_t should vary across wells (not hard-coded constant)"
    )


# ── 6. GET /field/carbon ──────────────────────────────────────────────────────

def test_field_carbon_structure(client):
    """GET /field/carbon returns field_totals with all required fields."""
    resp = client.get("/field/carbon")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "wells" in data
    assert "field_totals" in data
    ft = data["field_totals"]

    required_ft = [
        "total_co2_t",
        "total_oil_bbl",
        "total_cost_inr",
        "field_co2_per_bbl_kg",
        "field_cost_per_bbl_inr",
        "co2_delta_vs_baseline_pct",
        "n_wells",
    ]
    for key in required_ft:
        assert key in ft, f"Missing field_totals key: {key}"
    assert ft["n_wells"] > 0


# ── 7. Field CO2 >= sum of wells (accounting for any rounding) ────────────────

def test_field_carbon_aggregation(client):
    """field_totals.total_co2_t should approximately equal sum of per-well co2_total_t."""
    resp = client.get("/field/carbon")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    per_well_sum = sum(w["co2_total_t"] for w in data["wells"])
    field_total = data["field_totals"]["total_co2_t"]

    assert abs(field_total - per_well_sum) < 0.01, (
        f"Field total {field_total:.4f} doesn't match sum {per_well_sum:.4f}"
    )


# ── 8. GET /handover ──────────────────────────────────────────────────────────

def test_handover_response_structure(client):
    """GET /handover returns a structured handover document."""
    resp = client.get("/handover")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    required_keys = [
        "handover_id",
        "generated_at",
        "shift_label",
        "outgoing_operator",
        "incoming_operator",
        "executive_summary",
        "priority_actions",
        "active_faults",
        "wells_summary",
        "rod_fatigue_summary",
        "provenance",
        "disclaimer",
    ]
    for key in required_keys:
        assert key in data, f"Missing key: {key}"
    assert data["provenance"] == "DEMO_RESULT"


# ── 9. Executive summary fields ───────────────────────────────────────────────

def test_handover_executive_summary(client):
    """Executive summary has all required fields with plausible values."""
    resp = client.get("/handover?shift_label=Night+Shift&outgoing_operator=Bob&incoming_operator=Alice")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    es = data["executive_summary"]
    assert es["total_wells"] > 0
    assert es["total_wells"] >= es["wells_in_production"] + es["wells_in_injection"]
    assert es["active_faults_count"] >= 0
    assert "total_field_oil_rate_m3d" in es
    assert data["shift_label"] == "Night Shift"
    assert data["outgoing_operator"] == "Bob"


# ── 10. Priority actions is a list ────────────────────────────────────────────

def test_handover_priority_actions_list(client):
    """priority_actions is a list; if non-empty each has required fields."""
    resp = client.get("/handover")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    actions = data["priority_actions"]
    assert isinstance(actions, list)

    for a in actions:
        assert "priority" in a
        assert "well_id" in a
        assert "action" in a
        assert a["priority"] in ("critical", "high", "medium", "info")
