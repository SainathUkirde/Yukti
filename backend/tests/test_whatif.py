"""
backend/tests/test_whatif.py
Tests for /whatif endpoint.
"""
import pytest


def test_whatif_spm_change(client, first_well_id):
    resp = client.post("/whatif/", json={
        "well_id": first_well_id,
        "spm": 3.0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "baseline" in body
    assert "projected" in body
    assert "deltas" in body
    assert "narrative" in body
    assert body["provenance"] == "DEMO_RESULT"


def test_whatif_css_change(client, first_well_id):
    resp = client.post("/whatif/", json={
        "well_id": first_well_id,
        "steam_volume_cwe_m3": 500.0,
        "soak_days": 18.0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "overrides_applied" in body
    overrides = body["overrides_applied"]
    assert "steam_volume_cwe_m3" in overrides
    assert "soak_days" in overrides


def test_whatif_empty_overrides(client, first_well_id):
    """Sending no overrides should return 400."""
    resp = client.post("/whatif/", json={"well_id": first_well_id})
    assert resp.status_code == 400


def test_whatif_well_not_found(client):
    resp = client.post("/whatif/", json={
        "well_id": "NOPE_XYZ",
        "spm": 3.0,
    })
    assert resp.status_code == 404
