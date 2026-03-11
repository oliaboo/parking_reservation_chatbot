"""Simple tests for SQLite DB (users, reservations, availability)."""

import os

# Ensure project root is on path
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PROJECT_ROOT
from src.db.sqlite_db import SQLiteDB

_SEED_PATH = str(PROJECT_ROOT / "data" / "seed_data.json")


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = SQLiteDB(db_path=path, seed_path=_SEED_PATH)
    yield db
    try:
        os.unlink(path)
    except Exception:
        pass


def test_user_exists(temp_db):
    """Users table should have seeded nicknames."""
    assert temp_db.user_exists("alice") is True
    assert temp_db.user_exists("bob") is True
    assert temp_db.user_exists("unknown_user_xyz") is False


def test_add_and_get_reservations(temp_db):
    """Adding a reservation should make it appear for that nickname."""
    assert temp_db.add_reservation("alice", "2025-04-01") is True
    rows = temp_db.get_reservations_by_nickname("alice")
    assert any(r[0] == "2025-04-01" for r in rows)
    assert temp_db.get_reservations_by_nickname("bob") == []


def test_free_spaces(temp_db):
    """Availability table should return free_spaces for known dates."""
    free = temp_db.get_free_spaces("2025-03-10")
    assert free is not None
    assert free >= 0
    # Unknown date can be None or a value depending on seed
    free_unknown = temp_db.get_free_spaces("2099-01-01")
    assert free_unknown is None or free_unknown >= 0


def test_create_pending_request(temp_db):
    """create_pending_request returns request_id and row is queryable."""
    rid = temp_db.create_pending_request("alice", ["2025-03-10", "2025-03-11"])
    assert rid.isdigit()
    assert temp_db.get_request_status(rid) == "pending"
    details = temp_db.get_pending_request_details(rid)
    assert details is not None
    nickname, dates = details
    assert nickname == "alice"
    assert dates == ["2025-03-10", "2025-03-11"]


def test_get_request_status_unknown(temp_db):
    """get_request_status returns None for unknown id."""
    assert temp_db.get_request_status("99999") is None
    assert temp_db.get_request_status("0") is None


def test_set_request_status(temp_db):
    """set_request_status updates only pending requests."""
    rid = temp_db.create_pending_request("bob", ["2025-04-01"])
    assert temp_db.get_request_status(rid) == "pending"
    assert temp_db.set_request_status(rid, "approved") is True
    assert temp_db.get_request_status(rid) == "approved"
    # Idempotent update from pending is no-op after first update
    assert temp_db.set_request_status(rid, "rejected") is False
    assert temp_db.get_request_status(rid) == "approved"


def test_get_pending_request_details_unknown(temp_db):
    """get_pending_request_details returns None for unknown id."""
    assert temp_db.get_pending_request_details("99999") is None
