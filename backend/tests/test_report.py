"""
backend/tests/test_report.py
Tests for /report endpoint.
"""
import pytest


def test_report_json(client, first_well_id):
    resp = client.get(f"/report/{first_well_id}/json")
    assert resp.status_code == 200
    body = resp.json()
    assert "well_state" in body
    assert body["well_state"]["well_id"] == first_well_id
    assert body["provenance"] == "SIMULATED_LIVE"


def test_report_pdf(client, first_well_id):
    resp = client.get(f"/report/{first_well_id}")
    # 200 if reportlab installed, 501 if not
    assert resp.status_code in (200, 501)
    if resp.status_code == 200:
        assert resp.headers["content-type"] == "application/pdf"
        assert len(resp.content) > 1000  # minimal PDF size


def test_report_not_found(client):
    resp = client.get("/report/NOPE_XYZ")
    assert resp.status_code == 404
