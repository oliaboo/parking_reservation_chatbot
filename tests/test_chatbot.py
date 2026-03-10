"""Simple tests for chatbot-related behavior (show reservations, intent keywords)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from src.chatbot.chatbot import ParkingChatbot
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


def test_chat_show_my_reservations_invokes_show_reservations_handler(temp_db):
    """Chat with 'show my reservations' should return list from _handle_show_reservations, not RAG."""
    temp_db.add_reservation("alice", "2025-03-15")
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.generate_response = MagicMock(return_value="RAG would say this")
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    response = chatbot.chat("Show my reservations")
    assert "2025-03-15" in response
    assert "active reservations" in response.lower()
    mock_rag.generate_response.assert_not_called()


def test_chat_general_questions_go_to_rag_not_reservation(temp_db):
    """Questions about reservations/parking that are not booking intent should use RAG (general)."""
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.generate_response = MagicMock(return_value="Our reservation policy is flexible.")
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    response = chatbot.chat("What is your reservation policy?")
    mock_rag.generate_response.assert_called_once()
    assert "reservation policy" in response.lower() or "flexible" in response.lower()


def test_chat_booking_intent_goes_to_reservation(temp_db):
    """Clear booking intent should go to reservation handler, not RAG."""
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.generate_response = MagicMock(return_value="RAG response")
    mock_rag.guard_rails = MagicMock()
    mock_rag.guard_rails.validate_query = MagicMock(return_value=(True, None))
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    response = chatbot.chat("I want to make a reservation")
    mock_rag.generate_response.assert_not_called()
    assert "reservation" in response.lower() or "date" in response.lower() or "help" in response.lower()
