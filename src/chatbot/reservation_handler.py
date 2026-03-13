"""Reservation handling: collect date/range, check availability, escalate to admin or save to SQLite."""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

from ..db.sqlite_db import SQLiteDB


def _parse_single_date(value: str) -> Optional[str]:
    """Parse YYYY-MM-DD or MM/DD/YYYY or DD/MM/YYYY; return YYYY-MM-DD or None."""
    value = value.strip()
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_date_range(value: str) -> Optional[Tuple[str, str]]:
    """Parse 'YYYY-MM-DD - YYYY-MM-DD' or 'YYYY-MM-DD to YYYY-MM-DD'; return (start, end) or None."""
    value = value.strip()
    # Match two dates separated by " - " or " to " (with optional spaces)
    match = re.match(r"(\d{4}-\d{2}-\d{2})\s*[-–to]+\s*(\d{4}-\d{2}-\d{2})", value, re.IGNORECASE)
    if not match:
        return None
    start_s, end_s = match.group(1), match.group(2)
    start_d = _parse_single_date(start_s)
    end_d = _parse_single_date(end_s)
    if not start_d or not end_d:
        return None
    if start_d > end_d:
        return None
    return (start_d, end_d)


def _date_range_to_list(start: str, end: str) -> List[str]:
    """Return list of YYYY-MM-DD from start to end inclusive."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    out = []
    d = start_dt
    while d <= end_dt:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


class ReservationState:
    """Holds date or date range for one reservation in progress."""

    def __init__(self) -> None:
        self.date: Optional[str] = None
        self.start_date: Optional[str] = None
        self.end_date: Optional[str] = None
        self.is_complete: bool = False

    def update(self, field: str, value: str) -> bool:
        """Set field (e.g. date) from user input; return True if parsed successfully."""
        if field != "date":
            return False
        single = _parse_single_date(value)
        if single:
            self.date = single
            self.start_date = self.end_date = None
            self.is_complete = True
            return True
        rng = _parse_date_range(value)
        if rng:
            self.start_date, self.end_date = rng
            self.date = None
            self.is_complete = True
            return True
        return False

    def get_dates_to_reserve(self) -> List[str]:
        """Return list of dates to reserve (single day or range)."""
        if self.date:
            return [self.date]
        if self.start_date and self.end_date:
            return _date_range_to_list(self.start_date, self.end_date)
        return []

    def to_dict(self) -> Dict:
        """Return date/range and completion as a dict."""
        return {
            "date": self.date,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "is_complete": self.is_complete,
        }

    def reset(self) -> None:
        """Clear all fields and mark incomplete."""
        self.date = None
        self.start_date = None
        self.end_date = None
        self.is_complete = False


class ReservationHandler:
    """Orchestrates reservation flow: date/range input, availability check, DB write."""

    def __init__(self, db: Optional[SQLiteDB] = None) -> None:
        self.db = db or SQLiteDB()
        self.current_reservation: Optional[ReservationState] = None
        self.current_field_index: int = 0
        self._nickname: Optional[str] = None
        self.FIELD_ORDER = ["date"]
        self.FIELD_PROMPTS = {
            "date": "What is your preferred date or date range? (single: YYYY-MM-DD, or range: YYYY-MM-DD - YYYY-MM-DD)"
        }

    def set_nickname(self, nickname: str) -> None:
        """Set the current user's nickname for reservations."""
        self._nickname = nickname.strip() if nickname else None

    def get_nickname(self) -> Optional[str]:
        """Return the current user's nickname, or None."""
        return self._nickname

    def start_reservation(self) -> ReservationState:
        """Start a new reservation and return its state."""
        self.current_reservation = ReservationState()
        self.current_field_index = 0
        return self.current_reservation

    def get_current_field(self) -> Optional[str]:
        """Return the field we are currently collecting, or None."""
        if not self.current_reservation:
            return None
        if self.current_field_index < len(self.FIELD_ORDER):
            return self.FIELD_ORDER[self.current_field_index]
        return None

    def get_next_field_prompt(self) -> Optional[str]:
        """Return the prompt string for the next field to collect."""
        f = self.get_current_field()
        return self.FIELD_PROMPTS.get(f, f"Please provide {f}") if f else None

    def process_user_input(
        self, user_input: str
    ) -> Union[Tuple[bool, str], Tuple[bool, str, str]]:
        """Handle date/range input: validate, check availability; escalate to admin (pending request).
        Returns (success, message) or (True, "pending_approval", request_id) when waiting for admin."""
        if not self._nickname:
            return False, "Please identify yourself first (nickname is required at startup)."
        if not self.current_reservation:
            return False, "No active reservation. Say 'reserve' or 'book' to start."
        current_field = self.get_current_field()
        if not current_field:
            if self.current_reservation.is_complete:
                return True, "Reservation already complete."
            return (
                False,
                self.get_next_field_prompt()
                or "Provide date (YYYY-MM-DD) or range (YYYY-MM-DD - YYYY-MM-DD).",
            )
        value = user_input.strip()
        # Try range first (e.g. 2025-03-10 - 2025-03-15)
        if _parse_date_range(value):
            if not self.current_reservation.update("date", value):
                return False, f"Invalid date range. {self.get_next_field_prompt()}"
        else:
            # Single date: normalize if needed
            date_match = re.search(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", value)
            if date_match:
                value = date_match.group(0)
                if "/" in value:
                    parts = value.split("/")
                    if len(parts[0]) == 2:
                        value = f"{parts[2]}-{parts[0]}-{parts[1]}"
            if not self.current_reservation.update("date", value):
                return False, f"Invalid date format. {self.get_next_field_prompt()}"
        self.current_field_index += 1
        dates_to_reserve = self.current_reservation.get_dates_to_reserve()
        if not dates_to_reserve:
            self.current_reservation.reset()
            self.current_field_index = 0
            return (
                False,
                "Could not parse date or range. Use YYYY-MM-DD or YYYY-MM-DD - YYYY-MM-DD.",
            )
        # Check availability for all dates first
        no_space_dates = []
        for d in dates_to_reserve:
            free = self.db.get_free_spaces(d)
            if free is not None and free <= 0:
                no_space_dates.append(d)
        if no_space_dates:
            self.current_reservation.reset()
            self.current_field_index = 0
            return False, f"Sorry, no free spaces on: {', '.join(no_space_dates)}. Try other dates."
        # Escalate to administrator via admin API (creates pending request; admin approves in admin console)
        from ..admin_api.client import create_request

        try:
            request_id = create_request(self._nickname, dates_to_reserve)
        except Exception as e:
            return False, f"Could not send request to administrator: {e}"
        self.current_reservation = None
        return (True, "pending_approval", request_id)

    def get_current_reservation(self) -> Optional[ReservationState]:
        """Return the in-progress reservation state, or None."""
        return self.current_reservation

    def apply_approved_request(self, request_id: str) -> Tuple[bool, str]:
        """After admin approved: load request details, add reservations for each date. Return (success, message)."""
        from ..admin_api.client import get_pending_request_details

        details = get_pending_request_details(request_id)
        if not details:
            return False, "Request not found or already processed."
        nickname, dates = details
        added = 0
        for d in dates:
            if self.db.add_reservation(nickname, d):
                added += 1
        if added == len(dates):
            if len(dates) == 1:
                return True, f"Reservation saved for {dates[0]}. You're all set!"
            return (
                True,
                f"Reservations saved for {dates[0]} to {dates[-1]} ({added} days). You're all set!",
            )
        return False, "Could not save some reservations. Please try again."

    def get_active_reservations(self) -> List[str]:
        """Return list of reserved dates for the current nickname."""
        if not self._nickname:
            return []
        rows = self.db.get_reservations_by_nickname(self._nickname)
        return [r[0] for r in rows]
