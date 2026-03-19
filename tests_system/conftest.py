"""Pytest config for system tests. Sets PYTEST_RUNNING so MCP client_fs skips atexit."""

import os


def pytest_configure(config):
    os.environ["PYTEST_RUNNING"] = "1"
