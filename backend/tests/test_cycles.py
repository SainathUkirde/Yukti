"""
backend/tests/test_cycles.py
Tests for /cycles endpoints.
"""
import pytest


def test_list_cycles(client):
    resp = client.get("/cycles/")
    assert resp.status_code == 200
    body = resp.json()
    assert "cycles" in body
    assert "count" in body


def test_list_cycles_filtered(client, first_well_id):
    resp = client.get("/cycles/", params={"well_id": first_well_id})
    assert resp.status_code == 200
    body = resp.json()
    assert "cycles" in body


def test_get_latest_cycle(client, first_well_id):
    resp = client.get(f"/cycles/{first_well_id}/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["well_id"] == first_well_id
    assert "cycle_number" in body
    assert "phase" in body
    assert body["provenance"] == "SIMULATED_LIVE"


def test_post_cycle_log(client, first_well_id):
    payload = {
        "well_id": first_well_id,
        "cycle_number": 99,
        "steam_volume_cwe_m3": 400.0,
        "injection_pressure_kpa": 4000.0,
        "soak_days": 14.0,
        "peak_temp_c": 120.0,
        "heated_zone_radius_m": 25.0,
        "cum_oil_m3": 120.0,
        "cum_steam_m3": 550.0,
        "sor": 4.58,
        "duration_days": 90.0,
    }
    resp = client.post("/cycles/", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "logged"
    assert body["entry"]["cycle_number"] == 99
