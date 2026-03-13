# Parking Reservation Chatbot — Documentation

This folder contains technical documentation for the parking reservation chatbot: data flow, code structure, and testing.

## Contents

| Document | Description |
|----------|-------------|
| [DATA_FLOW.md](DATA_FLOW.md) | End-to-end data flow: startup, chat loop, intent routing, RAG, reservations, and database usage. |
| [CODE_STRUCTURE.md](CODE_STRUCTURE.md) | Project layout, modules, and how each component is used. |
| [TESTING_GUARDRAILS.md](TESTING_GUARDRAILS.md) | How to test guardrails manually and automatically. |
| [EVALUATION.md](EVALUATION.md) | RAG evaluation: Recall@K, Precision@K, retrieval latency, FAISS metric (cosine vs L2), and how to run it. |

## Quick overview

- **Entry point:** `run_chatbot_agent.py` — sets up path, loads config, asks for nickname, initializes the system, runs the chat loop.
- **Chat logic:** `src/chatbot/chatbot.py` — LangGraph workflow: single node `handle_general_query` runs every turn; it uses the LLM to classify intent (reserve / show_reservations / general) and then calls the reservation handler, show-reservations handler, or RAG to answer.
- **Answers:** General questions use **RAG** (vector store from `parking_info.txt` + SQLite prices/hours) and a local LLM (GPT4All).
- **Reservations:** Date or date range → check availability in SQLite → insert into `reservations` table.
- **Safety:** Guardrails block or redact SSN, credit card, email, phone in user input and bot responses.
