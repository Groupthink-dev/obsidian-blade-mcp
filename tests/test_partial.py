"""1.1.0: partial-result marker and package version in the MCP handshake."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from obsidian_blade_mcp import __version__
from obsidian_blade_mcp.backends import file as file_mod
from obsidian_blade_mcp.backends.file import FileBackend, note_partial, take_partial


@pytest.fixture
def vault(tmp_path):
    for i in range(5):
        (tmp_path / f"n{i}.md").write_text(f"# n{i}\nbody {i}\n")
    (tmp_path / "d1").mkdir()
    (tmp_path / "d2").mkdir()
    yield tmp_path
    take_partial()


class TestRegister:
    def test_take_clears(self):
        take_partial()
        note_partial("x")
        note_partial("x")
        assert take_partial() == ["x"]
        assert take_partial() == []


class TestBounds:
    def test_listing_bound_noted(self, vault, monkeypatch):
        monkeypatch.setattr(file_mod, "MAX_SCAN_FILES", 2)
        take_partial()
        out = FileBackend(str(vault)).files()
        assert len(out) == 2
        assert take_partial() == ["listing bound reached at 2 files"]

    def test_read_bound_noted(self, vault, monkeypatch):
        monkeypatch.setattr(file_mod, "MAX_SCAN_BYTES", 10)
        take_partial()
        FileBackend(str(vault)).search("body")
        notes = take_partial()
        assert len(notes) == 1
        assert notes[0].startswith("read bound reached at ")

    def test_folder_bound_noted(self, vault, monkeypatch):
        monkeypatch.setattr(file_mod, "MAX_SCAN_FILES", 1)
        take_partial()
        assert FileBackend(str(vault)).folders() == ["d1"]
        assert take_partial() == ["folder listing bound reached at 1 folders"]

    def test_unbounded_scan_notes_nothing(self, vault):
        take_partial()
        FileBackend(str(vault)).files()
        assert take_partial() == []


class TestServer:
    async def test_partial_line_precedes_backend_tag(self, vault, monkeypatch):
        from fastmcp import Client

        from obsidian_blade_mcp import server

        monkeypatch.setattr(file_mod, "MAX_SCAN_FILES", 2)
        env = {"OBSIDIAN_MCP_BACKEND": "file", "OBSIDIAN_VAULT_PATH": str(vault)}
        with patch.dict(os.environ, env):
            server._client = None
            try:
                async with Client(server.mcp) as c:
                    res = await c.call_tool("vault_files", {})
                    text = res.content[0].text
                    assert text.endswith("[partial: listing bound reached at 2 files]\n[backend: file]")
                    res = await c.call_tool("vault_read", {"path": "n0.md"})
                    assert res.content[0].text == "# n0\nbody 0\n[backend: file]"
            finally:
                server._client = None

    async def test_handshake_reports_package_version(self):
        from fastmcp import Client

        from obsidian_blade_mcp import server

        async with Client(server.mcp) as c:
            info = c.initialize_result.serverInfo
            assert info.name == "ObsidianBlade"
            assert info.version == __version__
