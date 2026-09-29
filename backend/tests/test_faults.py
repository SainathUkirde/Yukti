"""
backend/tests/test_faults.py
Tests for /faults endpoints.
"""
import pytest


def test_fault_types(client):
    resp = client.get("/faults/types")
    assert resp.status_code == 200
    body = resp.json()
    assert "fault_types" in body
    ids = [ft["id"] for ft in body["fault_types"]]
    assert "rod_floating" in ids
    assert "pump_off" in ids
    assert "gas_interference" in ids


def test_inject_fault(client, first_well_id):
    resp = client.post("/faults/inject", json={
        "well_id": first_well_id,
        "fault_type": "rod_floating",
        "ramp_ticks": 5,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "injected"
    assert body["fault_type"] == "rod_floating"
    assert body["provenance"] == "DEMO_RESULT"


def test_inject_invalid_fault(client, first_well_id):
    resp = client.post("/faults/inject", json={
        "well_id": first_well_id,
        "fault_type": "NONEXISTENT_FAULT",
        "ramp_ticks": 5,
    })
    assert resp.status_code == 400


def test_inject_fault_well_not_found(client):
    resp = client.post("/faults/inject", json={
        "well_id": "NOPE_XYZ",
        "fault_type": "rod_floating",
        "ramp_ticks": 5,
    })
    assert resp.status_code == 404


def test_resolve_fault(client, first_well_id):
    resp = client.post("/faults/resolve", json={
        "well_id": first_well_id,
        "fault_type": "rod_floating",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
