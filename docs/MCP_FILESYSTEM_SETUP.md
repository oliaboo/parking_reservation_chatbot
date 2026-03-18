# Using the Open-Source MCP Filesystem Server

The **chatbot** (in its LangGraph **record_data** node) logs each **approval** to `reservations_mcp/reservations_log.csv` (rejections are not logged) using the **official open-source MCP server** [@modelcontextprotocol/server-filesystem](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem) (Node.js). When the chatbot sees that the administrator approved a request (after polling), it writes reservations to the DB and then appends one row to the CSV via MCP. No custom MCP server process needs to run.

---

## How it works

- The **chatbot process** starts the filesystem MCP server **once per run** (on the first approval it processes), via `npx`, and reuses the same connection for all later logs. **Only approvals are logged.** In the **record_data** node the chatbot calls:
  - **read_text_file** to read the current CSV (or start with a header line),
  - **write_file** to write the file back with one new row: **name** (nickname), **car_number** (plates from users table), **reservation_period** (request dates), **approval_time** (UTC ISO).
- The server is allowed to access **only** the `reservations_mcp` directory (scoped to your project). The log file is `reservations_mcp/reservations_log.csv`. The npx process is closed when the chatbot process exits.

---

## Prerequisites

1. **Node.js** (and **npx**) installed. Check:
   ```bash
   node -v
   npx -v
   ```
   The filesystem server does not support `--help`; it expects directory paths. It will be run automatically by the chatbot when it records an approval (record_data node).
2. **Python** with the project dependencies installed (`pip install -r requirements.txt`).

---

## Usage

No configuration or separate process is required. Run the **chatbot** (and admin API + admin console for human-in-the-loop). When an administrator **approves** a request in the admin console, the chatbot (after polling) runs its **record_data** node and appends a row to `reservations_mcp/reservations_log.csv` via the filesystem MCP server. Rejections are not logged. **Node.js/npx** must be available in the environment where the **chatbot** runs.

---

## CSV format

`reservations_mcp/reservations_log.csv` has four columns:

| name  | car_number | reservation_period       | approval_time (UTC ISO)  |
|-------|-------------|---------------------------|--------------------------|
| alice | ABC-1234      | 2026-04-10, 2026-04-11    | 2026-03-10T12:34:56Z     |
| bob   | XYZ-9978       | 2026-04-15                | 2026-03-10T12:35:01Z     |

---

## Troubleshooting

- **"MCP logger unreachable"**  
  Ensure Node.js and npx are installed and that `reservations_mcp` is writable (the app creates it if missing).

- **npx not found**  
  Install Node.js (e.g. from [nodejs.org](https://nodejs.org)) so that `npx` is on your PATH.

- **Permission denied**  
  Ensure the project directory (and `reservations_mcp`) are writable by the user running the admin console.
