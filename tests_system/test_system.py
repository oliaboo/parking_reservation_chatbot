"""System testing: load tests and integration tests for orchestration (task4).

Uses real components where possible: real DB, real Admin API over HTTP, real
VectorStore/GuardRails/RAG (with a fast stub LLM so tests don't load a model),
and real file I/O for MCP storage. Only the LLM inference is stubbed.

Run with: make tests-system  or  pytest tests_system/ -v
Not run by default with make tests or CI.
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import requests
from fastapi.testclient import TestClient

from src.admin_api.app import app
from src.chatbot.chatbot import ParkingChatbot
from src.chatbot.rag_system import RAGSystem
from src.chatbot.reservation_handler import ReservationHandler
from src.config import PROJECT_ROOT, settings
from src.db.sqlite_db import SQLiteDB, get_db
from src.guardrails.guard_rails import GuardRails
from src.vector_db.vector_store import VectorStore

_SEED_PATH = str(PROJECT_ROOT / "data" / "seed_data.json")

# Load test sizes (real components; keep moderate for CI)
CHATBOT_LOAD_TURNS = 30
ADMIN_LOAD_REQUESTS = 25
MCP_LOAD_APPENDS = 80

# Port for integration test (real HTTP). Use a high port to avoid clashes.
_INTEGRATION_API_PORT = 18765


def _stub_llm_invoke_response(text: str):
    """Return an object with .content for RAGSystem/LLM invoke."""
    return type("Out", (), {"content": text})()


class StubLLM:
    """Minimal LLM stub: no model file, returns intent/general answers so the rest of the stack runs for real."""

    def invoke(self, prompt: str):
        if "Classify" in prompt or "intent" in prompt.lower():
            return _stub_llm_invoke_response("general")
        return _stub_llm_invoke_response("Short reply.")


class StubLLMProvider:
    """Provider that returns StubLLM so RAGSystem and chatbot use real code paths."""

    def __init__(self, intent_for_reservation: bool = False):
        self.intent_for_reservation = intent_for_reservation

    def get_llm(self):
        return StubLLMReserve() if self.intent_for_reservation else StubLLM()


class StubLLMReserve(StubLLM):
    """Stub LLM that returns 'reserve' for intent when user message is about reservation."""

    def invoke(self, prompt: str):
        if "Classify" in prompt and "reservation" in prompt.lower():
            return _stub_llm_invoke_response("reserve")
        return super().invoke(prompt)


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


def _make_rag_system_with_stub_llm(db: SQLiteDB, intent_for_reservation: bool = False):
    """Real VectorStore, real GuardRails, real RAGSystem; only LLM is stubbed."""
    vector_store = VectorStore(
        embedding_model=settings.embedding_model,
        use_mock=settings.use_mock_db,
        faiss_metric=settings.faiss_metric,
    )
    guard_rails = GuardRails(
        enabled=settings.enable_guard_rails,
        threshold=settings.sensitive_data_threshold,
    )
    rag = RAGSystem(
        vector_store=vector_store,
        llm_provider=StubLLMProvider(intent_for_reservation=intent_for_reservation),
        guard_rails=guard_rails,
        k=settings.retrieval_k,
        db=db,
    )
    return rag


# ----- Load tests (real components, stub LLM only) -----


def test_load_chatbot_dialogue_mode(temp_db):
    """Load test: many chat turns with real RAG (vector store, guard rails, graph); only LLM stubbed."""
    rag = _make_rag_system_with_stub_llm(temp_db)
    handler = ReservationHandler(db=temp_db)
    handler.set_nickname("alice")
    chatbot = ParkingChatbot(rag_system=rag, reservation_handler=handler)

    start = time.perf_counter()
    for i in range(CHATBOT_LOAD_TURNS):
        response = chatbot.chat(f"Question {i}")
        assert response and isinstance(response, str)
    elapsed = time.perf_counter() - start

    # Real stack; allow more time if embedding/FAISS load (e.g. first run)
    assert elapsed < 60.0, f"Chatbot load test took {elapsed:.2f}s for {CHATBOT_LOAD_TURNS} turns"


def test_load_admin_confirmation_functionality(temp_db):
    """Load test: real Admin API and DB; many PATCH approvals."""
    import src.db.sqlite_db as db_mod

    db_mod._db = temp_db
    try:
        with TestClient(app) as client:
            ids = []
            for i in range(ADMIN_LOAD_REQUESTS):
                rid = temp_db.create_pending_request("alice", [f"2025-04-{1 + (i % 28):02d}"])
                ids.append(rid)

            start = time.perf_counter()
            for rid in ids:
                r = client.patch(f"/requests/{rid}", json={"status": "approved"})
                assert r.status_code == 200
            elapsed = time.perf_counter() - start

            for rid in ids:
                assert temp_db.get_request_status(rid) == "approved"
            assert elapsed < 5.0, f"Admin confirmation load took {elapsed:.2f}s for {ADMIN_LOAD_REQUESTS} PATCHes"
    finally:
        db_mod._db = None


def test_load_mcp_recording_storage(tmp_path):
    """Load test: real file I/O – append many CSV rows to a real file (MCP storage path)."""
    from src.mcp_reservation_logger.client_fs import _append_line_to_content, _make_csv_header

    log_file = tmp_path / "reservations_log.csv"
    content = _make_csv_header()
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(content)

    start = time.perf_counter()
    for i in range(MCP_LOAD_APPENDS):
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        content = _append_line_to_content(
            content, f"user_{i}", f"CAR-{i}", "2025-03-10, 2025-03-11"
        )
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(content)
    elapsed = time.perf_counter() - start

    lines = content.strip().split("\n")
    assert len(lines) == MCP_LOAD_APPENDS + 1
    assert elapsed < 2.0, f"MCP file append load took {elapsed:.2f}s for {MCP_LOAD_APPENDS} appends"


# ----- Integration tests: all orchestration steps (user_interaction → wait_for_approval → record_data / end) -----


def _run_admin_api_in_thread(temp_db, port: int):
    """Inject temp_db, start Admin API on port, yield api_url. Restore get_db in finally."""
    import src.db.sqlite_db as db_mod
    import uvicorn

    db_mod._db = temp_db
    api_url = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            requests.get(f"{api_url}/requests", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.skip("Admin API did not start in time (port may be in use)")
    try:
        yield api_url
    finally:
        db_mod._db = None


def test_integration_orchestration_all_steps_approved(temp_db):
    """Integration: all orchestration steps on approved path.
    Step 1 user_interaction: reserve intent → ask for date; then date → create request, escalate.
    Step 2 wait_for_approval: poll API until admin approves.
    Step 3 record_data: apply reservation to DB, clear request id.
    """
    import src.db.sqlite_db as db_mod

    for api_url in _run_admin_api_in_thread(temp_db, _INTEGRATION_API_PORT):
        with pytest.MonkeyPatch.context() as m:
            m.setattr(settings, "admin_api_base_url", api_url)

            rag = _make_rag_system_with_stub_llm(temp_db, intent_for_reservation=True)
            handler = ReservationHandler(db=temp_db)
            handler.set_nickname("alice")
            chatbot = ParkingChatbot(rag_system=rag, reservation_handler=handler)

            # Step 1a: user_interaction (reserve intent) → ask for date
            r1 = chatbot.chat("I want to make a reservation")
            assert "date" in r1.lower() or "reservation" in r1.lower()

            # Step 1b: user_interaction (date) → create_request via API, set reservation_request_id → route to wait_for_approval
            history = [
                {"role": "user", "content": "I want to make a reservation"},
                {"role": "assistant", "content": r1},
            ]
            result = {"r2": None, "done": False}

            def run_second_turn():
                result["r2"] = chatbot.chat("2025-03-15", conversation_history=history)
                result["done"] = True

            t = threading.Thread(target=run_second_turn, daemon=True)
            t.start()
            time.sleep(2.5)

            # Step 2: wait_for_approval (chatbot is polling) → we approve via real PATCH
            r = requests.get(f"{api_url}/requests", params={"status": "pending"}, timeout=2)
            r.raise_for_status()
            data = r.json()
            assert len(data) >= 1, "Orchestration step: request must appear in API after user sent date"
            rid = data[0]["id"]
            patch_r = requests.patch(f"{api_url}/requests/{rid}", json={"status": "approved"}, timeout=2)
            patch_r.raise_for_status()

            t.join(timeout=15.0)
            assert result["done"], "Chatbot thread did not finish after approval"

            # Step 3: record_data must have run (reservation in DB)
            assert "2025-03-15" in handler.get_active_reservations() or (
                result["r2"] and "saved" in result["r2"].lower()
            ), "Orchestration step: record_data should add reservation after approval"


def test_integration_orchestration_all_steps_rejected(temp_db):
    """Integration: orchestration steps on rejected path.
    user_interaction → wait_for_approval → admin rejects → end (no record_data).
    """
    import src.db.sqlite_db as db_mod

    for api_url in _run_admin_api_in_thread(temp_db, _INTEGRATION_API_PORT + 1):  # different port
        with pytest.MonkeyPatch.context() as m:
            m.setattr(settings, "admin_api_base_url", api_url)

            rag = _make_rag_system_with_stub_llm(temp_db, intent_for_reservation=True)
            handler = ReservationHandler(db=temp_db)
            handler.set_nickname("alice")
            chatbot = ParkingChatbot(rag_system=rag, reservation_handler=handler)

            r1 = chatbot.chat("I want to make a reservation")
            history = [
                {"role": "user", "content": "I want to make a reservation"},
                {"role": "assistant", "content": r1},
            ]
            result = {"r2": None, "done": False}

            def run_second_turn():
                result["r2"] = chatbot.chat("2025-03-16", conversation_history=history)
                result["done"] = True

            t = threading.Thread(target=run_second_turn, daemon=True)
            t.start()
            time.sleep(2.5)

            r = requests.get(f"{api_url}/requests", params={"status": "pending"}, timeout=2)
            r.raise_for_status()
            data = r.json()
            assert len(data) >= 1
            rid = data[0]["id"]
            patch_r = requests.patch(f"{api_url}/requests/{rid}", json={"status": "rejected"}, timeout=2)
            patch_r.raise_for_status()

            t.join(timeout=15.0)
            assert result["done"]

            # record_data must NOT run: no reservation for that date
            assert "2025-03-16" not in handler.get_active_reservations()
            assert result["r2"] and ("declined" in result["r2"].lower() or "administrator" in result["r2"].lower())


def test_integration_orchestration_general_no_escalation(temp_db):
    """Integration: general intent does not escalate; only user_interaction runs, then end."""
    import src.db.sqlite_db as db_mod

    for api_url in _run_admin_api_in_thread(temp_db, _INTEGRATION_API_PORT + 2):
        with pytest.MonkeyPatch.context() as m:
            m.setattr(settings, "admin_api_base_url", api_url)

            rag = _make_rag_system_with_stub_llm(temp_db, intent_for_reservation=False)
            handler = ReservationHandler(db=temp_db)
            handler.set_nickname("alice")
            chatbot = ParkingChatbot(rag_system=rag, reservation_handler=handler)

            r_before = requests.get(f"{api_url}/requests", timeout=1)
            r_before.raise_for_status()
            count_before = len(r_before.json())

            response = chatbot.chat("What are your opening hours?")

            r_after = requests.get(f"{api_url}/requests", timeout=1)
            r_after.raise_for_status()
            count_after = len(r_after.json())

            assert "waiting for approval" not in response.lower(), "General question must not escalate to admin"
            assert count_after == count_before, "No new request must be created for general intent"
