"""Simple tests for ReservationHandler (date-only flow, SQLite)."""
import os
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.db.sqlite_db import SQLiteDB
from src.chatbot.reservation_handler import (
    ReservationHandler,
    ReservationState,
    _parse_date_range,
    _date_range_to_list,
)


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


@pytest.fixture
def handler(temp_db):
    h = ReservationHandler(db=temp_db)
    h.set_nickname("alice")
    return h


def test_reservation_state_valid_date():
    """ReservationState accepts YYYY-MM-DD and completes."""
    s = ReservationState()
    assert s.is_complete is False
    assert s.update("date", "2025-06-15") is True
    assert s.date == "2025-06-15"
    assert s.is_complete is True


def test_reservation_state_invalid_date():
    """ReservationState rejects invalid date."""
    s = ReservationState()
    assert s.update("date", "not-a-date") is False
    assert s.is_complete is False


def test_handler_requires_nickname(temp_db):
    """Handler without nickname should not process reservation."""
    h = ReservationHandler(db=temp_db)
    h.start_reservation()
    ok, msg = h.process_user_input("2025-06-15")
    assert ok is False
    assert "nickname" in msg.lower() or "identify" in msg.lower()


def test_handler_full_reservation_flow(handler):
    """Start reservation, provide date, should save and return success."""
    handler.start_reservation()
    ok, msg = handler.process_user_input("2025-03-10")
    assert ok is True
    assert "2025-03-10" in msg or "saved" in msg.lower()
    assert "2025-03-10" in handler.get_active_reservations()


def test_parse_date_range():
    """Range format YYYY-MM-DD - YYYY-MM-DD is parsed correctly."""
    assert _parse_date_range("2025-03-10 - 2025-03-15") == ("2025-03-10", "2025-03-15")
    assert _parse_date_range("2025-03-10 to 2025-03-15") == ("2025-03-10", "2025-03-15")
    assert _parse_date_range("2025-01-01 - 2025-01-03") == ("2025-01-01", "2025-01-03")
    assert _parse_date_range("2025-03-15 - 2025-03-10") is None  # end before start
    assert _parse_date_range("not a range") is None


def test_date_range_to_list():
    """Date range expands to list of days inclusive."""
    assert _date_range_to_list("2025-03-10", "2025-03-12") == ["2025-03-10", "2025-03-11", "2025-03-12"]
    assert _date_range_to_list("2025-03-10", "2025-03-10") == ["2025-03-10"]


def test_handler_date_range_reservation(handler):
    """Reserving a date range saves one row per day."""
    handler.start_reservation()
    ok, msg = handler.process_user_input("2025-03-10 - 2025-03-12")
    assert ok is True
    assert "saved" in msg.lower()
    active = handler.get_active_reservations()
    assert "2025-03-10" in active
    assert "2025-03-11" in active
    assert "2025-03-12" in active
    assert len(active) == 3
