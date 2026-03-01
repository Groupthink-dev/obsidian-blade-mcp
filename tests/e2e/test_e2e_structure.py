"""E2E tests for Phase 3 link & structure operations against a real Obsidian vault."""

from __future__ import annotations

import pytest

from obsidian_blade_mcp.client import ObsidianCLI

pytestmark = pytest.mark.e2e


class TestOutline:
    """Test outline against live vault."""

    def test_outline_returns_headings(self, e2e_cli: ObsidianCLI) -> None:
        # CLAUDE.md should have at least one heading
        result = e2e_cli.outline(file="CLAUDE")
        if isinstance(result, list):
            assert len(result) > 0
            assert "heading" in result[0]
        else:
            # String fallback — should have content
            assert len(str(result).strip()) > 0


class TestLinks:
    """Test links and backlinks against live vault."""

    def test_links_for_note(self, e2e_cli: ObsidianCLI) -> None:
        # CLAUDE.md links to several agent-state files
        result = e2e_cli.links(file="CLAUDE")
        text = str(result)
        assert len(text.strip()) > 0

    def test_backlinks_for_note(self, e2e_cli: ObsidianCLI) -> None:
        # CLAUDE.md should have at least some backlinks in a large vault
        result = e2e_cli.backlinks(file="CLAUDE")
        # Even if no backlinks, the command should succeed
        assert result is not None


class TestUnresolved:
    """Test unresolved links against live vault."""

    def test_unresolved_returns_list(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.unresolved()
        if isinstance(result, list):
            # Large vault should have unresolved links
            assert len(result) > 0
        else:
            assert len(str(result).strip()) > 0


class TestOrphansDeadends:
    """Test orphans and deadends against live vault."""

    def test_orphans_total(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.orphans(total_only=True)
        count = int(str(result).strip())
        assert count > 0

    def test_deadends_total(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.deadends(total_only=True)
        count = int(str(result).strip())
        assert count > 0
