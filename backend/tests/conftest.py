"""
conftest.py — Pytest fixtures for InterviewAgent tests.

Provides:
- FastAPI TestClient pointed at the app
- DB isolation: each test gets a temp DB, cleaned up after
- Real LLM calls via API keys from .env
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Load .env from project root BEFORE importing backend modules
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from backend import db as db_module


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Use a temporary database for each test. Cleans up after."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name

    monkeypatch.setattr(db_module, "DB_PATH", Path(tmp_path))
    db_module.init_db()

    yield

    # Cleanup
    import os as _os
    try:
        _os.unlink(tmp_path)
    except OSError:
        pass


@pytest.fixture
def client(temp_db):
    """FastAPI TestClient with isolated DB."""
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def candidate_id(client):
    """Register a test candidate and return their ID."""
    resp = client.post("/candidate/register", json={"name": "Test Candidate"})
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.fixture
def session_id(client, candidate_id):
    """Start an interview and return the session ID."""
    resp = client.post("/session/start", json={
        "candidate_id": candidate_id,
        "role": "Software Engineer",
        "skills": ["Python", "System Design"],
    })
    assert resp.status_code == 200
    return resp.json()["session_id"]
