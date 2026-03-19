"""Unit tests for RAGSystem (src/chatbot/rag_system.py).

All tests mock llm.invoke; no real or stub LLM.

"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch

import pytest

from langchain_core.messages import AIMessage, HumanMessage

from src.chatbot.rag_system import RAGSystem
from src.config import PROJECT_ROOT
from src.db.sqlite_db import SQLiteDB

_SEED_PATH = str(PROJECT_ROOT / "data" / "seed_data.json")


def _doc(content: str, metadata=None):
    return {"content": content, "metadata": metadata or {}}


def _llm_result(content: str):
    """Object with .content for LLM invoke return value."""
    return type("R", (), {"content": content})()


@pytest.fixture
def temp_db():
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = SQLiteDB(db_path=path, seed_path=_SEED_PATH)
    yield db
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def mock_guard():
    g = MagicMock()
    g.validate_query = MagicMock(return_value=(True, None))
    g.filter_retrieved_documents = MagicMock(side_effect=lambda docs: docs)
    g.validate_response = MagicMock(side_effect=lambda text: (True, text))
    return g


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def rag(mock_store, mock_guard, mock_llm):
    """RAGSystem with mocked store, guard, and LLM (provider returns mock_llm)."""
    provider = MagicMock(get_llm=MagicMock(return_value=mock_llm))
    r = RAGSystem(
        vector_store=mock_store,
        llm_provider=provider,
        guard_rails=mock_guard,
        k=3,
        db=None,
    )
    r.llm = mock_llm
    return r


# ----- retrieve_context -----


def test_retrieve_context_calls_search_and_filter(rag, mock_store, mock_guard):
    mock_store.similarity_search.return_value = [_doc("A"), _doc("B")]
    out = rag.retrieve_context("parking rates", allow_reservation_data=False)
    mock_guard.validate_query.assert_called_once_with("parking rates", allow_reservation_data=False)
    mock_store.similarity_search.assert_called_once_with("parking rates", k=3)
    mock_guard.filter_retrieved_documents.assert_called_once()
    assert len(out) == 2
    assert out[0]["content"] == "A"


def test_retrieve_context_unsafe_query_raises(rag, mock_guard):
    mock_guard.validate_query.return_value = (False, "Sensitive data")
    with pytest.raises(ValueError, match="Sensitive data"):
        rag.retrieve_context("my ssn is 123-45-6789")
    mock_guard.validate_query.assert_called_once()
    rag.vector_store.similarity_search.assert_not_called()


# ----- _get_dynamic_context -----


def test_get_dynamic_context_no_db_returns_empty(rag):
    rag.db = None
    assert rag._get_dynamic_context() == ""


def test_get_dynamic_context_with_db_includes_date_and_availability(temp_db, mock_store, mock_guard, mock_llm):
    provider = MagicMock(get_llm=MagicMock(return_value=mock_llm))
    rag = RAGSystem(vector_store=mock_store, llm_provider=provider, guard_rails=mock_guard, k=3, db=temp_db)
    with patch("src.chatbot.rag_system.date") as mock_date:
        mock_date.today.return_value = __import__("datetime").date(2025, 3, 10)
        ctx = rag._get_dynamic_context()
    assert "2025-03-10" in ctx
    assert "today" in ctx or "tomorrow" in ctx or "spaces" in ctx


# ----- _format_conversation_for_prompt -----


def test_format_conversation_human_and_ai_messages(rag):
    messages = [
        HumanMessage(content="Hi"),
        AIMessage(content="Hello"),
    ]
    text = rag._format_conversation_for_prompt(messages)
    assert "User: Hi" in text
    assert "Assistant: Hello" in text


def test_format_conversation_dict_messages(rag):
    messages = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
    text = rag._format_conversation_for_prompt(messages)
    assert "User: x" in text or "user" in text.lower()
    assert "y" in text


# ----- generate_response -----


def test_generate_response_no_context_returns_fallback_no_invoke(rag, mock_store, mock_guard, mock_llm):
    mock_store.similarity_search.return_value = []
    rag.db = None
    out = rag.generate_response("anything")
    assert "couldn't find relevant information" in out
    mock_llm.invoke.assert_not_called()


def test_generate_response_invokes_llm_with_context_in_prompt(rag, mock_store, mock_guard, mock_llm):
    unique = "Parking is $5 per hour."
    mock_store.similarity_search.return_value = [_doc(unique)]
    mock_llm.invoke.return_value = _llm_result("Five dollars per hour.")
    out = rag.generate_response("How much?")
    mock_llm.invoke.assert_called_once()
    (call_args,) = mock_llm.invoke.call_args[0]
    assert unique in call_args
    assert "How much?" in call_args
    assert out == "Five dollars per hour."


def test_generate_response_appends_dynamic_context_when_db_set(rag, mock_store, mock_guard, mock_llm, temp_db):
    mock_store.similarity_search.return_value = []
    rag.db = temp_db
    mock_llm.invoke.return_value = _llm_result("Here is the info.")
    with patch("src.chatbot.rag_system.date") as mock_date:
        mock_date.today.return_value = __import__("datetime").date(2025, 3, 10)
        rag.generate_response("Spaces tomorrow?")
    (call_args,) = mock_llm.invoke.call_args[0]
    assert "2025-03-10" in call_args or "tomorrow" in call_args or "spaces" in call_args


def test_generate_response_strips_code_from_llm_output(rag, mock_store, mock_guard, mock_llm):
    mock_store.similarity_search.return_value = [_doc("x")]
    mock_llm.invoke.return_value = _llm_result("The rate is $5.\n```python\ncode\n```")
    out = rag.generate_response("q")
    mock_guard.validate_response.assert_called_once()
    # _strip_code_from_response is applied before validate_response; guard receives stripped text
    call_arg = mock_guard.validate_response.call_args[0][0]
    assert "```" not in call_arg


# ----- _strip_code_from_response -----


def test_strip_code_from_response_removes_after_markers():
    assert "code" not in RAGSystem._strip_code_from_response("ok\n```\ncode")
    assert "def " not in RAGSystem._strip_code_from_response("text\n\ndef x(): pass")
    assert RAGSystem._strip_code_from_response("  only this  ") == "only this"
    assert RAGSystem._strip_code_from_response("") == ""
    assert RAGSystem._strip_code_from_response(None) is None


# ----- get_context_string -----


def test_get_context_string_delegates_to_vector_store(rag, mock_store):
    mock_store.get_relevant_context.return_value = "Context string here"
    out = rag.get_context_string("query")
    mock_store.get_relevant_context.assert_called_once_with("query", k=3)
    assert out == "Context string here"


# ----- classify_intent (mock llm.invoke return value) -----


def test_classify_intent_exact_word_reserve(rag, mock_llm):
    mock_llm.invoke.return_value = _llm_result("reserve")
    assert rag.classify_intent("book a spot") == "reserve"
    mock_llm.invoke.assert_called_once()


def test_classify_intent_exact_word_show_reservations(rag, mock_llm):
    mock_llm.invoke.return_value = _llm_result("show_reservations")
    assert rag.classify_intent("my bookings") == "show_reservations"


def test_classify_intent_exact_word_general(rag, mock_llm):
    mock_llm.invoke.return_value = _llm_result("general")
    assert rag.classify_intent("hours?") == "general"


def test_classify_intent_substring_show_reservation_typo(rag, mock_llm):
    mock_llm.invoke.return_value = _llm_result("show_reservation")
    assert rag.classify_intent("list") == "show_reservations"



def test_classify_intent_substring_reserve_phrase(rag, mock_llm):
    mock_llm.invoke.return_value = _llm_result("The user wants to reserve.")
    assert rag.classify_intent("book") == "reserve"


def test_classify_intent_unrecognized_defaults_to_general(rag, mock_llm):
    mock_llm.invoke.return_value = _llm_result("I'm not sure.")
    assert rag.classify_intent("hello") == "general"


def test_classify_intent_strips_and_lowers_before_match(rag, mock_llm):
    mock_llm.invoke.return_value = _llm_result("  RESERVE  \n")
    assert rag.classify_intent("x") == "reserve"


def test_classify_intent_result_without_content_uses_str(rag, mock_llm):
    """When invoke returns object without .content, str(result) is used."""
    no_content = type("R", (), {"__str__": lambda self: " general "})()
    mock_llm.invoke.return_value = no_content
    assert rag.classify_intent("x") == "general"
