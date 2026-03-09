# Parking Reservation Chatbot

Chatbot for parking information and reservations (RAG + LangGraph). Identifies users by nickname, stores reservations in SQLite, uses mock Weaviate with content from `parking_info.txt`.

## Setup

### 1. Create and use a virtual environment

```bash
# Create venv in project root
python3 -m venv .venv

# Activate (Unix/macOS)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate
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

## Run

From the **project root**:

```bash
python run.py
```

Enter a valid nickname (e.g. `alice`, `bob`) when prompted, then chat: ask for info, say "reserve" and give a date (YYYY-MM-DD), or "show my reservations".

## Tests

```bash
pytest tests/ -v
```

## RAG evaluation (Recall@K, Precision@K, latency)

To evaluate retrieval accuracy and performance:

```bash
python run_evaluation.py
```

This runs the same vector store as the chatbot on a fixed set of queries and reports mean **Recall@1/3/5**, **Precision@1/3/5**, and **retrieval latency** (no LLM required). See [docs/EVALUATION.md](docs/EVALUATION.md) for details.

Or with the venv Python explicitly:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Documentation

Technical docs are in the **`docs/`** folder:

- **[docs/README.md](docs/README.md)** — Index and overview
- **[docs/DATA_FLOW.md](docs/DATA_FLOW.md)** — End-to-end data flow (startup, chat, RAG, reservations, DB)
- **[docs/CODE_STRUCTURE.md](docs/CODE_STRUCTURE.md)** — Project layout and how each module is used
- **[docs/TESTING_GUARDRAILS.md](docs/TESTING_GUARDRAILS.md)** — How to test guardrails

## Requirements

- Python 3.10+
- `requirements.txt`: LangChain, LangGraph, GPT4All, sentence-transformers, pytest, etc. SQLite is used via the standard library (no extra package).
