"""
backend/tests/conftest.py
Shared pytest fixtures for backend API tests.
"""
import sys
import os
import pytest
from fastapi.testclient import TestClient

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def client():
    """
    Create a TestClient with the full FastAPI app.
    The lifespan starts the simulation service.
    """
    from backend.app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        import time
        time.sleep(2.0)  # allow first tick(s) to complete
        yield c


@pytest.fixture(scope="session")
def first_well_id(client):
    """Return the first active well ID."""
    resp = client.get("/wells/")
    assert resp.status_code == 200
    wells = resp.json()["wells"]
    assert len(wells) > 0
    return wells[0]["well_id"]
