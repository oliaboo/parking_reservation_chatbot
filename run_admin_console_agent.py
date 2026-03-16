"""Admin console (Agent 2): LangChain-based agent to interact with the administrator.

Lists pending requests via GET, approves/rejects via PATCH. Uses a LangChain chain to
interpret the administrator's input (e.g. "approve 1", "apprve 1, 2", "reject the second")
and execute the corresponding API actions.

Run the admin API first, then: PYTHONPATH=. python run_admin_console_agent.py
"""

import re
import sys
from typing import Any, Literal, Optional

import requests
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from src.config import settings

# ---- Constants ---------------------------------------------------------------

BASE_URL = settings.admin_api_base_url

ParsedActions = list[tuple[Literal["approve", "reject", "refresh", "unknown"], Optional[str]]]

ADMIN_PROMPT = """You must produce output based only on the input data below.

Input data: a single line containing one or more commands. Each command is either "approve" or "reject" followed by one or more numerical ids (e.g. 8, 10, 11). Typos and uppercase letters in the command words must be ignored (e.g. aprov, aprove, rejct = approve/reject). Multiple commands can be separated by commas.
Do not show any thinking, reasoning, argumentation, or explanation. Reply with ONLY the output line (e.g. APPROVE 12 or APPROVE 8, APPROVE 9). No code. No markdown. No other text.

Produce the output by converting each command to the format approve N or reject N. One action per command, comma-separated on one line.
Don't include any info from the examples in output.

Examples:
in: approve 10  -> out: approve 10
in: aprov 11    -> out: approve 11
in: ApRove 8, 9 -> out: approve 8, approve 9
in: rejct 12    -> out: reject 12

Input: {admin_input}
Output:"""

# ---- API (LangChain tools) ----------------------------------------------------


@tool
def list_pending_requests() -> list[dict[str, Any]]:
    """List all pending reservation requests from the admin API."""
    r = requests.get(f"{BASE_URL}/requests", params={"status": "pending"}, timeout=10)
    r.raise_for_status()
    return r.json()


@tool
def approve_request(request_id: str) -> dict[str, Any]:
    """Approve a reservation request by its id."""
    r = requests.patch(
        f"{BASE_URL}/requests/{request_id}",
        json={"status": "approved"},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()


@tool
def reject_request(request_id: str) -> dict[str, Any]:
    """Reject a reservation request by its id."""
    r = requests.patch(
        f"{BASE_URL}/requests/{request_id}",
        json={"status": "rejected"},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()


# Match APPROVE/DISCARD/REJECT plus id (one line: "APPROVE 15, DISCARD 16")
_ACTION_RE = re.compile(
    r"\b(approve|reject)\s+([a-zA-Z0-9_-]+)\b",
)


def _parse_llm_output(text: str) -> ParsedActions:
    """Extract actions from LLM output. Scans full text for APPROVE N / REJECT N so we get the right result even when the model adds code or explanation."""
    raw = (text or "").strip().lower()
    # remove trash from LLM response
    raw = raw.split("\n\n", 1)[0]
    if not raw:
        return [("unknown", None)]
    matches = _ACTION_RE.findall(raw)
    if matches:
        return list(dict.fromkeys(matches))  # unique, order preserved
    u = raw.upper()
    if re.search(r"\bREFRESH\b", u):
        return [("refresh", None)]
    if re.search(r"\bUNKNOWN\b", u):
        return [("unknown", None)]
    return [("unknown", None)]


def interpret_admin_input(
    pending: list[dict[str, Any]],
    admin_input: str,
    llm: Any,
) -> ParsedActions:
    """Interpret admin input via LLM; expect one line: APPROVE 15, DISCARD 16."""
    prompt = PromptTemplate.from_template(ADMIN_PROMPT)
    formatted = prompt.format(admin_input=admin_input)
    out = llm.invoke(formatted)
    content = out.content if hasattr(out, "content") else out
    return _parse_llm_output(str(content).strip())


# ---- Resolve & execute --------------------------------------------------------


def _log_reservation_action_to_mcp(name: str, car_number: str, reservation_period: str) -> None:
    """Append reservation log row to CSV via @modelcontextprotocol/server-filesystem (npx). Best-effort; no raise."""
    try:
        from src.mcp_reservation_logger.client_fs import log_reservation_action_via_fs_mcp

        log_reservation_action_via_fs_mcp(name, car_number, reservation_period)
    except Exception as e:
        inner = getattr(e, "exceptions", (e,))
        msg = inner[0] if inner else e
        print(f"  (MCP logger unreachable: {msg})")


def _apply_action(
    action: Literal["approve", "reject"],
    request_id: str,
    pending: list[dict[str, Any]],
) -> Optional[str]:
    """Call API for one action. Returns None on success, or error message."""
    try:
        if action == "approve":
            approve_request.invoke({"request_id": request_id})
        else:
            reject_request.invoke({"request_id": request_id})
        if action == "approve":
            req = next((r for r in pending if str(r["id"]) == str(request_id)), None)
            if req:
                from src.db.sqlite_db import get_db

                name = req.get("nickname", "")
                car_number = get_db().get_plates_by_nickname(name) or ""
                reservation_period = ", ".join(req.get("dates") or [])
                _log_reservation_action_to_mcp(name, car_number, reservation_period)
        return None
    except requests.RequestException as e:
        resp = getattr(e, "response", None)
        if resp is not None and resp.status_code == 409:
            return f"Request {request_id} is already approved or rejected."
        return f"API error for {request_id}: {e}"


def execute_actions(pending: list[dict[str, Any]], actions: ParsedActions) -> None:
    """Resolve each action to a request id and call the API; print outcome."""
    for action, raw_id in actions:
        if action not in ("approve", "reject") or not raw_id:
            continue
        msg = _apply_action(action, raw_id, pending)
        if msg:
            print(f"  {msg}")
        else:
            label = "Approved" if action == "approve" else "Rejected"
            print(f"  {label} {raw_id}.")


# ---- Main loop ----------------------------------------------------------------


def _fetch_pending() -> list[dict[str, Any]]:
    """Fetch pending requests; exit on connection error."""
    try:
        return list_pending_requests.invoke({})
    except requests.RequestException as e:
        print(f"Cannot reach API: {e}")
        print("Is the admin API running? (python run_admin_api.py)")
        sys.exit(1)


def _display_pending(pending: list[dict[str, Any]]) -> None:
    """Print current pending list and usage hint."""
    print("Pending requests:")
    for req in pending:
        print(f" request_id={req['id']}  user={req['nickname']}  dates={req['dates']}")
    print("  ---")
    print(
        "Examples: approve 1 | approve 1, 2 | reject 2 | refresh | q to quit\n          Note that the number reflects request_id"
    )


def main() -> None:
    from src.chatbot.llm_setup import LLMProvider

    print(f"Admin console (LangChain) — API at {BASE_URL}\n")
    llm_instance = LLMProvider(temperature=0.0).get_llm()

    while True:
        pending = _fetch_pending()

        if not pending:
            print("No pending requests. (Press Enter to refresh, or q to quit.)")
            if input().strip().lower() == "q":
                break
            continue

        _display_pending(pending)
        choice = input("You: ").strip()

        if choice.lower() == "q":
            break
        if not choice:
            continue

        actions = interpret_admin_input(pending, choice, llm_instance)

        if actions and actions[0][0] == "refresh":
            continue
        if actions and actions[0][0] == "unknown":
            print("  Unclear command. Try: approve 1, 2 | reject 2 | refresh | q to quit.")
            continue

        execute_actions(pending, actions)
        print()


if __name__ == "__main__":
    main()
