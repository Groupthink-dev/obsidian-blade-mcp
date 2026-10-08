"""Tests for backend selection and the running-app probe."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from obsidian_blade_mcp import backend
from obsidian_blade_mcp.backends.file import FileBackend
from obsidian_blade_mcp.client import ObsidianCLI, ObsidianCLIError


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "a.md").write_text("# a")
    return tmp_path


class TestProbe:
    @patch("obsidian_blade_mcp.backend.subprocess.run")
    @patch("obsidian_blade_mcp.backend.shutil.which", return_value="/usr/bin/pgrep")
    @patch("obsidian_blade_mcp.backend.platform.system", return_value="Darwin")
    def test_running(self, _sys, _which, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="2430\n")
        assert backend.obsidian_is_running() is True
        assert mock_run.call_args[0][0] == ["pgrep", "-x", "Obsidian"]

    @patch("obsidian_blade_mcp.backend.subprocess.run")
    @patch("obsidian_blade_mcp.backend.shutil.which", return_value="/usr/bin/pgrep")
    @patch("obsidian_blade_mcp.backend.platform.system", return_value="Linux")
    def test_not_running(self, _sys, _which, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert backend.obsidian_is_running() is False

    @patch("obsidian_blade_mcp.backend.subprocess.run", side_effect=OSError)
    @patch("obsidian_blade_mcp.backend.shutil.which", return_value="/usr/bin/pgrep")
    def test_probe_failure_is_false(self, _which, _run):
        assert backend.obsidian_is_running() is False

    @patch("obsidian_blade_mcp.backend.platform.system", return_value="Windows")
    def test_unknown_platform_is_false(self, _sys):
        assert backend.obsidian_is_running() is False


class TestSelect:
    def test_auto_prefers_cli_when_running(self, vault):
        with (
            patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_MCP_BACKEND": "auto"}),
            patch("obsidian_blade_mcp.backend.obsidian_is_running", return_value=True),
            patch("obsidian_blade_mcp.backend.cli_is_installed", return_value=True),
            patch("obsidian_blade_mcp.client.shutil.which", return_value="/usr/local/bin/obsidian"),
        ):
            assert isinstance(backend.select_backend(), ObsidianCLI)

    def test_auto_falls_back_to_file_without_launching(self, vault):
        with (
            patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault)}, clear=False),
            patch("obsidian_blade_mcp.backend.obsidian_is_running", return_value=False),
            patch("obsidian_blade_mcp.backend.cli_is_installed", return_value=True),
            patch("obsidian_blade_mcp.client.subprocess.run") as cli_run,
        ):
            os.environ.pop("OBSIDIAN_MCP_BACKEND", None)
            b = backend.select_backend()
            assert isinstance(b, FileBackend)
            assert b.name == "file"
            cli_run.assert_not_called()

    def test_auto_cli_installed_but_app_closed_still_file(self, vault):
        with (
            patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault)}),
            patch("obsidian_blade_mcp.backend.obsidian_is_running", return_value=False),
            patch("obsidian_blade_mcp.backend.cli_is_installed", return_value=True),
        ):
            os.environ.pop("OBSIDIAN_MCP_BACKEND", None)
            assert isinstance(backend.select_backend(), FileBackend)

    def test_auto_nothing_available(self):
        with (
            patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": ""}),
            patch("obsidian_blade_mcp.backend.obsidian_is_running", return_value=False),
        ):
            os.environ.pop("OBSIDIAN_MCP_BACKEND", None)
            with pytest.raises(ObsidianCLIError, match="No backend available"):
                backend.select_backend()

    def test_forced_file_needs_path(self):
        with patch.dict(os.environ, {"OBSIDIAN_MCP_BACKEND": "file", "OBSIDIAN_VAULT_PATH": "/nonexistent"}):
            with pytest.raises(ObsidianCLIError, match="OBSIDIAN_VAULT_PATH"):
                backend.select_backend()

    def test_forced_file(self, vault):
        with patch.dict(os.environ, {"OBSIDIAN_MCP_BACKEND": "file", "OBSIDIAN_VAULT_PATH": str(vault)}):
            assert isinstance(backend.select_backend(), FileBackend)

    def test_forced_cli(self):
        with (
            patch.dict(os.environ, {"OBSIDIAN_MCP_BACKEND": "cli"}),
            patch("obsidian_blade_mcp.client.shutil.which", return_value="/usr/local/bin/obsidian"),
        ):
            b = backend.select_backend()
            assert isinstance(b, ObsidianCLI)
            assert b.name == "cli"

    def test_unknown_mode(self):
        with patch.dict(os.environ, {"OBSIDIAN_MCP_BACKEND": "magic"}):
            with pytest.raises(ObsidianCLIError, match="Unknown"):
                backend.select_backend()


class TestServerIntegration:
    """Through the FastMCP in-memory client so middleware runs."""

    async def test_backend_tag_and_new_tools(self, vault):
        from fastmcp import Client

        from obsidian_blade_mcp import server

        (vault / ".obsidian").mkdir()
        (vault / ".obsidian" / "templates.json").write_text('{"folder": "tpl"}')
        (vault / "tpl").mkdir()
        (vault / "tpl" / "t.md").write_text("tpl body")
        with patch.dict(os.environ, {"OBSIDIAN_MCP_BACKEND": "file", "OBSIDIAN_VAULT_PATH": str(vault)}):
            server._client = None
            try:
                async with Client(server.mcp) as c:
                    tools = {t.name for t in await c.list_tools()}
                    assert {"vault_daily_read", "vault_daily_append", "vault_template_read"} <= tools
                    assert len(tools) == 40
                    res = await c.call_tool("vault_read", {"path": "a.md"})
                    assert res.content[0].text == "# a\n[backend: file]"
                    res = await c.call_tool("vault_template_read", {"name": "t"})
                    assert res.content[0].text == "tpl body\n[backend: file]"
                    res = await c.call_tool("vault_base_query", {"path": "x.base"})
                    assert res.content[0].text.startswith("Error: backend_unsupported")
            finally:
                server._client = None

    async def test_tag_absent_before_selection(self):
        from obsidian_blade_mcp import server

        server._client = None
        assert server._backend_name() is None
