"""E2E tests for Phase 2 search/tags/bases operations against a real Obsidian vault."""

from __future__ import annotations

import pytest

from obsidian_blade_mcp.client import ObsidianCLI

pytestmark = pytest.mark.e2e


class TestSearch:
    """Test search against live vault."""

    def test_search_returns_results(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.search(query="vault")
        # Should find at least one note mentioning "vault"
        if isinstance(result, list):
            assert len(result) > 0
        else:
            assert len(str(result).strip()) > 0

    def test_search_context_returns_lines(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.search_context(query="vault")
        assert isinstance(result, str)
        assert len(result.strip()) > 0


class TestTags:
    """Test tags against live vault."""

    def test_tags_returns_list(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.tags()
        if isinstance(result, list):
            assert len(result) > 0
        else:
            assert len(str(result).strip()) > 0


class TestBaseQuery:
    """Test base query against live vault."""

    def test_bases_returns_list(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.bases()
        # Vault should have at least one .base file
        if isinstance(result, list):
            assert len(result) > 0
        elif isinstance(result, str):
            assert ".base" in result or len(result.strip()) > 0
