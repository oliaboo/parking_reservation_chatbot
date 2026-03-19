# Code Structure

This document describes the project layout and how each module is used.

---

## 1. Project layout

```
parking_reservation_chatbot/
├── run_chatbot_agent.py         # Chatbot entry: nickname, init, chat loop
├── run_admin_api.py             # Admin REST API (FastAPI, POST/GET/PATCH requests)
├── run_admin_console_agent.py   # Admin console: list pending, LLM-interpreted approve/reject; logs via filesystem MCP
├── data/
│   └── parking.db         # SQLite (users, reservations, reservation_requests, prices, working_hours, availability)
├── rag_data/
│   ├── parking_info.txt
│   ├── faiss_parking.index
│   └── faiss_parking_docs.json
├── requirements.txt
├── .env / .env_example
├── local_models/
├── logs/                  # Step log from run_chatbot_agent.py (see § Logging)
├── docs/
├── tests/
└── src/
    ├── config.py
    ├── db/
    │   └── sqlite_db.py   # + reservation_requests table and methods
    ├── admin_api/
    │   ├── app.py         # FastAPI: POST/GET/PATCH for reservation requests
    │   └── client.py      # create_request, get_request_status, get_pending_request_details
    ├── vector_db/
    │   └── ...            # FAISS over parking_info.txt
    ├── guardrails/
    │   └── ...
    ├── mcp_reservation_logger/
    │   └── client_fs.py       # Spawns @modelcontextprotocol/server-filesystem (npx), read_text_file + write_file → CSV
└── chatbot/
        ├── chatbot.py     # LangGraph; _handle_reservation polls API, apply on approve
        ├── rag_system.py   # RAG (retrieval k=3, no conversation history in prompt)
        ├── llm_setup.py
        └── reservation_handler.py  # create_request via client; apply_approved_request
```

---

## 2. Entry point: run_chatbot_agent.py

**Role:** Bootstrap the app and run the interactive chat.

- **Path and cwd:** Adds project root to `sys.path`, `os.chdir(project_root)` so imports and paths like `data/parking.db` and `local_models/` work.
- **Imports:** All `src.*` modules used by the app (config, vector_db, guardrails, chatbot, db).
- **main():**
  1. `get_db()` — ensure SQLite DB exists (singleton).
  2. Nickname loop: `input()` until `db.user_exists(nickname)`.
  3. `initialize_system(nickname)` — build VectorStore, GuardRails, LLMProvider, RAGSystem, ReservationHandler, ParkingChatbot.
  4. Chat loop: `input()` → `chatbot.chat(user_input, conversation_history)` → print response, append to history; exit on "quit"/"exit".

**Uses:** config.settings, get_db, VectorStore, GuardRails, LLMProvider, RAGSystem, ReservationHandler, ParkingChatbot.

### Logging (run_chatbot_agent.py)

When you run the chatbot, a **step logger** writes execution steps to a file under the project root so you can see what ran without watching the console.

- **Log file:** Default `logs/chatbot.log` (path from `settings.log_file`, overridable with env `LOG_FILE`).
- **Format:** One line per event: `YYYY-MM-DD HH:MM:SS | LEVEL | message`.
- **What is logged:** Startup (chatbot name), waiting for nickname, nickname accepted, each init step (vector store, guard rails, LLM loaded, RAG system, reservation handler, chatbot), “System ready”, “Session started for &lt;nickname&gt;”, and session end (“Session ended (user quit)” or “Session ended (interrupted)”). Errors (e.g. failed vector store or LLM load) are written at ERROR level.
- **Setup:** `_setup_step_logger()` creates the `logs/` directory if needed, attaches a single `FileHandler` to the logger `chatbot.run`, and disables propagation so only this file receives the messages. No console output is sent to the log file.

---

## 3. Configuration: src/config.py

**Role:** Central settings from environment and `.env`.

- **Settings:** Model path, temperature, max tokens, `use_mock_db` (FAISS backend), embedding model name, guardrails enabled/threshold, **log_file** (default `logs/chatbot.log` for step logging), chatbot name, retrieval_k, etc.
- **Usage:** Imported as `settings` everywhere (run_chatbot_agent.py, and inside components that need paths or flags). No direct DB or chat logic.

---

## 4. Database layer: src/db/

### sqlite_db.py

**Role:** Single SQLite database for all dynamic data.

- **Path:** Default `data/parking.db` (under project root).
- **Schema:** `users`, `reservations`, `reservation_requests` (id, nickname, dates_json, status), `working_hours`, `prices`, `availability`.
- **Seed:** If `users` is empty, inserts sample users (alice, bob, …), working_hours, prices, availability for a few dates.
- **API:** `user_exists`, `get_free_spaces`, `add_reservation`, `get_reservations_by_nickname`, `get_prices`, `get_working_hours`; for human-in-the-loop: `create_pending_request`, `get_request_status`, `set_request_status`, `get_pending_request_details`, `list_reservation_requests`. Only the admin API writes to `reservation_requests`.
- **Singleton:** `get_db()` returns one shared `SQLiteDB` instance so RAG and reservations use the same DB.

---

## 5. Vector store: src/vector_db/

**Role:** Provide text chunks and similarity search for RAG. Uses FAISS over `rag_data/parking_info.txt`.

### vector_store.py

- **VectorStore:** Holds embedding model name and `use_mock` flag. Lazy-inits:
  - `embedding_generator` — EmbeddingGenerator (sentence-transformers).
  - `client` — FAISSStore (loads and chunks `parking_info.txt`, builds FAISS index, semantic search).
- **Methods:** `similarity_search(query, k)`, `get_relevant_context(query, k)` — used by RAGSystem to get context from `parking_info.txt` content.

### embeddings.py

- **EmbeddingGenerator:** Loads a sentence-transformers model, exposes `generate_embedding(text)` and `generate_embeddings(texts)`. Used by VectorStore and FAISSStore.

### parking_info_loader.py

- **load_parking_info_chunks():** Reads `rag_data/parking_info.txt`, splits by blank lines into paragraphs; returns list of `{content, metadata}`. Used by FAISSStore.

### faiss_store.py

- **FAISSStore:** On init loads chunks via `load_parking_info_chunks()`, embeds them with the given EmbeddingGenerator, builds a FAISS index (cosine or L2 per config). **query(query_vector, limit):** returns top-k documents with id, content, metadata, score. Used as the RAG backend when `use_mock_db=True`.

---

## 6. Guardrails: src/guardrails/

**Role:** Prevent sensitive data from being sent to the LLM or shown to the user.

### guard_rails.py

- **GuardRails:** Wraps SensitiveDataFilter. Entry points:
  - `validate_query(query, allow_reservation_data=False)` — before using the query (general vs reservation). If `allow_reservation_data` True, only SSN and credit-card patterns are blocked.
  - `validate_response(response)` — after LLM; returns (safe, filtered_response), redacting if needed.
  - `filter_retrieved_documents(documents)` — filter/redact chunks before they are passed to the LLM.
- **Usage:** RAGSystem uses it for query validation and response filtering; chatbot uses it in the reservation branch with `allow_reservation_data=True`.

### sensitive_data_filter.py

- **SensitiveDataFilter:** Regex patterns for SSN, credit card, email, US phone. Optional NER (transformers) for person/org. `contains_sensitive_data(text)`, `filter_sensitive_data(text)`, `filter_documents(documents)`.
- **Usage:** Only via GuardRails.

---

## 7. Admin API: src/admin_api/

**Role:** Single entry point for reservation requests. Chatbot and admin console use it; only the API writes to `reservation_requests`.

- **app.py:** FastAPI: POST `/requests` (create), GET `/requests` (list, optional ?status=), GET `/requests/{id}`, PATCH `/requests/{id}` (status approved/rejected).
- **client.py:** `create_request(nickname, dates)`, `get_request_status(request_id)`, `get_pending_request_details(request_id)` (from DB). No DB fallback; raises `AdminAPIUnavailableError` if API unreachable.

---

## 7.1 MCP Reservation Logger: src/mcp_reservation_logger/

**Role:** The **chatbot's record_data node** (after administrator approval) logs each approval to `reservations_mcp/reservations_log.csv` using the **open-source** [@modelcontextprotocol/server-filesystem](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem) (Node.js). MCP server is started once (on first log) via npx and reuses the same session until exit.

- **client_fs.py:** Starts `npx -y @modelcontextprotocol/server-filesystem <reservations_mcp_dir>` once per run (on first log), connects over stdio, and reuses that session for every approval: **read_text_file** then **write_file** to append one row (name, car_number, reservation_period, approval_time UTC ISO). Requires Node.js/npx. See [MCP_FILESYSTEM_SETUP.md](MCP_FILESYSTEM_SETUP.md).

---

## 8. Chatbot layer: src/chatbot/

**Role:** Orchestrate conversation and the full pipeline (user interaction → administrator approval → data recording) via LangGraph.

### chatbot.py

- **ParkingChatbot:** Builds a LangGraph with three nodes for the pipeline:
  1. **user_interaction** — RAG context and chatbot: intent (reserve / show_reservations / general), collect reservation date or answer with RAG; when user submits dates and handler creates a pending request, sets `reservation_request_id` and routes to **wait_for_approval**.
  2. **wait_for_approval** — Administrator approval (human-in-the-loop): polls `get_request_status` until approved/rejected/timeout; sets `approval_result` and routes to **record_data** only when approved.
  3. **record_data** — Data recording after confirmation: calls `apply_approved_request` (DB), then gets (nickname, dates, plates) and calls MCP `log_reservation_action_via_fs_mcp` to append one row to the CSV.
- **State:** `messages` (append), optional `reservation_request_id` and `approval_result` for the reservation flow.
- **Edges:** user_interaction → (if `reservation_request_id`) wait_for_approval else END; wait_for_approval → (if approved) record_data else END; record_data → END.
- **_looks_like_date(text):** True if input matches a single date (YYYY-MM-DD) or date range; used when in reservation to route date input to reservation logic.
- **chat(user_input, conversation_history):** Invoke graph, return last AI message content.

**Uses:** RAGSystem, ReservationHandler, admin_api.client (get_request_status, get_pending_request_details), mcp_reservation_logger.client_fs (from record_data node).

### rag_system.py

- **RAGSystem:** Combines vector store, LLM, guard rails, and optional `db`. Builds a prompt template (context + question → answer). Uses either a QA chain (if available) or a simple “format prompt + llm.invoke” path.
- **classify_intent(user_input):** Uses the LLM with a short prompt to classify the user's intent into **reserve**, **show_reservations**, or **general**. Used by the chatbot for routing each turn.
- **generate_response(query, conversation_history=None):** When answering a general question, the chatbot passes Retrieval uses top-k (config, default 3). No conversation history is included in the prompt.
  1. Retrieve documents: `vector_store.similarity_search(query, k)` (from parking_info.txt).
  3. Append dynamic context: `db.get_prices()`, `db.get_working_hours()` formatted as text.
  4. Validate query with guard_rails; filter retrieved documents.
  5. Build context string, call LLM with prompt.
  6. Validate and filter response with guard_rails, return.
- **Uses:** VectorStore, LLMProvider, GuardRails, SQLiteDB (optional).

### llm_setup.py

- **LLMProvider:** Loads GPT4All model from `model_path`, exposes `get_llm()`. Used by RAGSystem to run the QA/LLM step. No direct use of DB or guardrails.

### reservation_handler.py

- **ReservationState:** Holds either a single date or a range (start_date, end_date); `get_dates_to_reserve()` returns a list of YYYY-MM-DD strings.
- **Helpers:** `_parse_single_date`, `_parse_date_range`, `_date_range_to_list` — used to accept "YYYY-MM-DD" or "YYYY-MM-DD - YYYY-MM-DD".
- **ReservationHandler:** Holds `db`, `current_reservation`, `_nickname`. `start_reservation()` creates a new state and asks for date. `process_user_input(text)` parses date or range, checks `db.get_free_spaces(date)` for each date, then **create_request(nickname, dates)** via admin API client (no direct add_reservation); returns `(True, "pending_approval", request_id)`. **apply_approved_request(request_id)** loads details via client and calls db.add_reservation for each date (used by chatbot after admin approval).
- **Uses:** SQLiteDB and admin_api.client.

---

## 9. How components connect

- **run_chatbot_agent.py** → get_db, initialize_system (VectorStore, GuardRails, LLMProvider, RAGSystem, ReservationHandler, ParkingChatbot).
- **run_admin_console_agent.py** → admin API (GET/PATCH), LLMProvider; approves/rejects only (MCP logging is done by the chatbot's record_data node when it sees approval).
- **ParkingChatbot** → RAGSystem, ReservationHandler; ReservationHandler uses admin_api.client for create and status.
- **RAGSystem** → VectorStore, LLMProvider, GuardRails, SQLiteDB (prices, working_hours). Retrieval k=3, no conversation history in prompt.
- **ReservationHandler** → SQLiteDB (availability, reservations), admin_api.client (create_request, get_pending_request_details).
- **VectorStore** → EmbeddingGenerator, FAISSStore.

---

## 10. Tests (tests/)

- **test_db.py** — SQLiteDB: user_exists, add_reservation, get_reservations, get_free_spaces, reservation_requests methods.
- **test_admin_api.py** — API endpoints (POST/GET/PATCH).
- **test_mcp_reservation_logger.py** — client_fs: CSV header/append helpers, module exports.
- **test_reservation_handler.py** — ReservationState, ReservationHandler (create_request via client, apply_approved_request); admin client mocked.
- **test_chatbot.py** — Show reservations, RAG, reservation flow with mocked admin API.
- **test_rag_system.py** — RAGSystem unit tests: generate_response uses retrieved and dynamic context in the prompt, no-context fallback message; classify_intent returns reserve / show_reservations / general (including typo and “reserve” fallbacks).
- **test_guardrails.py** — GuardRails: block SSN, card, email, phone; allow safe query and reservation date.
- **tests_system/** — System tests (load + integration). Not run by `make tests` or CI. Run with `make tests-system` or `pytest tests_system/ -v`. Contains load tests (chatbot, admin confirmation, MCP recording) and integration tests for orchestration (approved, rejected, general no-escalation).

Tests use temp SQLite files and do not start the full app or load the local LLM.

This is the full code structure and how each part is used in the project.
