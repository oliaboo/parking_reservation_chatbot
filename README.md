# Parking Reservation Chatbot

Chatbot for parking information and reservations (RAG + LangGraph). Identifies users by nickname. Reservations are **escalated to a human administrator**: the chatbot sends a pending request via the admin REST API, the admin approves or rejects in the admin console, and the chatbot then completes or cancels. Uses FAISS over `rag_data/parking_info.txt` for RAG; SQLite for users, reservations, and admin request state.

> **Want a high-level overview?** See **[docs/SYSTEM_SUMMARY.md](docs/SYSTEM_SUMMARY.md)**. For the human-in-the-loop flow (admin API, admin console, polling), see **[docs/DESIGN_HUMAN_IN_THE_LOOP.md](docs/DESIGN_HUMAN_IN_THE_LOOP.md)**.

### Screenshots

| Component | Description |
|-----------|-------------|
| [![Chatbot run](docs/images/example_chatbot_run.png)](docs/images/example_chatbot_run.png) | **Chatbot** — Launched app and sample chat (info, reserve, show reservations). |
| [![Admin API run](docs/images/example_admin_api_run.png)](docs/images/example_admin_api_run.png) | **Admin API** — REST server running (e.g. uvicorn, listing/serving requests). |
| [![Admin console agent run](docs/images/example_admin_agent_run.png)](docs/images/example_admin_agent_run.png) | **Admin console** — Pending requests list and approve/reject interaction. |

## Setup

### 1. Create and use a virtual environment

```bash
# Create venv in project root
python3 -m venv .venv

# Activate (Unix/macOS)
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Optional: environment variables

```bash
cp .env_example .env
# Edit .env if you need to change model path, log level, etc.
```

### 4. Node.js (for approval logging to CSV)

If you use human-in-the-loop and want approvals written to `reservations_mcp/reservations_log.csv`, install **Node.js** (which includes **npx**) where the **chatbot** runs. The chatbot's record_data node uses the MCP filesystem server via `npx` to append log rows when it sees an approval.

```bash
node -v   # e.g. v18+
npx -v
```

See [docs/MCP_FILESYSTEM_SETUP.md](docs/MCP_FILESYSTEM_SETUP.md) for details. Without Node.js/npx, the chatbot still works; only the CSV logging will be skipped.

## Run

Set **PYTHONPATH** to the project root (e.g. `export PYTHONPATH=/path/to/parking_reservation_chatbot`). For **human-in-the-loop** reservations you need the following processes and **ADMIN_API_BASE_URL** (e.g. `http://127.0.0.1:8000`) in `.env` (see [docs/DESIGN_HUMAN_IN_THE_LOOP.md](docs/DESIGN_HUMAN_IN_THE_LOOP.md).):

1. **Admin API** (from project root): `python run_admin_api.py` (or `make run_admin_api`)
2. **Admin console** (in another terminal): `python run_admin_console_agent.py` (or `make run_admin`) — list pending requests, type e.g. `approve 15` or `reject 8` to approve/reject by request id.
3. **Chatbot**: `python run_chatbot_agent.py` (or `make run_chatbot`) — enter nickname, then chat; when the admin approves, the chatbot saves the reservation and appends a row to `reservations_mcp/reservations_log.csv` via the **open-source MCP filesystem server** ([@modelcontextprotocol/server-filesystem](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem)). **Node.js/npx** is required for that CSV logging (where the chatbot runs). See **[docs/MCP_FILESYSTEM_SETUP.md](docs/MCP_FILESYSTEM_SETUP.md)** for setup and prerequisites.
(Reservation requests wait for admin approval before being saved; the chatbot polls until approved/rejected.)

To run only the chatbot without admin approval, the API must still be reachable if you use reservations (or configure accordingly); see [docs/DESIGN_HUMAN_IN_THE_LOOP.md](docs/DESIGN_HUMAN_IN_THE_LOOP.md).

## Tests

```bash
pytest tests/ -v
```

Or from the project root: **`make tests`**. See the **Makefile** for shortcuts: `make run_chatbot`, `make run_admin`, `make run_admin_api`, `make lint`, `make evaluation`, etc.

## Linting

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting (configured in `pyproject.toml`):

```bash
# Check code
ruff check .

# Auto-fix safe issues (e.g. import order)
ruff check . --fix

# Format code
ruff format .
```

## Evaluation report (system performance)

To generate an **evaluation report** on retrieval accuracy and performance (Recall@K, Precision@K, latency):

```bash
python run_evaluation.py
```

To save the report to a file:

```bash
python run_evaluation.py -o evaluation_report.txt
```

Use `--remove-index` to delete the FAISS index files after the run (`rag_data/faiss_parking.index`, `rag_data/faiss_parking_docs.json`), so the next run rebuilds the index (e.g. after changing `FAISS_METRIC` or `parking_info.txt`). See [docs/EVALUATION.md](docs/EVALUATION.md) for all options and metric definitions.

**FAISS similarity:** Set `FAISS_METRIC=cosine` (default) or `FAISS_METRIC=l2` in `.env`. After changing the metric, delete `rag_data/faiss_parking.index` (and optionally `rag_data/faiss_parking_docs.json`) so the index is rebuilt on next run. Details in [docs/EVALUATION.md](docs/EVALUATION.md#faiss-similarity-metric).

## Documentation

Technical docs are in **`docs/`**:

- **[docs/SYSTEM_SUMMARY.md](docs/SYSTEM_SUMMARY.md)** — What the system does, user interaction (chat, reserve, show reservations), data, RAG, guardrails, evaluation
- **[docs/DESIGN_HUMAN_IN_THE_LOOP.md](docs/DESIGN_HUMAN_IN_THE_LOOP.md)** — Human-in-the-loop: admin API, admin console (LLM-interpreted commands), escalation and polling
- **[docs/INDEX.md](docs/INDEX.md)** — Doc index and quick overview
- **[docs/DATA_FLOW.md](docs/DATA_FLOW.md)** — Startup, chat loop, RAG, reservations, escalation
- **[docs/CODE_STRUCTURE.md](docs/CODE_STRUCTURE.md)** — Project layout and modules
- **[docs/TESTING_GUARDRAILS.md](docs/TESTING_GUARDRAILS.md)** — Testing guardrails
- **[docs/EVALUATION.md](docs/EVALUATION.md)** — RAG evaluation (Recall@K, Precision@K, latency)
- **[docs/MCP_FILESYSTEM_SETUP.md](docs/MCP_FILESYSTEM_SETUP.md)** — Using the open-source MCP filesystem server for logging approvals to CSV

## Requirements

- **Python 3.10+**
- `requirements.txt`: LangChain, LangGraph, GPT4All, sentence-transformers, pytest, ruff (linting), etc. SQLite is used via the standard library (no extra package).
- **Node.js** (and **npx**): required only for the chatbot's approval logging to CSV via the MCP filesystem server. Optional if you do not use that feature.
