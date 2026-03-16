"""Tests for MCP reservation logging via @modelcontextprotocol/server-filesystem (client_fs)."""

import csv
import io

from src.mcp_reservation_logger.client_fs import (
    LOG_FILENAME,
    RESERVATIONS_MCP_DIR,
    log_reservation_action_via_fs_mcp,
)


def test_make_csv_header():
    """CSV header is name,car_number,reservation_period,approval_time."""
    from src.mcp_reservation_logger.client_fs import _make_csv_header

    assert _make_csv_header() == "name,car_number,reservation_period,approval_time\n"


def test_append_line_to_content():
    """_append_line_to_content appends a valid CSV row with approval_time as UTC ISO."""
    from src.mcp_reservation_logger.client_fs import _append_line_to_content

    existing = "name,car_number,reservation_period,approval_time\n"
    out = _append_line_to_content(existing, "alice", "AB-123", "2025-03-10, 2025-03-11")
    lines = out.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "name,car_number,reservation_period,approval_time"
    row = list(csv.reader(io.StringIO(lines[1])))[0]
    assert row[0] == "alice"
    assert row[1] == "AB-123"
    assert row[2] == "2025-03-10, 2025-03-11"
    assert len(row) == 4 and "T" in row[3]  # approval_time ISO


def test_client_fs_module_exports():
    """client_fs exposes log_reservation_action_via_fs_mcp and constants."""
    assert callable(log_reservation_action_via_fs_mcp)
    assert LOG_FILENAME == "reservations_log.csv"
    assert "reservations_mcp" in str(RESERVATIONS_MCP_DIR)
