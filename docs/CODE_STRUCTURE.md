# Code Structure

This document describes the project layout and how each module is used.

---

## 1. Project layout

```
parking_reservation_chatbot/
├── run.py                 # Entry point: nickname prompt, init, chat loop
├── data/
│   ├── parking_info.txt   # Static content for RAG (location, capacity, booking process, etc.)
│   ├── parking.db         # SQLite DB (users, reservations, prices, working_hours, availability)
│   ├── faiss_parking.index
│   └── faiss_parking_docs.json
├── requirements.txt
├── .env / .env_example
├── local_models/          # Local LLM file (e.g. Meta-Llama-3-8B-Instruct.Q4_0.gguf)
├── logs/                  # chatbot.log (if logging to file)
├── docs/                  # Documentation (this folder)
├── tests/                 # Pytest tests
└── src/
    ├── __init__.py
    ├── config.py          # Settings (env, model path, guardrails, etc.)
    ├── db/                # SQLite layer
    │   ├── __init__.py
    │   └── sqlite_db.py   # SQLiteDB, get_db(), schema, seed data
    ├── vector_db/         # Vector store (FAISS over parking_info.txt)
    │   ├── __init__.py
    │   ├── vector_store.py
    │   ├── embeddings.py
    │   ├── parking_info_loader.py   # Load and chunk parking_info.txt
    │   ├── faiss_store.py           # FAISS index for similarity search
    │   └── mock_weaviate.py         # Optional mock for tests
    ├── guardrails/        # Sensitive data filtering
    │   ├── __init__.py
    │   ├── guard_rails.py
    │   └── sensitive_data_filter.py
    └── chatbot/           # Chat logic, RAG, reservation, LLM
        ├── __init__.py
        ├── chatbot.py     # ParkingChatbot, LangGraph workflow
        ├── rag_system.py   # RAGSystem (retrieve + generate)
        ├── llm_setup.py    # LLMProvider (GPT4All)
        └── reservation_handler.py
```

---

## 2. Entry point: run.py

**Role:** Bootstrap the app and run the interactive chat.

- **Path and cwd:** Adds project root to `sys.path`, `os.chdir(project_root)` so imports and paths like `data/parking.db` and `local_models/` work.
- **Imports:** All `src.*` modules used by the app (config, vector_db, guardrails, chatbot, db).
- **Logging:** Configures stdout and optional log file (loguru or stdlib).
- **main():**
  1. `get_db()` — ensure SQLite DB exists (singleton).
  2. Nickname loop: `input()` until `db.user_exists(nickname)`.
  3. `initialize_system(nickname)` — build VectorStore, GuardRails, LLMProvider, RAGSystem, ReservationHandler, ParkingChatbot.
  4. Chat loop: `input()` → `chatbot.chat(user_input, conversation_history)` → print response, append to history; exit on "quit"/"exit".

**Uses:** config.settings, get_db, VectorStore, GuardRails, LLMProvider, RAGSystem, ReservationHandler, ParkingChatbot.

---

## 3. Configuration: src/config.py

**Role:** Central settings from environment and `.env`.

- **Settings:** Model path, temperature, max tokens, Weaviate URL (for future use), `use_mock_db`, embedding model name, guardrails enabled/threshold, log level/file, chatbot name, retrieval_k, etc.
- **Usage:** Imported as `settings` everywhere (run.py, and inside components that need paths or flags). No direct DB or chat logic.

---

## 4. Database layer: src/db/

### sqlite_db.py

**Role:** Single SQLite database for all dynamic data.

- **Path:** Default `data/parking.db` (under project root).
- **Schema:** `users` (nickname, plates), `reservations` (nickname, date), `working_hours`, `prices`, `availability` (date, free_spaces).
- **Seed:** If `users` is empty, inserts sample users (alice, bob, …), working_hours, prices, availability for a few dates.
- **API:**
  - `user_exists(nickname)` — used at startup.
  - `get_free_spaces(date)`, `add_reservation(nickname, date)`, `get_reservations_by_nickname(nickname)` — used by ReservationHandler and show-reservations.
  - `get_prices()`, `get_working_hours()` — used by RAGSystem for dynamic context.
- **Singleton:** `get_db()` returns one shared `SQLiteDB` instance so RAG and reservations use the same DB.

---

## 5. Vector store: src/vector_db/

**Role:** Provide text chunks and similarity search for RAG. Uses FAISS over `parking_info.txt`; production Weaviate is optional.

### vector_store.py

- **VectorStore:** Holds embedding model name and `use_mock` flag. Lazy-inits:
  - `embedding_generator` — EmbeddingGenerator (sentence-transformers).
  - `client` — FAISSStore (loads and chunks `parking_info.txt`, builds FAISS index, semantic search).
- **Methods:** `similarity_search(query, k)`, `get_relevant_context(query, k)` — used by RAGSystem to get context from `parking_info.txt` content.

### embeddings.py

- **EmbeddingGenerator:** Loads a sentence-transformers model, exposes `generate_embedding(text)` and `generate_embeddings(texts)`. Used by VectorStore and FAISSStore.

### parking_info_loader.py

- **load_parking_info_chunks():** Reads `data/parking_info.txt`, splits by blank lines into paragraphs; returns list of `{content, metadata}`. Shared by FAISSStore and mock_weaviate.

### faiss_store.py

- **FAISSStore:** On init loads chunks via `load_parking_info_chunks()`, embeds them with the given EmbeddingGenerator, builds a FAISS IndexFlatIP (cosine via normalized vectors). **query(query_vector, limit):** returns top-k documents with id, content, metadata, score. Used as the default RAG backend when `use_mock=True`.

### mock_weaviate.py

- **MockWeaviateClient:** In-memory fallback using the same chunking (parking_info_loader). Used in tests or when FAISS is not desired; not used by default in run.py.

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

## 7. Chatbot layer: src/chatbot/

**Role:** Orchestrate conversation: classify intent, call RAG or reservation logic or show reservations, return one reply per turn.

### chatbot.py

- **ParkingChatbot:** Builds a LangGraph `StateGraph(Dict)` with nodes: classify_intent, handle_general_query, handle_reservation, handle_show_reservations. State is `{"messages": [...]}`.
- **classify_intent:** Sets `state["intent"]` to "show_reservations" | "reservation" | "general" from keywords in the last user message.
- **Routing:** Conditional edges from classify_intent to the three handlers; each handler appends an AIMessage and goes to END.
- **handle_general_query:** Re-route to reservation if there is an active reservation or reservation keywords; else call `rag_system.generate_response(user_input)` and append response (with error handling).
- **handle_reservation:** Validate query with guardrails (reservation mode), then start reservation or process_user_input (date/range) and return the handler’s message.
- **handle_show_reservations:** `reservation_handler.get_active_reservations()` → format and return as one AI message.
- **chat(user_input, conversation_history):** Build state with messages, invoke graph, return last AI message content.

**Uses:** RAGSystem, ReservationHandler (and thus db for reservations and show-reservations).

### rag_system.py

- **RAGSystem:** Combines vector store, LLM, guard rails, and optional `db`. Builds a prompt template (context + question → answer). Uses either a QA chain (if available) or a simple “format prompt + llm.invoke” path.
- **generate_response(query):**
  1. Retrieve documents: `vector_store.similarity_search(query, k)` (from parking_info.txt).
  2. Append dynamic context: `db.get_prices()`, `db.get_working_hours()` formatted as text.
  3. Validate query with guard_rails; filter retrieved documents.
  4. Build context string, call LLM with prompt.
  5. Validate and filter response with guard_rails, return.
- **Uses:** VectorStore, LLMProvider, GuardRails, SQLiteDB (optional).

### llm_setup.py

- **LLMProvider:** Loads GPT4All model from `model_path`, exposes `get_llm()`. Used by RAGSystem to run the QA/LLM step. No direct use of DB or guardrails.

### reservation_handler.py

- **ReservationState:** Holds either a single date or a range (start_date, end_date); `get_dates_to_reserve()` returns a list of YYYY-MM-DD strings.
- **Helpers:** `_parse_single_date`, `_parse_date_range`, `_date_range_to_list` — used to accept "YYYY-MM-DD" or "YYYY-MM-DD - YYYY-MM-DD".
- **ReservationHandler:** Holds `db`, `current_reservation`, `_nickname`. `start_reservation()` creates a new state and asks for date. `process_user_input(text)` parses date or range, checks `db.get_free_spaces(date)` for each date, then `db.add_reservation(nickname, date)` for each, then clears current reservation and returns success or error message.
- **Uses:** SQLiteDB only (no RAG, no LLM).

---

## 8. How components connect

- **run.py** → get_db, initialize_system (VectorStore, GuardRails, LLMProvider, RAGSystem(db), ReservationHandler(db), ParkingChatbot(rag_system, reservation_handler)).
- **ParkingChatbot** → RAGSystem (general answers), ReservationHandler (reservations and show reservations).
- **RAGSystem** → VectorStore (parking_info.txt), LLMProvider (local LLM), GuardRails, SQLiteDB (prices, working_hours).
- **ReservationHandler** → SQLiteDB (availability, reservations).
- **VectorStore** → EmbeddingGenerator, MockWeaviateClient (which reads parking_info.txt and, when given an embedding generator, embeds chunks for real similarity search).

No circular imports: config and db have no chatbot/vector/guardrail imports; chatbot imports rag and reservation; rag imports vector, guardrails, llm, and db.

---

## 9. Tests (tests/)

- **test_db.py** — SQLiteDB: user_exists, add_reservation, get_reservations, get_free_spaces.
- **test_reservation_handler.py** — ReservationState (single/range), ReservationHandler (nickname required, full flow, date range).
- **test_chatbot.py** — Show reservations returns saved dates; no cross-user leakage.
- **test_guardrails.py** — GuardRails: block SSN, card, email, phone; allow safe query and reservation date.

Tests use temp SQLite files and do not start the full app or load the local LLM.

This is the full code structure and how each part is used in the project.
