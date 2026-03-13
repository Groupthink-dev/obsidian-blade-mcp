"""Tests for vault_section_read and vault_section_replace — heading-scoped operations."""

from __future__ import annotations

import os
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from obsidian_blade_mcp.client import ObsidianCLI, ObsidianCLIError, ObsidianFileNotFoundError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault_dir(tmp_path):
    """Create a temporary vault with test notes."""
    note = tmp_path / "notes" / "test.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        textwrap.dedent("""\
        ---
        kind: note
        ---

        # Top Heading

        Top-level content here.

        ## Section A

        Content under A.
        More A content.

        ### Sub-section A1

        Sub content under A1.

        ## Section B

        Content under B.

        # Second Top Heading

        Content under second top.
        """)
    )

    empty_section = tmp_path / "notes" / "empty.md"
    empty_section.write_text(
        textwrap.dedent("""\
        # Note

        ## Empty Section

        ## Next Section

        content here.
        """)
    )

    eof_note = tmp_path / "notes" / "eof.md"
    eof_note.write_text(
        textwrap.dedent("""\
        # Top

        intro.

        ## Last Section

        content at eof.
        no following heading.
        """)
    )

    duplicate_headings = tmp_path / "notes" / "dupe.md"
    duplicate_headings.write_text(
        textwrap.dedent("""\
        ## Section A

        first occurrence.

        ## Section A

        second occurrence.
        """)
    )

    return tmp_path


@pytest.fixture
def cli(vault_dir):
    """CLI instance pointing at tmp vault."""
    with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
        return ObsidianCLI(cli_path="/usr/bin/obsidian", vault_name="test")


# ---------------------------------------------------------------------------
# _parse_heading unit tests
# ---------------------------------------------------------------------------


class TestParseHeading:
    """Test _parse_heading static method."""

    def test_h1(self):
        assert ObsidianCLI._parse_heading("# Title\n") == (1, "Title")

    def test_h2(self):
        assert ObsidianCLI._parse_heading("## My Section\n") == (2, "My Section")

    def test_h3(self):
        assert ObsidianCLI._parse_heading("### Sub\n") == (3, "Sub")

    def test_h6(self):
        assert ObsidianCLI._parse_heading("###### Deep\n") == (6, "Deep")

    def test_heading_no_trailing_newline(self):
        assert ObsidianCLI._parse_heading("## Title") == (2, "Title")

    def test_heading_with_extra_spaces_in_text(self):
        # Strips leading/trailing spaces from text portion
        assert ObsidianCLI._parse_heading("## Title  \n") == (2, "Title")

    def test_non_heading_regular_text(self):
        assert ObsidianCLI._parse_heading("Regular text\n") is None

    def test_non_heading_no_space_after_hash(self):
        # Must have space after hashes
        assert ObsidianCLI._parse_heading("##NoSpace\n") is None

    def test_non_heading_empty_line(self):
        assert ObsidianCLI._parse_heading("\n") is None

    def test_non_heading_just_hashes(self):
        assert ObsidianCLI._parse_heading("###\n") is None

    def test_non_heading_bold(self):
        assert ObsidianCLI._parse_heading("**bold**\n") is None


# ---------------------------------------------------------------------------
# section_read tests
# ---------------------------------------------------------------------------


class TestSectionRead:
    """Test ObsidianCLI.section_read."""

    def test_read_h2_section(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/test.md", heading="Section A")
        assert "Content under A." in result
        assert "More A content." in result

    def test_section_does_not_include_heading_line(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/test.md", heading="Section A")
        assert "## Section A" not in result

    def test_section_stops_at_sibling_heading(self, cli, vault_dir):
        """Section A should not include Section B content."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/test.md", heading="Section A")
        assert "Content under B." not in result
        assert "## Section B" not in result

    def test_section_includes_nested_headings(self, cli, vault_dir):
        """Section A's body includes the Sub-section A1 heading and its content."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/test.md", heading="Section A")
        assert "Sub-section A1" in result
        assert "Sub content under A1." in result

    def test_read_section_at_eof(self, cli, vault_dir):
        """Section ending at EOF (no following heading)."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/eof.md", heading="Last Section")
        assert "content at eof." in result
        assert "no following heading." in result

    def test_empty_section(self, cli, vault_dir):
        """Heading immediately followed by sibling — empty section."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/empty.md", heading="Empty Section")
        assert result == ""

    def test_heading_not_found_raises(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            with pytest.raises(ObsidianCLIError, match="not found"):
                cli.section_read(path="notes/test.md", heading="Nonexistent Heading")

    def test_file_not_found_raises(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            with pytest.raises(ObsidianFileNotFoundError):
                cli.section_read(path="notes/missing.md", heading="Any")

    def test_duplicate_heading_returns_first(self, cli, vault_dir):
        """When heading appears twice, first occurrence wins."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/dupe.md", heading="Section A")
        assert "first occurrence." in result
        assert "second occurrence." not in result

    def test_h1_section_stops_at_sibling_h1(self, cli, vault_dir):
        """H1 section boundary is next H1."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_read(path="notes/test.md", heading="Top Heading")
        assert "Top-level content here." in result
        assert "Content under second top." not in result


# ---------------------------------------------------------------------------
# section_replace tests
# ---------------------------------------------------------------------------


class TestSectionReplace:
    """Test ObsidianCLI.section_replace."""

    def test_replace_h2_section(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli.section_replace(path="notes/test.md", heading="Section B", content="\nNew B content.\n")
            result = cli.section_read(path="notes/test.md", heading="Section B")
        assert "New B content." in result
        assert "Content under B." not in result

    def test_replace_preserves_other_sections(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli.section_replace(path="notes/test.md", heading="Section B", content="\nReplaced.\n")
            result = cli.section_read(path="notes/test.md", heading="Section A")
        # Section A should be untouched
        assert "Content under A." in result

    def test_replace_preserves_sibling_after(self, cli, vault_dir):
        """Content after the section is intact after replace."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli.section_replace(path="notes/test.md", heading="Section A", content="\nNew A.\n")
            result = cli.section_read(path="notes/test.md", heading="Section B")
        assert "Content under B." in result

    def test_replace_section_at_eof(self, cli, vault_dir):
        """Replace a section that runs to EOF."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli.section_replace(path="notes/eof.md", heading="Last Section", content="\nNew EOF content.\n")
            result = cli.section_read(path="notes/eof.md", heading="Last Section")
        assert "New EOF content." in result
        assert "content at eof." not in result

    def test_replace_empty_section(self, cli, vault_dir):
        """Replace an empty section (no body)."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli.section_replace(path="notes/empty.md", heading="Empty Section", content="\nNow has content.\n")
            result = cli.section_read(path="notes/empty.md", heading="Empty Section")
        assert "Now has content." in result

    def test_replace_with_empty_content(self, cli, vault_dir):
        """Replacing with empty content clears the section body."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli.section_replace(path="notes/test.md", heading="Section B", content="")
            result = cli.section_read(path="notes/test.md", heading="Section B")
        assert result == ""

    def test_replace_adds_trailing_newline(self, cli, vault_dir):
        """Content without trailing newline gets one appended."""
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            cli.section_replace(path="notes/test.md", heading="Section B", content="\nNo trailing newline")
            # Next heading should still be parseable — file integrity check
            result_b = cli.section_read(path="notes/test.md", heading="Section B")
            result_top2 = cli.section_read(path="notes/test.md", heading="Second Top Heading")
        assert "No trailing newline" in result_b
        assert "Content under second top." in result_top2

    def test_replace_returns_confirmation(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = cli.section_replace(path="notes/test.md", heading="Section B", content="\nX.\n")
        assert "Section B" in result
        assert "replaced" in result.lower()

    def test_replace_heading_not_found_raises(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            with pytest.raises(ObsidianCLIError, match="not found"):
                cli.section_replace(path="notes/test.md", heading="Ghost Heading", content="x")

    def test_replace_file_not_found_raises(self, cli, vault_dir):
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            with pytest.raises(ObsidianFileNotFoundError):
                cli.section_replace(path="notes/missing.md", heading="Any", content="x")


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------


class TestVaultSectionReadTool:
    """Test vault_section_read MCP tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_read

        mock_client = MagicMock()
        mock_client.section_read.return_value = "\nSome content.\n"
        mock_get_client.return_value = mock_client

        result = await vault_section_read(path="notes/note.md", heading="My Section")
        assert "Some content." in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_empty_section_returns_placeholder(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_read

        mock_client = MagicMock()
        mock_client.section_read.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_section_read(path="notes/note.md", heading="Empty")
        assert "empty section" in result.lower() or "Empty" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_heading_not_found_returns_error(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_read

        mock_client = MagicMock()
        mock_client.section_read.side_effect = ObsidianCLIError("Heading 'X' not found in notes/note.md")
        mock_get_client.return_value = mock_client

        result = await vault_section_read(path="notes/note.md", heading="X")
        assert "Error" in result
        assert "not found" in result.lower()

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_file_not_found_returns_error(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_read

        mock_client = MagicMock()
        mock_client.section_read.side_effect = ObsidianFileNotFoundError("File not found: notes/missing.md")
        mock_get_client.return_value = mock_client

        result = await vault_section_read(path="notes/missing.md", heading="Any")
        assert "Error" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_unexpected_error(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_read

        mock_client = MagicMock()
        mock_client.section_read.side_effect = RuntimeError("disk full")
        mock_get_client.return_value = mock_client

        result = await vault_section_read(path="notes/note.md", heading="X")
        assert "Error" in result
        assert "disk full" in result


class TestVaultSectionReplaceTool:
    """Test vault_section_replace MCP tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_replace

        mock_client = MagicMock()
        mock_client.section_replace.return_value = "Section 'My Section' replaced in notes/note.md"
        mock_get_client.return_value = mock_client

        result = await vault_section_replace(path="notes/note.md", heading="My Section", content="\nNew content.\n")
        assert "replaced" in result.lower()
        assert "My Section" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_heading_not_found_returns_error(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_replace

        mock_client = MagicMock()
        mock_client.section_replace.side_effect = ObsidianCLIError("Heading 'X' not found in notes/note.md")
        mock_get_client.return_value = mock_client

        result = await vault_section_replace(path="notes/note.md", heading="X", content="y")
        assert "Error" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_unexpected_error(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_section_replace

        mock_client = MagicMock()
        mock_client.section_replace.side_effect = RuntimeError("permission denied")
        mock_get_client.return_value = mock_client

        result = await vault_section_replace(path="notes/note.md", heading="X", content="y")
        assert "Error" in result
        assert "permission denied" in result
