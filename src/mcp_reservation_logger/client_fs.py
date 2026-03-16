"""Use the open-source MCP filesystem server to append reservation actions to CSV.

Requires Node.js and npx. Spawns @modelcontextprotocol/server-filesystem once per
admin console run; reuses the same session for every approve/reject (read_text_file +
write_file). Process is started on first log and closed on stop_mcp_fs_logger() or exit.
"""

import asyncio
import atexit
import csv
import io
import queue
import threading
from datetime import datetime, timezone

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.config import PROJECT_ROOT

RESERVATIONS_MCP_DIR = PROJECT_ROOT / "reservations_mcp"
LOG_FILENAME = "reservations_log.csv"
LOG_PATH = RESERVATIONS_MCP_DIR / LOG_FILENAME

# One process/session per admin console run
_request_queue: queue.Queue = queue.Queue()
_result_queue: queue.Queue = queue.Queue()
_session_ready: threading.Event = threading.Event()
_worker_thread: threading.Thread | None = None
_loop: asyncio.AbstractEventLoop | None = None
_SENTINEL = object()


def _make_csv_header() -> str:
    return "name,car_number,reservation_period,approval_time\n"


def _append_line_to_content(
    existing: str, name: str, car_number: str, reservation_period: str
) -> str:
    """Return existing content + one new CSV row. Approval time is UTC ISO."""
    approval_time = datetime.now(timezone.utc).isoformat()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([name, car_number, reservation_period, approval_time])
    return existing.rstrip() + "\n" + buf.getvalue().strip() + "\n"


async def _run_one_log(
    session: ClientSession,
    name: str,
    car_number: str,
    reservation_period: str,
) -> None:
    """Read CSV, append one row, write back. Uses existing session."""
    file_path = str(LOG_PATH.resolve())
    try:
        result = await session.call_tool(
            "read_text_file",
            arguments={"path": file_path},
        )
    except Exception:
        result = None
    if result and not getattr(result, "isError", True) and result.content:
        text = getattr(result.content[0], "text", "") or ""
        existing = text
    else:
        existing = _make_csv_header()

    new_content = _append_line_to_content(existing, name, car_number, reservation_period)

    write_result = await session.call_tool(
        "write_file",
        arguments={"path": file_path, "content": new_content},
    )
    if getattr(write_result, "isError", False):
        raise RuntimeError(
            " ".join(c.text for c in write_result.content if hasattr(c, "text"))
            or "write_file failed"
        )


async def _mcp_worker_loop() -> None:
    """Run one long-lived MCP session; process (action, request_id) from queue until sentinel."""
    global _session_ready
    RESERVATIONS_MCP_DIR.mkdir(parents=True, exist_ok=True)
    path_arg = str(RESERVATIONS_MCP_DIR.resolve())
    params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", path_arg],
    )
    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                _session_ready.set()

                loop = asyncio.get_event_loop()
                while True:
                    item = await loop.run_in_executor(None, _request_queue.get)
                    if item is _SENTINEL:
                        break
                    name, car_number, reservation_period = item
                    try:
                        await _run_one_log(session, name, car_number, reservation_period)
                        _result_queue.put((True, None))
                    except Exception as e:
                        _result_queue.put((False, e))
    except Exception as e:
        _session_ready.set()
        _result_queue.put((False, e))
    finally:
        _session_ready.set()


def _thread_target() -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_mcp_worker_loop())
    finally:
        _loop.close()


def _ensure_worker_started() -> None:
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _session_ready.clear()
    _worker_thread = threading.Thread(target=_thread_target, daemon=True)
    _worker_thread.start()
    if not _session_ready.wait(timeout=30):
        raise RuntimeError("MCP filesystem server failed to start within 30s")


def stop_mcp_fs_logger() -> None:
    """Close the MCP session and worker thread. Safe to call multiple times."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        return
    try:
        _request_queue.put(_SENTINEL)
        _worker_thread.join(timeout=5)
    except Exception:
        pass
    _worker_thread = None


def log_reservation_action_via_fs_mcp(name: str, car_number: str, reservation_period: str) -> None:
    """Append one reservation log row to CSV (name, car_number, reservation_period, approval_time). Starts the MCP process on first call; reuses it after that. Raises on error."""
    _ensure_worker_started()
    _request_queue.put((name, car_number, reservation_period))
    ok, err = _result_queue.get(timeout=15)
    if not ok and err is not None:
        raise err


# When the process exits, close the MCP session so the npx subprocess does not linger
atexit.register(stop_mcp_fs_logger)
