"""
backend/tests/test_recommendations.py
Tests for /recommendations endpoint.
"""
import pytest


def test_recommendations_all(client):
    resp = client.get("/recommendations/")
    assert resp.status_code == 200
    body = resp.json()
    assert "recommendations" in body
    assert "count" in body
    assert "critical_count" in body
    assert isinstance(body["recommendations"], list)


def test_recommendations_by_well(client, first_well_id):
    resp = client.get("/recommendations/", params={"well_id": first_well_id})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["recommendations"], list)
    for rec in body["recommendations"]:
        assert rec["well_id"] == first_well_id
        assert rec["priority"] in ("critical", "high", "medium", "info")
        assert "title" in rec
        assert "action" in rec
        assert "provenance" in rec


def test_recommendations_priority_filter(client):
    resp = client.get("/recommendations/", params={"priority": "critical"})
    assert resp.status_code == 200
    body = resp.json()
    for rec in body["recommendations"]:
        assert rec["priority"] == "critical"
