"""Simple tests for chatbot-related behavior (show reservations, intent keywords)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import tempfile

import pytest
from src.chatbot.reservation_handler import ReservationHandler
from src.db.sqlite_db import SQLiteDB


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = SQLiteDB(db_path=path)
    yield db
    try:
        os.unlink(path)
    except Exception:
        pass


def test_show_reservations_returns_saved_dates(temp_db):
    """Handler get_active_reservations should return dates saved for that nickname."""
    temp_db.add_reservation("alice", "2025-03-10")
    temp_db.add_reservation("alice", "2025-03-11")
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    assert "2025-03-10" in handler.get_active_reservations()
    assert "2025-03-11" in handler.get_active_reservations()
    assert len(handler.get_active_reservations()) == 2


def test_show_reservations_empty_for_other_nickname(temp_db):
    """Reservations for one user should not appear for another."""
    temp_db.add_reservation("alice", "2025-03-10")
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("bob")
    assert handler.get_active_reservations() == []
