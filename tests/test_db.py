"""Simple tests for SQLite DB (users, reservations, availability)."""

import os

# Ensure project root is on path
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.sqlite_db import SQLiteDB


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SEED_PATH = str(_PROJECT_ROOT / "data" / "seed_data.json")


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
