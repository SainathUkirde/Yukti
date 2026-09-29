"""
backend/tests/test_predict.py
Tests for /predict endpoints.
"""
import pytest


def test_predict_all(client, first_well_id):
    resp = client.post(f"/predict/?well_id={first_well_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "fault_classification" in body
    assert "failure_risk" in body
    assert "production_forecast" in body

    fc = body["fault_classification"]
    assert "predicted_fault" in fc
    assert "confidence" in fc
    assert fc["provenance"] == "ML_PREDICTION"

    fr = body["failure_risk"]
    assert "risk_score" in fr
    assert "risk_level" in fr
    assert fr["risk_level"] in ("low", "medium", "high")
    assert fr["provenance"] == "ML_PREDICTION"


def test_predict_risk(client, first_well_id):
    resp = client.get(f"/predict/{first_well_id}/risk")
    assert resp.status_code == 200
    body = resp.json()
    assert "risk_score" in body
    assert 0.0 <= body["risk_score"] <= 100.0
    assert body["provenance"] == "ML_PREDICTION"


def test_predict_not_found(client):
    resp = client.post("/predict/?well_id=NOPE_XYZ")
    assert resp.status_code == 404
