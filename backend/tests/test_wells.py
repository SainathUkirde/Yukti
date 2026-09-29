"""
backend/tests/test_wells.py
Tests for /wells endpoints.
"""
import pytest


def test_list_wells(client):
    resp = client.get("/wells/")
    assert resp.status_code == 200
    body = resp.json()
    assert "wells" in body
    assert body["count"] > 0
    well = body["wells"][0]
    assert "well_id" in well
    assert "phase" in well
    assert "status_color" in well
    assert well["status_color"] in ("green", "amber", "red")
    assert "provenance" in well


def test_get_well(client, first_well_id):
    resp = client.get(f"/wells/{first_well_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["well_id"] == first_well_id
    assert "reservoir_temp_c" in body
    # ProvenancedFloat structure
    pf = body["reservoir_temp_c"]
    assert isinstance(pf, dict)
    assert "value" in pf
    assert pf["provenance"] == "SIMULATED_LIVE"
    assert "active_fault" in body
    assert "surface_position_m" in body
    assert isinstance(body["surface_position_m"], list)


def test_get_well_not_found(client):
    resp = client.get("/wells/NONEXISTENT_WELL_XYZ")
    assert resp.status_code == 404


def test_get_well_history(client, first_well_id):
    resp = client.get(f"/wells/{first_well_id}/history", params={"n": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert "ticks" in body
    assert isinstance(body["ticks"], list)
    # Should have at least 1 tick after 2s warmup
    assert len(body["ticks"]) >= 1
    tick = body["ticks"][0]
    assert "reservoir_temp_c" in tick
    assert "oil_rate_m3d" in tick
    assert "active_fault" in tick


def test_get_well_params(client, first_well_id):
    resp = client.get(f"/wells/{first_well_id}/params")
    assert resp.status_code == 200
    body = resp.json()
    assert body["well_id"] == first_well_id
    assert body["provenance"] == "SYNTHETIC_HISTORICAL"
    assert "permeability_md" in body
    assert "api_gravity" in body
