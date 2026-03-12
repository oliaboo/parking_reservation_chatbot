"""Tests for the admin REST API (reservation requests)."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from src.admin_api.app import app
from src.config import PROJECT_ROOT
from src.db.sqlite_db import SQLiteDB, get_db

_SEED_PATH = str(PROJECT_ROOT / "data" / "seed_data.json")


@pytest.fixture
def temp_db():
    """Provide a temporary DB with schema and optional seed."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = SQLiteDB(db_path=path, seed_path=_SEED_PATH)
    yield db
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def client(temp_db):
    """Provide a test client with get_db returning temp_db."""
    import src.db.sqlite_db as db_mod

    db_mod._db = temp_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        db_mod._db = None


def test_list_requests_empty(client):
    """GET /requests returns empty list when no requests."""
    r = client.get("/requests")
    assert r.status_code == 200
    assert r.json() == []


def test_list_requests_with_filter(client, temp_db):
    """GET /requests?status=pending returns only pending."""
    temp_db.create_pending_request("alice", ["2025-03-10"])
    temp_db.create_pending_request("bob", ["2025-03-11"])
    rid = temp_db.create_pending_request("bob", ["2025-03-12"])
    temp_db.set_request_status(rid, "approved")

    r = client.get("/requests?status=pending")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(x["status"] == "pending" for x in data)

    r_all = client.get("/requests")
    assert r_all.status_code == 200
    assert len(r_all.json()) == 3


def test_get_request(client, temp_db):
    """GET /requests/{id} returns the request."""
    rid = temp_db.create_pending_request("alice", ["2025-03-10", "2025-03-11"])
    r = client.get(f"/requests/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == rid
    assert body["nickname"] == "alice"
    assert body["dates"] == ["2025-03-10", "2025-03-11"]
    assert body["status"] == "pending"
    assert "created_at" in body


def test_get_request_404(client):
    """GET /requests/99999 returns 404."""
    r = client.get("/requests/99999")
    assert r.status_code == 404


def test_patch_approve(client, temp_db):
    """PATCH /requests/{id} with status approved updates the request."""
    rid = temp_db.create_pending_request("bob", ["2025-04-01"])
    r = client.patch(f"/requests/{rid}", json={"status": "approved"})
    assert r.status_code == 200
    assert r.json() == {"id": rid, "status": "approved"}
    assert temp_db.get_request_status(rid) == "approved"


def test_patch_reject(client, temp_db):
    """PATCH /requests/{id} with status rejected updates the request."""
    rid = temp_db.create_pending_request("alice", ["2025-03-10"])
    r = client.patch(f"/requests/{rid}", json={"status": "rejected"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert temp_db.get_request_status(rid) == "rejected"


def test_patch_conflict_when_not_pending(client, temp_db):
    """PATCH on already approved/rejected request returns 409."""
    rid = temp_db.create_pending_request("alice", ["2025-03-10"])
    temp_db.set_request_status(rid, "approved")
    r = client.patch(f"/requests/{rid}", json={"status": "rejected"})
    assert r.status_code == 409


def test_patch_invalid_status(client, temp_db):
    """PATCH with invalid status returns 400."""
    rid = temp_db.create_pending_request("alice", ["2025-03-10"])
    r = client.patch(f"/requests/{rid}", json={"status": "invalid"})
    assert r.status_code == 422  # FastAPI validation error


def test_patch_404(client):
    """PATCH on unknown id returns 404."""
    r = client.patch("/requests/99999", json={"status": "approved"})
    assert r.status_code == 404
