"""E2E test fixtures — require a running Obsidian instance."""

from __future__ import annotations

import pytest

from obsidian_blade_mcp.client import ObsidianCLI


@pytest.fixture
def live_cli():
    """Create an ObsidianCLI instance targeting the real Obsidian app."""
    return ObsidianCLI()
