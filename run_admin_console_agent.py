"""Admin console (Agent 2): list pending requests via GET, approve/reject via PATCH.

Uses ADMIN_API_BASE_URL (default http://127.0.0.1:8000). Run the admin API first, then:
  PYTHONPATH=. python run_admin_console_agent.py
"""

import os
import sys
from pathlib import Path

if os.environ.get("PYTHONPATH"):
    for p in os.environ["PYTHONPATH"].split(os.pathsep):
        p = p.strip()
        if p and Path(p).resolve().is_dir():
            if p not in sys.path:
                sys.path.insert(0, p)
            break

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

from src.config import settings

BASE_URL = (settings.admin_api_base_url or "http://127.0.0.1:8000").rstrip("/")


def list_pending():
    r = requests.get(f"{BASE_URL}/requests", params={"status": "pending"}, timeout=10)
    r.raise_for_status()
    return r.json()


def patch_status(request_id: str, status: str):
    r = requests.patch(
        f"{BASE_URL}/requests/{request_id}",
        json={"status": status},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()


def main():
    print(f"Admin console — using API at {BASE_URL}\n")
    while True:
        try:
            pending = list_pending()
        except requests.RequestException as e:
            print(f"Cannot reach API: {e}")
            print("Is the admin API running? (python run_admin_api.py)")
            sys.exit(1)
        if not pending:
            print("No pending requests. (Press Enter to refresh, or Ctrl+C to exit.)")
            input()
            continue
        print("Pending requests:")
        for i, req in enumerate(pending, 1):
            print(f"  {i}. id={req['id']}  {req['nickname']}  dates={req['dates']}")
        print("  ---")
        choice = input("Enter number to approve/reject (or Enter to refresh, q to quit): ").strip()
        if choice.lower() == "q":
            break
        if not choice:
            continue
        try:
            idx = int(choice)
            if 1 <= idx <= len(pending):
                req = pending[idx - 1]
                rid = req["id"]
                action = input(f"  Approve (a) or Reject (r) request {rid}? ").strip().lower()
                if action == "a":
                    patch_status(rid, "approved")
                    print(f"  Approved {rid}.")
                elif action == "r":
                    patch_status(rid, "rejected")
                    print(f"  Rejected {rid}.")
                else:
                    print("  Skipped.")
            else:
                print("  Invalid number.")
        except ValueError:
            print("  Enter a number.")
        except requests.RequestException as e:
            print(f"  API error: {e}")
        print()


if __name__ == "__main__":
    main()
