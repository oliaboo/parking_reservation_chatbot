# Parking Reservation Chatbot — Documentation

Technical documentation: data flow, code structure, human-in-the-loop design, testing, and evaluation.

## Contents

| Document | Description |
|----------|-------------|
| [SYSTEM_SUMMARY.md](SYSTEM_SUMMARY.md) | What the system does, user interaction, data storages, RAG, guardrails, evaluation. |
| [DESIGN_HUMAN_IN_THE_LOOP.md](DESIGN_HUMAN_IN_THE_LOOP.md) | Reservation escalation: admin API, admin console (LLM-interpreted commands), polling; includes [screenshots](DESIGN_HUMAN_IN_THE_LOOP.md#screenshots). |
| [DATA_FLOW.md](DATA_FLOW.md) | Startup, chat loop, intent routing, RAG, reservations, escalation and polling. |
| [CODE_STRUCTURE.md](CODE_STRUCTURE.md) | Project layout, modules, admin API and console. |
| [TESTING_GUARDRAILS.md](TESTING_GUARDRAILS.md) | Testing guardrails manually and automatically. |
| [EVALUATION.md](EVALUATION.md) | RAG evaluation: Recall@K, Precision@K, retrieval latency, FAISS metric. |

## Quick overview

- **Chatbot:** `run_chatbot_agent.py` — nickname, then chat (RAG for info, reserve, show reservations). Reservations are sent to the admin API and wait for approval.
- **Admin API:** `run_admin_api.py` — REST API for creating and updating reservation requests (POST/GET/PATCH).
- **Admin console:** `run_admin_console_agent.py` — lists pending requests, interprets lines like `approve 15` / `reject 8` via an LLM, PATCHes the API.
- **Chat logic:** `src/chatbot/chatbot.py` — LangGraph single node; intent (reserve / show_reservations / general) → reservation handler, show-reservations, or RAG. Reservation flow: create request via API, poll until approved/rejected, then write to `reservations` on approve.
- **RAG:** Vector store (`parking_info.txt`) + SQLite prices/hours; top-k retrieval (default k=3); no conversation history in the prompt. Guardrails block or redact sensitive data.
