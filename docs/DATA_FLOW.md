# Data Flow

This document describes the end-to-end data flow: from application startup through each user message to database and responses.

---

## 1. Application startup

```
run_chatbot_agent.py (main)
    │
    ├─► Set project root on sys.path, chdir to project root
    ├─► setup_logging()
    ├─► get_db()  →  SQLiteDB (data/parking.db), singleton
    │
    ├─► Nickname loop:
    │       input("Enter your nickname...")
    │       db.user_exists(nickname)  →  until True
    │
    └─► initialize_system(nickname)
```

**initialize_system(nickname)** builds the full stack:

1. **VectorStore** — embedding model (e.g. sentence-transformers), FAISS-backed vector store that loads and embeds chunks from `parking_info.txt`.
2. **GuardRails** — enabled by config, wraps SensitiveDataFilter (patterns for SSN, card, email, phone).
3. **LLMProvider** — GPT4All, loads local model from `settings.model_path` (e.g. `local_models/Meta-Llama-3-8B-Instruct.Q4_0.gguf`).
4. **RAGSystem** — vector_store + llm_provider + guard_rails + **db** (for prices and working hours in context).
5. **ReservationHandler** — db + set_nickname(nickname).
6. **ParkingChatbot** — rag_system + reservation_handler, compiles LangGraph.

All of these are created once per run; the same `db` instance is shared by RAG and ReservationHandler.

---

## 2. Chat loop (per user message)

```
User types message  →  run_chatbot_agent.py: chatbot.chat(user_input, conversation_history)
                            │
                            ▼
                    ParkingChatbot.chat()
                            │
                            ├─► messages = history + HumanMessage(user_input)
                            ├─► state = {"messages": messages}
                            └─► result = self.graph.invoke(state)
```

So each turn is one invocation of the LangGraph with the current message and history.

---

## 3. LangGraph flow (one invoke)

The graph has a single node: **handle_general_query**. Every turn runs this node; it uses the LLM to classify intent and then delegates to the right logic.

```
                    ┌─────────────────────────────┐
                    │   handle_general_query      │
                    │   (always runs first)      │
                    └──────────────┬──────────────┘
                                   │
         Reservation in progress?  │  Else: LLM classify_intent(user_input)
         If date-like → _handle_   │  → reserve | show_reservations | general
         reservation; else intent  │
         (show/general clear flow) │
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
    _handle_show_reservations   _handle_reservation   RAG generate_response
    (list dates from DB)        (guardrails + date     (retrieve + LLM answer)
                                → DB)                         │
              │                    │                    │
              └────────────────────┴────────────────────┘
                                   │
                                   ▼
                            END  →  last AI message returned to run_chatbot_agent.py
```

**Intent (LLM-based):**

- **reserve** — user wants to make/book a new parking reservation → `_handle_reservation`.
- **show_reservations** — user wants to see/list their existing reservations → `_handle_show_reservations`.
- **general** — any other question or statement → RAG: `rag_system.generate_response(user_input)` (retrieve top-k, default 3; no conversation history in prompt; LLM answer).

**Reservation in progress:** If `get_current_reservation()` is not `None` (bot is waiting for a date), the message is first checked: if it **looks like a date** (YYYY-MM-DD or range), it is passed to `_handle_reservation`. Otherwise intent is classified so the user can say "show my reservations", "cancel", or ask a general question; **show_reservations** or **general** clear the current reservation and run that path, so the user is not stuck in the reservation flow.

---

## 4. Handler flows

### 4.1 handle_show_reservations

- **Input:** state with messages (user already identified by nickname at startup).
- **Data:** `reservation_handler.get_active_reservations()` → `db.get_reservations_by_nickname(nickname)` → list of dates from `reservations` table.
- **Output:** One AI message: "Your active reservations: - date1\n- date2..." or "You have no active reservations."

No RAG, no LLM; direct read from SQLite.

---

### 4.2 handle_reservation

- **Guardrails:** `rag_system.guard_rails.validate_query(user_input, allow_reservation_data=True)` — blocks SSN/card only, allows names/dates.
- If not safe → append error AI message and return.
- **If no current reservation:** `reservation_handler.start_reservation()` → ask for date (or range).
- **If current reservation exists:** `reservation_handler.process_user_input(user_input)`:
  - Parse single date (YYYY-MM-DD) or range; for each date `db.get_free_spaces(date)`; if any has 0 free spaces, fail and clear reservation.
  - **create_request(nickname, dates)** via admin API client (POST `/requests`). No direct add_reservation. Returns `(True, "pending_approval", request_id)`.
  - Chatbot informs user and **polls** `get_request_status(request_id)` every 2 s (max 300 s). On **approved**: `apply_approved_request(request_id)` (load details from DB, then `db.add_reservation` per date). On **rejected** or timeout: show message.
- Data written: `reservations` only after admin approval. Read: `availability`, then API for status, then DB for request details on approve.

---

### 4.3 handle_general_query

- **Reservation in progress:** If there is an active reservation (waiting for date), check whether the message **looks like a date** (e.g. YYYY-MM-DD or range). If yes → call `_handle_reservation(state)` (see 4.2). If no, call **LLM** to classify intent so the user can do something else: **show_reservations** or **general** clear the reservation and run that handler/RAG; **reserve** → `_handle_reservation(state)`.
- **Else:** Call **LLM** via `rag_system.classify_intent(user_input)` → returns **reserve** | **show_reservations** | **general**.
  - **reserve** → call `_handle_reservation(state)`.
  - **show_reservations** → call `_handle_show_reservations(state)` (see 4.1).
  - **general** → RAG response:
    1. **Query validation:** `rag_system.guard_rails.validate_query(user_input)` — full sensitive-data check (SSN, card, email, phone). If not safe → return error message, no RAG.
    2. **Retrieve context:** inside `rag_system.generate_response(user_input)`:
       - **Vector store:** `vector_store.similarity_search(query, k)` (k from config, default 3) → FAISS from `parking_info.txt` chunks. No conversation history in the prompt.
       - **Dynamic context:** `db.get_prices()` and `db.get_working_hours()` → formatted text appended to context.
       - **Guardrails:** `guard_rails.filter_retrieved_documents(documents)`.
    3. **LLM:** Prompt = "Use the following context... Context: {vector + dynamic}\n\nQuestion: {query}\nAnswer:". LLM generates answer.
    4. **Response guardrails:** `guard_rails.validate_response(response)` → redact sensitive data in the answer.
    5. Return filtered response as one AI message.

Data read: vector store (from file), `prices` and `working_hours` tables. Nothing written.

---

## 5. Database usage summary

| Component            | Reads from DB                    | Writes to DB        |
|----------------------|----------------------------------|---------------------|
| run_chatbot_agent.py (startup) | users (user_exists)        | —                   |
| RAGSystem            | prices, working_hours            | —                   |
| ReservationHandler   | availability; request details (on approve) | reservations (only after admin approval) |
| Admin API            | reservation_requests             | reservation_requests (create, PATCH status) |
| Show reservations   | reservations (by nickname)       | —                   |

**Admin flow (separate processes):** `run_admin_api.py` serves REST API (create/list/patch requests). `run_admin_console_agent.py` calls GET `/requests` and PATCH `/requests/{id}`; the LLM interprets commands like "approve 15" / "reject 8" and the console applies the corresponding PATCH. See [Design: Human in the loop](DESIGN_HUMAN_IN_THE_LOOP.md).

**Files and storage:**

- **Static text:** `parking_info.txt` → split into chunks → embedded and stored in FAISS index (on disk in rag_data/).
- **Dynamic data:** SQLite `data/parking.db` — users, reservations, working_hours, prices, availability, reservation_requests.

---

## 6. Configuration and environment

- **Config:** `src/config.py` — `Settings` (pydantic-settings), loads from `.env` and env vars.
- **Paths:** Model path, DB path (default `data/parking.db`), log file, embedding model name, retrieval_k, guardrails on/off, etc.
- **run_chatbot_agent.py** does not pass DB path explicitly; `get_db()` uses default path under project root, so running from project root ensures the same DB file is used everywhere.

This is the complete data flow from startup through each user message to the database and back to the user.
