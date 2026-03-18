"""Pytest configuration. Sets PYTEST_RUNNING so MCP client_fs skips atexit (avoids join blocking test exit)."""

import os


def pytest_configure(config):
    os.environ["PYTEST_RUNNING"] = "1"
