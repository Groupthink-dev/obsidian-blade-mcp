"""Shared fixtures for Obsidian Blade MCP tests."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from obsidian_blade_mcp.client import ObsidianCLI


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.run for all tests that need it."""
    with patch("obsidian_blade_mcp.client.subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def mock_which():
    """Patch shutil.which to always find the CLI."""
    with patch("obsidian_blade_mcp.client.shutil.which", return_value="/usr/local/bin/obsidian"):
        yield


@pytest.fixture
def cli(mock_which):
    """Create an ObsidianCLI instance with a mocked binary path."""
    return ObsidianCLI(vault_name="test-vault", cli_path="/usr/local/bin/obsidian")


@pytest.fixture
def successful_result():
    """Factory for creating successful subprocess results."""

    def _make(stdout: str = "", stderr: str = "") -> MagicMock:
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = stdout
        result.stderr = stderr
        return result

    return _make


@pytest.fixture
def failed_result():
    """Factory for creating failed subprocess results."""

    def _make(returncode: int = 1, stdout: str = "", stderr: str = "Error") -> MagicMock:
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    return _make


@pytest.fixture
def sample_vault_info() -> dict[str, Any]:
    """Sample vault info JSON response."""
    return {
        "name": "test-vault",
        "path": "/Users/test/test-vault",
        "fileCount": 1234,
        "noteCount": 890,
    }


@pytest.fixture
def sample_files() -> list[dict[str, Any]]:
    """Sample file listing response."""
    return [
        {"path": "notes/Note A.md", "size": 2345, "modified": "2026-03-01T10:00:00"},
        {"path": "notes/Note B.md", "size": 1234, "modified": "2026-02-28T14:00:00"},
        {"path": "atlas/cards/Concept.md", "size": 567, "modified": "2026-02-27T09:00:00"},
    ]


@pytest.fixture
def sample_properties() -> dict[str, Any]:
    """Sample frontmatter properties."""
    return {
        "kind": "effort",
        "status": "on",
        "rank": 8,
        "tags": ["#IT/software", "#PKM/workflow"],
        "created": "2026-02-24T12:00:00+11:00",
        "publish": False,
        "llm_generated": True,
    }


@pytest.fixture
def sample_folders() -> list[str]:
    """Sample folder listing."""
    return [
        "+/",
        "+/ingest/",
        "atlas/",
        "atlas/cards/",
        "atlas/maps/",
        "calendar/",
        "spaces/",
        "spaces/Systems/",
    ]


@pytest.fixture
def sample_search_results() -> list[str]:
    """Sample search result paths (JSON array from CLI)."""
    return [
        "atlas/cards/Docker.md",
        "spaces/Systems/Areas/Information Infrastructure/efforts/Declarative Infrastructure.md",
        "+/ingest/raw-capture.md",
    ]


@pytest.fixture
def sample_search_context() -> str:
    """Sample search:context output (text format)."""
    return (
        "atlas/cards/Docker.md:5: Docker is a containerization platform\n"
        "atlas/cards/Docker.md:12: Use Docker for reproducible builds\n"
        "spaces/Systems/note.md:3: Docker compose configuration\n"
    )


@pytest.fixture
def sample_tags() -> list[dict[str, str]]:
    """Sample tags listing (JSON from CLI)."""
    return [
        {"tag": "#IT/software/Docker", "count": "15"},
        {"tag": "#IT/networking/Tailscale", "count": "8"},
        {"tag": "#PKM/workflow", "count": "42"},
        {"tag": "#on/health", "count": "7"},
    ]


@pytest.fixture
def sample_bases() -> str:
    """Sample bases listing (newline-delimited paths from CLI)."""
    return (
        "spaces/Systems/Areas/Knowledge Management/efforts/Digital Assistant/Digital Assistant - jobs.base\n"
        "spaces/Systems/Areas/Knowledge Management/efforts/Digital Assistant/Agentic MVP Roadmap.base\n"
    )
