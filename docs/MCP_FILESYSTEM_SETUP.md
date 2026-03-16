# Using the Open-Source MCP Filesystem Server

The admin console can log each approve/reject to `reservations_mcp/reservations_log.csv` using the **official open-source MCP server** [@modelcontextprotocol/server-filesystem](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem) (Node.js). No custom MCP server process needs to run.

---

## How it works

- The admin console starts the filesystem MCP server **once per run** (on the first approve/reject), via `npx`, and reuses the same connection for all later logs. For each approve/reject it calls:
  - **read_text_file** to read the current CSV (or start with a header line),
  - **write_file** to write the file back with one new row: `action`, `request_id`, `time` (UTC ISO).
- The server is allowed to access **only** the `reservations_mcp` directory (scoped to your project). The log file is `reservations_mcp/reservations_log.csv`. The npx process is closed when the admin console exits.

---

## Prerequisites

1. **Node.js** (and **npx**) installed. Check:
   ```bash
   node -v
   npx -v
   ```
   The filesystem server does not support `--help`; it expects directory paths. It will be run automatically by the admin console when you approve/reject.
2. **Python** with the project dependencies installed (`pip install -r requirements.txt`).

---

## Usage

No configuration or separate process is required. Run the admin console as usual:

```bash
export PYTHONPATH=/path/to/parking_reservation_chatbot
python run_admin_console_agent.py
```

When you approve or reject a request, a row is appended to `reservations_mcp/reservations_log.csv` via the filesystem MCP server.

---

## CSV format

`reservations_mcp/reservations_log.csv` has three columns:

| action   | request_id | time (UTC ISO)        |
|----------|------------|------------------------|
| approved | 15         | 2025-03-10T12:34:56Z   |
| rejected | 8          | 2025-03-10T12:35:01Z   |

---

## Troubleshooting

- **"MCP logger unreachable"**  
  Ensure Node.js and npx are installed and that `reservations_mcp` is writable (the app creates it if missing).

- **npx not found**  
  Install Node.js (e.g. from [nodejs.org](https://nodejs.org)) so that `npx` is on your PATH.

- **Permission denied**  
  Ensure the project directory (and `reservations_mcp`) are writable by the user running the admin console.
