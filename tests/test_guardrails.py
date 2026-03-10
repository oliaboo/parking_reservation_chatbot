"""Tests for guardrails: sensitive data is blocked in queries."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.guardrails.guard_rails import GuardRails


@pytest.fixture
def guard_rails():
    return GuardRails(enabled=True, threshold=0.7)


def test_blocks_ssn_in_query(guard_rails):
    """Query containing SSN pattern should be blocked."""
    is_safe, msg = guard_rails.validate_query("What are prices? My SSN is 123-45-6789")
    assert is_safe is False
    assert "sensitive" in (msg or "").lower()


def test_blocks_credit_card_in_query(guard_rails):
    """Query containing credit card pattern should be blocked."""
    is_safe, msg = guard_rails.validate_query("Charge 4532-1234-5678-9012 for parking")
    assert is_safe is False
    assert "sensitive" in (msg or "").lower()


def test_blocks_email_in_query(guard_rails):
    """Query containing email should be blocked."""
    is_safe, msg = guard_rails.validate_query("Send receipt to user@example.com")
    assert is_safe is False
    assert "sensitive" in (msg or "").lower()


def test_blocks_phone_in_query(guard_rails):
    """Query containing US phone pattern should be blocked."""
    is_safe, msg = guard_rails.validate_query("Call me at 555-123-4567")
    assert is_safe is False
    assert "sensitive" in (msg or "").lower()


def test_allows_safe_query(guard_rails):
    """Normal question without sensitive data should pass."""
    is_safe, msg = guard_rails.validate_query("How many parking spaces do you have?")
    assert is_safe is True
    assert msg is None


def test_reservation_allows_date_only(guard_rails):
    """During reservation, date-only input should pass (allow_reservation_data=True)."""
    is_safe, msg = guard_rails.validate_query("2025-03-15", allow_reservation_data=True)
    assert is_safe is True


def test_reservation_blocks_ssn_even_when_allowed(guard_rails):
    """During reservation, SSN should still be blocked."""
    is_safe, msg = guard_rails.validate_query("123-45-6789", allow_reservation_data=True)
    assert is_safe is False
