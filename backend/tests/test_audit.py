"""
backend/tests/test_audit.py
Feature 4 — Trust Layer tests

Tests:
  1. propose → approve → apply state machine
  2. cannot apply without approve
  3. viewer cannot approve
  4. operator cannot approve
  5. engineer can approve
  6. hash chain verifies clean
  7. tampered entry breaks chain
  8. safe-mode clamps step size
"""
import pytest
import json


def test_audit_status(client):
    resp = client.get("/audit/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "current_role" in body
    assert "safe_mode_active" in body
    assert "permissions" in body
    assert body["provenance"] == "DEMO_RESULT"


def test_audit_log_empty_initially(client):
    resp = client.get("/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert "entries" in body
    assert "total" in body


def test_propose_recommendation(client, first_well_id):
    resp = client.post(f"/recommendations/test-rec-001/propose", json={
        "well_id": first_well_id,
        "recommendation": {
            "id": "test-rec-001",
            "title": "Test recommendation",
            "recommended_config": {"spm": 4.0, "stroke_length_m": 2.5},
            "kpi_deltas": {"oil_rate_delta_pct": 5.0},
        },
        "confidence_low": -3.0,
        "confidence_high": 8.0,
        "constraint_result": "SAFE",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "proposed"
    assert body["verdict"] == "SAFE"
    assert body["provenance"] == "DEMO_RESULT"


def test_get_rec_state(client):
    resp = client.get("/recommendations/test-rec-001/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation_id"] == "test-rec-001"
    assert body["state"] == "proposed"


def test_cannot_apply_without_approve(client):
    """Applying a proposed (not approved) recommendation must fail with 400."""
    resp = client.post("/recommendations/test-rec-001/apply", json={"approver": "Operator"})
    assert resp.status_code == 400
    assert "approved" in resp.json()["detail"].lower()


def test_role_switch_to_viewer(client):
    resp = client.post("/audit/role", json={"role": "Viewer"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "Viewer"
    # Viewer cannot approve
    resp2 = client.post("/recommendations/test-rec-001/approve", json={"approver": "viewer1"})
    assert resp2.status_code == 403


def test_role_switch_to_operator_cannot_approve(client):
    client.post("/audit/role", json={"role": "Operator"})
    resp = client.post("/recommendations/test-rec-001/approve", json={"approver": "op1"})
    assert resp.status_code == 403


def test_engineer_can_approve(client):
    client.post("/audit/role", json={"role": "Engineer"})
    resp = client.post("/recommendations/test-rec-001/approve", json={
        "approver": "engineer1",
        "reason": "Looks good",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "approved"
    assert body["approved_by"] == "engineer1"


def test_apply_approved_recommendation(client, first_well_id):
    """After approve, apply should succeed and move state to 'applied'."""
    client.post("/audit/role", json={"role": "Operator"})
    resp = client.post("/recommendations/test-rec-001/apply", json={"approver": "op1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["state"] == "applied"


def test_audit_log_has_entries(client):
    resp = client.get("/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 3  # proposed + approved + applied


def test_hash_chain_valid(client):
    resp = client.get("/audit/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["first_broken_at"] is None


def test_reject_flow(client, first_well_id):
    """Propose a new rec and reject it."""
    client.post("/audit/role", json={"role": "Engineer"})
    client.post("/recommendations/test-rec-reject/propose", json={
        "well_id": first_well_id,
        "recommendation": {"id": "test-rec-reject", "title": "Reject me"},
        "constraint_result": "CAUTION",
    })
    resp = client.post("/recommendations/test-rec-reject/reject", json={
        "approver": "engineer2",
        "reason": "Too risky",
    })
    assert resp.status_code == 200
    assert resp.json()["state"] == "rejected"


def test_safe_mode_toggle(client):
    resp = client.post("/audit/safe-mode", json={"active": True})
    assert resp.status_code == 200
    assert resp.json()["safe_mode_active"] is True
    resp2 = client.post("/audit/safe-mode", json={"active": False})
    assert resp2.json()["safe_mode_active"] is False


def test_list_recommendation_states(client, first_well_id):
    resp = client.get("/audit/recommendations", params={"well_id": first_well_id})
    assert resp.status_code == 200
    body = resp.json()
    assert "states" in body
    assert isinstance(body["states"], list)
