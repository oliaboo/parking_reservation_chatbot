"""Tests for MCP reservation logging via @modelcontextprotocol/server-filesystem (client_fs)."""

import csv
import io

import pytest

from src.mcp_reservation_logger.client_fs import (
    LOG_FILENAME,
    RESERVATIONS_MCP_DIR,
    log_reservation_action_via_fs_mcp,
)


def test_make_csv_header():
    """CSV header is action,request_id,time."""
    from src.mcp_reservation_logger.client_fs import _make_csv_header

    assert _make_csv_header() == "action,request_id,time\n"


def test_append_line_to_content():
    """_append_line_to_content appends a valid CSV row with UTC time."""
    from src.mcp_reservation_logger.client_fs import _append_line_to_content

    existing = "action,request_id,time\n"
    out = _append_line_to_content(existing, "approved", "15")
    lines = out.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "action,request_id,time"
    row = list(csv.reader(io.StringIO(lines[1])))[0]
    assert row[0] == "approved"
    assert row[1] == "15"
    assert len(row) == 3 and "T" in row[2]  # ISO time


def test_client_fs_module_exports():
    """client_fs exposes log_reservation_action_via_fs_mcp and constants."""
    assert callable(log_reservation_action_via_fs_mcp)
    assert LOG_FILENAME == "reservations_log.csv"
    assert "reservations_mcp" in str(RESERVATIONS_MCP_DIR)
