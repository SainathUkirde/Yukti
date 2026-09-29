"""
backend/tests/test_assistant.py
Tests for /assistant endpoint.
"""
import pytest


def test_assistant_topics(client):
    resp = client.get("/assistant/topics")
    assert resp.status_code == 200
    body = resp.json()
    assert "topics" in body
    assert len(body["topics"]) > 0


def test_assistant_css_question(client):
    resp = client.post("/assistant/", json={"query": "What is CSS and how does it work?"})
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert len(body["answer"]) > 50
    assert body["provenance"] == "DEMO_RESULT"
    assert "disclaimer" in body


def test_assistant_rod_float(client):
    resp = client.post("/assistant/", json={"query": "Explain rod floating and N_rf"})
    assert resp.status_code == 200
    body = resp.json()
    assert "rod" in body["answer"].lower() or "N_rf" in body["answer"]


def test_assistant_viscosity(client):
    resp = client.post("/assistant/", json={"query": "How does viscosity change with temperature?"})
    assert resp.status_code == 200
    body = resp.json()
    assert "andrade" in body["answer"].lower() or "viscosity" in body["answer"].lower()


def test_assistant_with_well_context(client, first_well_id):
    resp = client.post("/assistant/", json={
        "query": "What is the current SOR?",
        "well_id": first_well_id,
        "include_well_context": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["well_id"] == first_well_id
    assert "answer" in body


def test_assistant_empty_query(client):
    resp = client.post("/assistant/", json={"query": ""})
    assert resp.status_code == 400
