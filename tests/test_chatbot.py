"""Simple tests for chatbot-related behavior (show reservations, intent keywords, reservation-in-progress escape)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.chatbot.chatbot import ParkingChatbot
from src.chatbot.reservation_handler import ReservationHandler
from src.db.sqlite_db import SQLiteDB
from src.guardrails.guard_rails import GuardRails


_SEED_PATH = str(Path(__file__).resolve().parent.parent / "data" / "seed_data.json")


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
    mock_rag.guard_rails.validate_query = MagicMock(return_value=(True, None))
    mock_rag.classify_intent = MagicMock(return_value="show_reservations")
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
    mock_rag.guard_rails.validate_query = MagicMock(return_value=(True, None))
    mock_rag.classify_intent = MagicMock(return_value="general")
    mock_rag.generate_response = MagicMock(return_value="Our reservation policy is flexible.")
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    response = chatbot.chat("What is your reservation policy?")
    mock_rag.generate_response.assert_called_once()
    assert "reservation policy" in response.lower() or "flexible" in response.lower()


def test_chat_blocks_email_in_query(temp_db):
    """Query containing email should be blocked by guard rails before RAG/LLM; user sees sensitive-data message."""
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.guard_rails.validate_query = MagicMock(
        return_value=(False, "Query contains potentially sensitive information. Please rephrase.")
    )
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    response = chatbot.chat("Contact me at john.doe@email.com for the receipt")
    assert "sensitive" in response.lower() or "rephrase" in response.lower()
    mock_rag.classify_intent.assert_not_called()
    mock_rag.generate_response.assert_not_called()


def test_chat_blocks_email_with_real_guard_rails(temp_db):
    """With real GuardRails, query containing john.doe@email.com is blocked and RAG is never called."""
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    guard_rails = GuardRails(enabled=True, threshold=0.7)
    mock_rag = MagicMock()
    mock_rag.guard_rails = guard_rails
    mock_rag.classify_intent = MagicMock(return_value="general")
    mock_rag.generate_response = MagicMock(return_value="Parking info here")
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    response = chatbot.chat("Contact me at john.doe@email.com for the receipt")
    assert "sensitive" in response.lower() or "rephrase" in response.lower()
    mock_rag.generate_response.assert_not_called()


def test_chat_booking_intent_goes_to_reservation(temp_db):
    """Clear booking intent should go to reservation handler, not RAG."""
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.classify_intent = MagicMock(return_value="reserve")
    mock_rag.generate_response = MagicMock(return_value="RAG response")
    mock_rag.guard_rails = MagicMock()
    mock_rag.guard_rails.validate_query = MagicMock(return_value=(True, None))
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    response = chatbot.chat("I want to make a reservation")
    mock_rag.generate_response.assert_not_called()
    assert "reservation" in response.lower() or "date" in response.lower() or "help" in response.lower()


def test_looks_like_date_accepts_single_and_range():
    """_looks_like_date returns True for YYYY-MM-DD and date ranges."""
    handler = ReservationHandler(db=MagicMock())
    mock_rag = MagicMock()
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    assert chatbot._looks_like_date("2025-03-15") is True
    assert chatbot._looks_like_date("  2025-03-15  ") is True
    assert chatbot._looks_like_date("2025-03-10 - 2025-03-15") is True
    assert chatbot._looks_like_date("2025-03-10 to 2025-03-15") is True
    assert chatbot._looks_like_date("3/15/2025") is True
    assert chatbot._looks_like_date("show my reservations") is False
    assert chatbot._looks_like_date("cancel") is False
    assert chatbot._looks_like_date("What are your hours?") is False


def test_reservation_in_progress_date_like_goes_to_reservation(temp_db):
    """When waiting for date, a date-like message goes to reservation without calling classify_intent again."""
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.classify_intent = MagicMock(return_value="reserve")
    mock_rag.guard_rails = MagicMock()
    mock_rag.guard_rails.validate_query = MagicMock(return_value=(True, None))
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    # Start reservation
    r1 = chatbot.chat("I want to make a reservation")
    assert "date" in r1.lower() or "reservation" in r1.lower()
    history = [HumanMessage(content="I want to make a reservation"), AIMessage(content=r1)]
    # Send date: should be treated as reservation input (date-like), not trigger classify_intent
    r2 = chatbot.chat("2025-03-15", conversation_history=history)
    assert mock_rag.classify_intent.call_count == 1
    assert "2025-03-15" in handler.get_active_reservations() or "2025-03-15" in r2 or "saved" in r2.lower()


def test_reservation_in_progress_show_reservations_clears_and_shows(temp_db):
    """When waiting for date, 'show my reservations' clears reservation and returns list."""
    temp_db.add_reservation("alice", "2025-03-10")
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.classify_intent = MagicMock(side_effect=["reserve", "show_reservations"])
    mock_rag.generate_response = MagicMock(return_value="RAG response")
    mock_rag.guard_rails = MagicMock()
    mock_rag.guard_rails.validate_query = MagicMock(return_value=(True, None))
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    r1 = chatbot.chat("I want to book a spot")
    history = [HumanMessage(content="I want to book a spot"), AIMessage(content=r1)]
    r2 = chatbot.chat("show my reservations", conversation_history=history)
    assert "2025-03-10" in r2
    assert "active reservations" in r2.lower()
    assert handler.get_current_reservation() is None
    mock_rag.generate_response.assert_not_called()


def test_reservation_in_progress_general_clears_and_answers_rag(temp_db):
    """When waiting for date, a general question clears reservation and returns RAG answer."""
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    mock_rag = MagicMock()
    mock_rag.classify_intent = MagicMock(side_effect=["reserve", "general"])
    mock_rag.generate_response = MagicMock(return_value="We are open 9 to 5.")
    mock_rag.guard_rails = MagicMock()
    mock_rag.guard_rails.validate_query = MagicMock(return_value=(True, None))
    chatbot = ParkingChatbot(rag_system=mock_rag, reservation_handler=handler)
    r1 = chatbot.chat("I want to make a reservation")
    history = [HumanMessage(content="I want to make a reservation"), AIMessage(content=r1)]
    r2 = chatbot.chat("What are your hours?", conversation_history=history)
    assert "9" in r2 or "5" in r2 or "open" in r2.lower()
    assert handler.get_current_reservation() is None
    assert mock_rag.generate_response.call_count == 1


def test_rag_dynamic_context_includes_availability_for_tomorrow(temp_db):
    """RAG dynamic context includes today's date and availability so questions like 'how many for tomorrow?' can be answered."""
    from src.chatbot.rag_system import RAGSystem

    mock_store = MagicMock()
    mock_store.similarity_search = MagicMock(return_value=[])
    mock_llm = MagicMock()
    mock_rag = RAGSystem(
        vector_store=mock_store,
        llm_provider=MagicMock(get_llm=MagicMock(return_value=mock_llm)),
        guard_rails=MagicMock(validate_query=MagicMock(return_value=(True, None))),
        db=temp_db,
    )
    with patch("src.chatbot.rag_system.date") as mock_date:
        mock_date.today.return_value = date(2025, 3, 10)
        ctx = mock_rag._get_dynamic_context()
    assert "Today's date: 2025-03-10" in ctx
    assert "tomorrow" in ctx
    assert "spaces available" in ctx
