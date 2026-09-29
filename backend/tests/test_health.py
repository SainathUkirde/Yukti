"""
backend/tests/test_health.py
Tests for health and offline-check endpoints.
"""
import pytest


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "uptime_s" in body
    assert body["wells_active"] > 0


def test_health_ready(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_offline_check(client):
    resp = client.get("/offline-check")
    assert resp.status_code == 200
    assert resp.json()["online"] is True
