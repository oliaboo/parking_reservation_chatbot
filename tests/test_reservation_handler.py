"""Simple tests for ReservationHandler (date-only flow, SQLite)."""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.chatbot.reservation_handler import (
    ReservationHandler,
    ReservationState,
    _date_range_to_list,
    _parse_date_range,
)
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


@patch("src.admin_api.client.create_request")
def test_handler_full_reservation_flow(mock_create_request, handler):
    """Start reservation, provide date: handler escalates to admin (create_request), returns pending_approval."""
    mock_create_request.return_value = "req-001"
    handler.start_reservation()
    result = handler.process_user_input("2025-03-10")
    assert len(result) == 3
    ok, msg, request_id = result[0], result[1], result[2]
    assert ok is True
    assert msg == "pending_approval"
    assert request_id == "req-001"
    mock_create_request.assert_called_once_with("alice", ["2025-03-10"])
    # Reservations are only added after admin approval (apply_approved_request), not here
    assert "2025-03-10" not in handler.get_active_reservations()


def test_parse_date_range():
    """Range format YYYY-MM-DD - YYYY-MM-DD is parsed correctly."""
    assert _parse_date_range("2025-03-10 - 2025-03-15") == ("2025-03-10", "2025-03-15")
    assert _parse_date_range("2025-03-10 to 2025-03-15") == ("2025-03-10", "2025-03-15")
    assert _parse_date_range("2025-01-01 - 2025-01-03") == ("2025-01-01", "2025-01-03")
    assert _parse_date_range("2025-03-15 - 2025-03-10") is None  # end before start
    assert _parse_date_range("not a range") is None


def test_date_range_to_list():
    """Date range expands to list of days inclusive."""
    assert _date_range_to_list("2025-03-10", "2025-03-12") == [
        "2025-03-10",
        "2025-03-11",
        "2025-03-12",
    ]
    assert _date_range_to_list("2025-03-10", "2025-03-10") == ["2025-03-10"]


@patch("src.admin_api.client.create_request")
def test_handler_date_range_reservation(mock_create_request, handler):
    """Reserving a date range escalates to admin (create_request) with all dates, returns pending_approval."""
    mock_create_request.return_value = "req-range-1"
    handler.start_reservation()
    result = handler.process_user_input("2025-03-10 - 2025-03-12")
    assert len(result) == 3
    ok, msg, request_id = result[0], result[1], result[2]
    assert ok is True
    assert msg == "pending_approval"
    assert request_id == "req-range-1"
    mock_create_request.assert_called_once_with("alice", ["2025-03-10", "2025-03-11", "2025-03-12"])
    assert handler.get_active_reservations() == []


def test_handler_rejects_reservation_when_parking_full(handler):
    """When a date has 0 free spaces, reservation is rejected with a clear message."""
    with sqlite3.connect(handler.db.db_path) as conn:
        conn.execute(
            "UPDATE availability SET free_spaces = 0 WHERE date = ?", ("2025-03-13",)
        )
        conn.commit()
    handler.start_reservation()
    ok, msg = handler.process_user_input("2025-03-13")
    assert ok is False
    assert "no free spaces" in msg.lower() or "2025-03-13" in msg
    assert "2025-03-13" not in handler.get_active_reservations()


def test_handler_rejects_range_when_any_day_full(handler):
    """When any day in a range has 0 free spaces, the whole reservation is rejected."""
    with sqlite3.connect(handler.db.db_path) as conn:
        conn.execute(
            "UPDATE availability SET free_spaces = 0 WHERE date = ?", ("2025-03-11",)
        )
        conn.commit()
    handler.start_reservation()
    ok, msg = handler.process_user_input("2025-03-10 - 2025-03-12")
    assert ok is False
    assert "no free spaces" in msg.lower()
    assert "2025-03-11" in msg
    assert "2025-03-10" not in handler.get_active_reservations()


@patch("src.admin_api.client.get_db")
def test_apply_approved_request_adds_reservations(mock_get_db, handler):
    """After admin approval, apply_approved_request loads request and adds reservations to DB."""
    mock_get_db.return_value = handler.db
    request_id = handler.db.create_pending_request("alice", ["2025-03-10", "2025-03-11"])
    ok, msg = handler.apply_approved_request(request_id)
    assert ok is True
    assert "saved" in msg.lower()
    active = handler.get_active_reservations()
    assert "2025-03-10" in active
    assert "2025-03-11" in active
    assert len(active) == 2
