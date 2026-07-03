"""Pytest defaults that keep test memories out of the real Dhee vault."""

from __future__ import annotations

import os
import tempfile


def pytest_configure(config):
    if os.environ.get("DHEE_TEST_LIVE_DATA") and os.environ.get("DHEE_TEST_ALLOW_LIVE_FIXTURES"):
        return
    temp_home = tempfile.mkdtemp(prefix="dhee-pytest-home-")
    os.environ["HOME"] = temp_home
    os.environ["DHEE_DATA_DIR"] = os.path.join(temp_home, ".dhee")
    os.environ["DHEE_PYTEST_ISOLATED_DATA_DIR"] = "1"
