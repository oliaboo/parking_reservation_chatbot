# Task 2: Implementation of Human-in-the-Loop Agent

Flow: first agent collects reservation details → escalate to pending request → admin responds via REST → chat polls until approved/rejected → on approve write to `reservations`.

---

## 1. Data layer: pending requests

**Where:** `src/db/sqlite_db.py` (extend) or a small `src/db/pending_requests.py` that uses the same DB path.

**Schema (new table in same DB):**

```text
reservation_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nickname TEXT NOT NULL,
  dates_json TEXT NOT NULL,        -- e.g. '["2025-03-10","2025-03-11"]'
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
  created_at TEXT NOT NULL,        -- ISO datetime
  updated_at TEXT                  -- set when status changes
)
```

**New API (on SQLiteDB or a PendingRequestStore):**

- `create_pending_request(nickname: str, dates: List[str]) -> str`  
  Insert row, return `request_id` (e.g. str of id).
- `get_request_status(request_id: str) -> Optional[Literal["pending","approved","rejected"]]`  
  Return status or None if not found.
- `set_request_status(request_id: str, status: Literal["approved","rejected"]) -> bool`  
  Update row and `updated_at`; return True if updated.
- `get_pending_request_details(request_id: str) -> Optional[Tuple[str, List[str]]]`  
  Return (nickname, dates) for the request (used when applying approval).

Keep `reservations` as-is; write to it only when status becomes `approved`.

---

## 2. Admin REST API

**Where:** Package `src/admin_api/` — implemented with **FastAPI**.

**Stack:** FastAPI app (`src/admin_api/app.py`) served with **uvicorn**. Same DB layer as the chatbot (`src/db/sqlite_db.py`, `get_db()`); both processes use the same `data/parking.db` when run on the same host. For chatbot and admin on different VMs, the DB must be shared (e.g. network-mounted SQLite file or a central DB server).

**Endpoints:**

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/requests` | List all requests (optional query `?status=pending` \| `approved` \| `rejected`). Response: `[{ "id", "nickname", "dates", "status", "created_at", "updated_at" }, ...]`. |
| GET | `/requests/{request_id}` | Get one request (for admin UI or polling). |
| PATCH | `/requests/{request_id}` | Body: `{ "status": "approved" \| "rejected" }`. Update DB, return 200; 404 if not found, 409 if request is no longer pending. |

**Run:** Separate process: `PYTHONPATH=. python run_admin_api.py` or `uvicorn src.admin_api.app:app --host 0.0.0.0 --port 8000`. Requires `fastapi` and `uvicorn[standard]` in `requirements.txt`.

---

## 3. Second agent (LangChain) — “admin side”

**Where:** e.g. `src/chatbot/admin_agent.py` or `src/admin_agent/`.

**Role:**

- **Input:** Reservation payload `{ nickname, dates[] }`.
- **Output:** Human-readable summary string (for admin UI or future email).
- No need to “receive” REST response: admin uses REST; the agent only **formats the request** and optionally a “request id” for reference.

**Suggested interface:**

```text
class AdminRequestAgent:
    def format_request_for_admin(self, nickname: str, dates: List[str]) -> str
        # LangChain: prompt + optional LLM to turn payload into a short, clear message.
        # Fallback: simple template "User {nickname} requests: {dates}."
```

This agent is called when creating the pending request, so the admin UI (or GET `/requests`) can show a nice message. The actual “sending” is “write to DB + admin sees it via REST.”

---

## 4. Escalation and polling (first agent + reservation flow)

**Where:** `src/chatbot/reservation_handler.py` and `src/chatbot/chatbot.py`.

**4.1 ReservationHandler**

- Add dependency: something that can create a pending request and return its id (e.g. DB or a small `PendingRequestService`).
- In `process_user_input`, **instead of** calling `self.db.add_reservation(...)` in a loop after availability check:
  1. Call `create_pending_request(self._nickname, dates_to_reserve)` and get `request_id`.
  2. Clear `current_reservation` (same as now).
  3. Return a **special** result so the chatbot knows to poll: e.g. `(True, "pending_approval", request_id)` or a small dataclass `ReservationResult(success, message, pending_request_id=None)`.

- Add a method the chatbot will use after approval:

  - `apply_approved_request(request_id: str) -> Tuple[bool, str]`  
    Load (nickname, dates) for that request, call `db.add_reservation` for each date, then update request status to `approved` (or delete/ignore). Return (True, "Reservation saved...") or (False, error).

**4.2 Chatbot (`chatbot.py`) — `_handle_reservation`**

- After `process_user_input`, check if the result is “pending_approval” + `request_id`.
- If yes:
  1. Append an AI message like “Request sent to administrator. Waiting for response…”
  2. **Poll** in a loop: every 2–3 s call `get_request_status(request_id)` (from DB or a thin service). Break when status is `approved` or `rejected` or after timeout (e.g. 2–5 minutes).
  3. If `approved`: call `reservation_handler.apply_approved_request(request_id)`, then append AI message with the success text.
  4. If `rejected` or timeout: append AI message “Administrator declined.” or “No response in time. Please try again later.”
- If not pending (normal success/failure): keep current behavior (append one AI message with success or error).

So the “wait” is implemented in the same synchronous chat turn: poll in `_handle_reservation` until the admin has set status via REST.

---

## 5. Wiring and config

- **run.py (or init):** Build DB (with new table), ReservationHandler, and optionally AdminRequestAgent. Pass a “pending request store” (DB or adapter) into ReservationHandler so it can create and query pending requests.
- **Config:** Optional: admin API base URL if the chat process calls an HTTP API for status (instead of reading DB directly). Simpler: both chat and admin API use the same DB, so no HTTP from chat to API; only the admin uses the API.
- **Starting the admin API:** Either a second script `run_admin_api.py` that runs `uvicorn admin_api.app:app --host 0.0.0.0 --port 8000`, or document that the admin runs it separately so they can open GET `/requests` and PATCH to approve/reject.

---

## 6. Call flow (summary)

```text
User: "2025-03-10 - 2025-03-11"
  → handle_general_query → _handle_reservation
  → reservation_handler.process_user_input("2025-03-10 - 2025-03-11")
  → availability OK → create_pending_request(nickname, dates) → request_id
  → return (pending_approval, request_id)
  → chatbot appends "Request sent. Waiting for administrator..."
  → loop: get_request_status(request_id) every 2–3 s
  → [Admin in another terminal/browser: GET /requests, then PATCH /requests/1 {"status":"approved"}]
  → status becomes "approved"
  → reservation_handler.apply_approved_request(request_id) → add_reservation for each date
  → chatbot appends "Reservation saved for 2025-03-10 to 2025-03-11. You're all set!"
  → state returned to user
```

---

## 7. File layout

```text
src/
  db/
    sqlite_db.py          # add reservation_requests table + create_pending_request, get_request_status, set_request_status, get_pending_request_details
  admin_api/
    __init__.py
    app.py                # FastAPI app: GET/PATCH /requests, uses get_db() and the new methods
  chatbot/
    reservation_handler.py # escalation: create_pending_request instead of add_reservation; apply_approved_request
    chatbot.py            # _handle_reservation: detect pending, poll, then apply or show reject/timeout
  admin_agent.py (optional)
    # AdminRequestAgent: format_request_for_admin(nickname, dates) for human-readable text
```

Tests: `tests/test_admin_api.py`, `tests/test_reservation_escalation.py` (mock DB or in-memory SQLite).
