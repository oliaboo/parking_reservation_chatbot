"""Client for the admin REST API (Variant 1: Agent 1 sends/polls via REST).

No DB fallback: when ADMIN_API_BASE_URL is set, all create/status calls go through
the API. If the URL is not set or the API is unreachable, we raise so the operator
must start the API and configure the URL (single path, no silent bypass).
"""

from typing import List, Literal, Optional

from src.config import settings
from src.db.sqlite_db import get_db


class AdminAPIUnavailableError(Exception):
    """Raised when the admin API is required but not configured or unreachable."""

    pass


def create_request(nickname: str, dates: List[str]) -> str:
    """Create a pending reservation request via the admin API. Returns request_id.
    Requires ADMIN_API_BASE_URL to be set and the API to be reachable; raises
    AdminAPIUnavailableError otherwise (no DB fallback).
    """
    if not settings.admin_api_base_url:
        raise AdminAPIUnavailableError(
            "ADMIN_API_BASE_URL is not set. Start the admin API (run_admin_api.py) and set it in .env for reservation requests."
        )
    import requests

    try:
        r = requests.post(
            f"{settings.admin_api_base_url}/requests",
            json={"nickname": nickname.strip(), "dates": [d.strip() for d in dates]},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["request_id"]
    except requests.RequestException as e:
        raise AdminAPIUnavailableError(
            f"Cannot reach admin API at {settings.admin_api_base_url}: {e}. Is run_admin_api.py running?"
        ) from e


def get_request_status(
    request_id: str,
) -> Optional[Literal["pending", "approved", "rejected"]]:
    """Get status of a request from the admin API. Requires ADMIN_API_BASE_URL and a reachable API."""
    if not settings.admin_api_base_url:
        raise AdminAPIUnavailableError(
            "ADMIN_API_BASE_URL is not set. Start the admin API and set it in .env."
        )
    import requests

    try:
        r = requests.get(
            f"{settings.admin_api_base_url}/requests/{request_id}",
            timeout=5,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("status")
    except requests.RequestException as e:
        raise AdminAPIUnavailableError(
            f"Cannot reach admin API at {settings.admin_api_base_url}: {e}"
        ) from e


def get_pending_request_details(
    request_id: str,
) -> Optional[tuple]:
    """Get (nickname, dates) for a request. Uses DB (API does not expose this endpoint for the client)."""
    return get_db().get_pending_request_details(request_id)
