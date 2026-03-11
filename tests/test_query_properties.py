"""Tests for vault_query_properties — direct filesystem frontmatter queries."""

from __future__ import annotations

import os
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from obsidian_blade_mcp.client import ObsidianCLI, ObsidianVaultError


@pytest.fixture
def vault_dir(tmp_path):
    """Create a temporary vault with effort notes for testing."""
    # Create effort notes with various statuses
    spaces = tmp_path / "spaces" / "Systems" / "Areas" / "AI" / "efforts"
    spaces.mkdir(parents=True)

    (spaces / "Digital Assistant.md").write_text(
        textwrap.dedent("""\
        ---
        kind: effort
        status: on
        rank: 8
        space: spaces/Systems
        area: Augmented Intelligence
        ---

        # Digital Assistant

        Body content that should not be read.
    """)
    )

    (spaces / "Infrastructure.md").write_text(
        textwrap.dedent("""\
        ---
        kind: effort
        status: on
        rank: 6
        space: spaces/Systems
        area: Information Infrastructure
        ---

        # Infrastructure
    """)
    )

    (spaces / "Archived Project.md").write_text(
        textwrap.dedent("""\
        ---
        kind: effort
        status: done
        rank: 3
        ---

        # Archived
    """)
    )

    (spaces / "Ongoing Work.md").write_text(
        textwrap.dedent("""\
        ---
        kind: effort
        status: ongoing
        rank: 5
        ---

        # Ongoing
    """)
    )

    # Note without frontmatter
    (spaces / "README.md").write_text("# Just a readme\n")

    # Note with broken frontmatter
    (spaces / "Broken.md").write_text("---\nunclosed frontmatter\n")

    # Non-md file
    (spaces / "data.json").write_text('{"key": "value"}')

    # Note in a different folder
    atlas = tmp_path / "atlas" / "cards"
    atlas.mkdir(parents=True)
    (atlas / "Docker.md").write_text(
        textwrap.dedent("""\
        ---
        kind: card
        status: on
        ---

        # Docker
    """)
    )

    return tmp_path


@pytest.fixture
def cli(vault_dir):
    """Create CLI instance with vault path env var."""
    with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
        return ObsidianCLI(cli_path="/usr/bin/obsidian", vault_name="test-vault")


class TestResolveVaultPath:
    """Test _resolve_vault_path resolution."""

    def test_from_env_var(self, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli = ObsidianCLI(cli_path="/usr/bin/obsidian")
            assert cli._resolve_vault_path() == str(vault_dir)

    def test_env_var_nonexistent_dir(self):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": "/nonexistent/path"}):
            cli = ObsidianCLI(cli_path="/usr/bin/obsidian")
            # Should fall through to CLI fallback, which will fail
            with pytest.raises(ObsidianVaultError):
                cli._resolve_vault_path()

    def test_no_env_var_no_obsidian(self):
        with patch.dict(os.environ, {}, clear=True):
            cli = ObsidianCLI(cli_path="/usr/bin/obsidian")
            with pytest.raises(ObsidianVaultError):
                cli._resolve_vault_path()


class TestParseFrontmatter:
    """Test _parse_frontmatter static method."""

    def test_valid_frontmatter(self, vault_dir):
        fm = ObsidianCLI._parse_frontmatter(
            str(vault_dir / "spaces" / "Systems" / "Areas" / "AI" / "efforts" / "Digital Assistant.md")
        )
        assert fm is not None
        assert fm["kind"] == "effort"
        assert fm["status"] == "on"
        assert fm["rank"] == 8

    def test_no_frontmatter(self, vault_dir):
        fm = ObsidianCLI._parse_frontmatter(
            str(vault_dir / "spaces" / "Systems" / "Areas" / "AI" / "efforts" / "README.md")
        )
        assert fm is None

    def test_unclosed_frontmatter(self, vault_dir):
        fm = ObsidianCLI._parse_frontmatter(
            str(vault_dir / "spaces" / "Systems" / "Areas" / "AI" / "efforts" / "Broken.md")
        )
        assert fm is None

    def test_nonexistent_file(self):
        fm = ObsidianCLI._parse_frontmatter("/nonexistent/file.md")
        assert fm is None


class TestQueryProperties:
    """Test query_properties method."""

    def test_filter_status_on(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on")
        # Should find Digital Assistant (rank 8), Infrastructure (rank 6), Docker (rank 0/none)
        assert len(results) >= 2
        # Sorted by rank descending
        ranks = [r["properties"].get("rank", 0) for r in results]
        assert ranks == sorted(ranks, reverse=True)

    def test_filter_with_path_restriction(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on", path="spaces/")
        # Should find only notes under spaces/, not atlas/
        paths = [r["file"] for r in results]
        for p in paths:
            assert p.startswith("spaces/")

    def test_field_filtering(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on", path="spaces/", fields="kind,rank")
        for r in results:
            props = r["properties"]
            # Should only contain requested fields (that exist in the note)
            assert all(k in ("kind", "rank") for k in props.keys())

    def test_substring_match(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on")
        statuses = [r["properties"].get("status") for r in results]
        # Should match "on" and "ongoing" (substring match)
        assert any(s == "on" for s in statuses)
        assert any(s == "ongoing" for s in statuses)

    def test_case_insensitive(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="ON")
        assert len(results) >= 2

    def test_limit(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on", limit=1)
        assert len(results) == 1

    def test_no_matches(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="nonexistent")
        assert results == []

    def test_nonexistent_path(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on", path="nonexistent/")
        assert results == []

    def test_nonexistent_property(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="nonexistent", value="anything")
        assert results == []

    def test_rank_sorting(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on", path="spaces/", fields="kind,status,rank")
        ranks = [r["properties"].get("rank", 0) or 0 for r in results]
        assert ranks == sorted(ranks, reverse=True)

    def test_done_status_included_in_on_query(self, cli, vault_dir):
        """'done' contains 'on' as substring, so it matches."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="on", path="spaces/")
        statuses = {r["properties"].get("status") for r in results}
        # Substring match: "done" contains "on", so it's included
        assert "done" in statuses
        assert "on" in statuses
        assert "ongoing" in statuses

    def test_exact_done_query(self, cli, vault_dir):
        """Querying for 'done' specifically gets only done status."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            results = cli.query_properties(property="status", value="done", path="spaces/")
        statuses = {r["properties"].get("status") for r in results}
        assert "done" in statuses
        assert "on" not in statuses


class TestVaultQueryPropertiesTool:
    """Test the MCP tool wrapper."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tool_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_query_properties

        mock_client = MagicMock()
        mock_client.query_properties.return_value = [
            {"file": "spaces/effort1.md", "properties": {"kind": "effort", "status": "on", "rank": 8}},
            {"file": "spaces/effort2.md", "properties": {"kind": "effort", "status": "on", "rank": 6}},
        ]
        mock_get_client.return_value = mock_client

        result = await vault_query_properties(property="status", value="on", path="spaces/")
        assert "effort1.md" in result
        assert "effort2.md" in result
        assert "rank=8" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tool_no_results(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_query_properties

        mock_client = MagicMock()
        mock_client.query_properties.return_value = []
        mock_get_client.return_value = mock_client

        result = await vault_query_properties(property="status", value="nonexistent")
        assert "No matching" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tool_error(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_query_properties

        mock_client = MagicMock()
        mock_client.query_properties.side_effect = ObsidianVaultError("Cannot resolve vault path")
        mock_get_client.return_value = mock_client

        result = await vault_query_properties(property="status", value="on")
        assert "Error" in result
