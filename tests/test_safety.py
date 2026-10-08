"""Phase C safety gates: read-only default (C1), confirm (C2), content hashes (C3), HTTP policy (C4)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

from obsidian_blade_mcp import server
from obsidian_blade_mcp.auth import check_http_policy, is_loopback
from obsidian_blade_mcp.backend import writes_enabled
from obsidian_blade_mcp.backends.file import FileBackend
from obsidian_blade_mcp.client import ObsidianConflictError, content_hash_of


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "Alpha.md").write_text("---\nstatus: draft\n---\n# Alpha\n\n- [ ] task\n")
    (tmp_path / "notes" / "Beta.md").write_text("See [[Alpha]] and [[notes/Alpha]].\n")
    return tmp_path


@pytest.fixture
def file_env(vault):
    env = {"OBSIDIAN_MCP_BACKEND": "file", "OBSIDIAN_VAULT_PATH": str(vault)}
    with patch.dict(os.environ, env):
        os.environ.pop("OBSIDIAN_MCP_WRITES", None)
        server._client = None
        server.apply_write_policy()
        try:
            yield vault
        finally:
            server._client = None
            os.environ.pop("OBSIDIAN_MCP_WRITES", None)
            server.apply_write_policy()


def _enable_writes() -> None:
    os.environ["OBSIDIAN_MCP_WRITES"] = "1"
    server.apply_write_policy()


# ---------------------------------------------------------------------------
# C1 read-only default
# ---------------------------------------------------------------------------


class TestWritePolicy:
    def test_env_parsing(self):
        for value, expected in [("", False), ("0", False), ("no", False), ("1", True), ("true", True), ("YES", True)]:
            with patch.dict(os.environ, {"OBSIDIAN_MCP_WRITES": value}):
                assert writes_enabled() is expected

    async def test_read_only_hides_write_tools(self, file_env):
        async with Client(server.mcp) as c:
            tools = {t.name for t in await c.list_tools()}
        assert len(tools) == 28
        assert not (tools & server.WRITE_TOOLS)
        assert "vault_read" in tools

    async def test_read_only_refuses_calls(self, file_env):
        async with Client(server.mcp) as c:
            with pytest.raises(Exception, match="Unknown tool"):
                await c.call_tool("vault_append", {"path": "notes/Alpha.md", "content": "x"})
        assert "x" not in (file_env / "notes" / "Alpha.md").read_text()

    async def test_writes_env_registers_tools(self, file_env):
        _enable_writes()
        async with Client(server.mcp) as c:
            tools = {t.name for t in await c.list_tools()}
        assert len(tools) == 40
        assert server.WRITE_TOOLS <= tools

    async def test_write_tools_all_tagged(self, file_env):
        _enable_writes()
        tools = await server.mcp.list_tools()
        tagged = {t.name for t in tools if server.WRITE_TAG in t.tags}
        assert tagged == server.WRITE_TOOLS


# ---------------------------------------------------------------------------
# C2 confirm on delete / rename / move
# ---------------------------------------------------------------------------


class TestConfirm:
    async def test_delete_dry_run_names_path(self, file_env):
        _enable_writes()
        async with Client(server.mcp) as c:
            res = await c.call_tool("vault_delete", {"path": "notes/Alpha.md"})
        text = res.content[0].text
        assert text.startswith("Dry run: delete not applied")
        assert "source: notes/Alpha.md" in text
        assert "destination: .trash/Alpha.md" in text
        assert (file_env / "notes" / "Alpha.md").exists()

    async def test_delete_permanent_dry_run(self, file_env):
        _enable_writes()
        async with Client(server.mcp) as c:
            res = await c.call_tool("vault_delete", {"path": "notes/Alpha.md", "permanent": True})
        assert "permanent (unrecoverable)" in res.content[0].text

    async def test_rename_dry_run_counts_links(self, file_env):
        _enable_writes()
        async with Client(server.mcp) as c:
            res = await c.call_tool("vault_rename", {"path": "notes/Alpha.md", "new_name": "Gamma"})
        text = res.content[0].text
        assert "source: notes/Alpha.md" in text
        assert "destination: notes/Gamma.md" in text
        assert "target_exists: False" in text
        assert "notes_with_links_to_rewrite: 1" in text
        assert (file_env / "notes" / "Alpha.md").exists()
        assert "[[Alpha]]" in (file_env / "notes" / "Beta.md").read_text()

    async def test_move_dry_run_then_confirm(self, file_env):
        _enable_writes()
        async with Client(server.mcp) as c:
            res = await c.call_tool("vault_move", {"path": "notes/Alpha.md", "destination": "archive"})
            assert "destination: archive/Alpha.md" in res.content[0].text
            assert (file_env / "notes" / "Alpha.md").exists()
            res = await c.call_tool("vault_move", {"path": "notes/Alpha.md", "destination": "archive", "confirm": True})
        assert res.content[0].text.startswith("Moved: notes/Alpha.md")
        assert (file_env / "archive" / "Alpha.md").exists()
        assert "[[archive/Alpha]]" in (file_env / "notes" / "Beta.md").read_text()

    async def test_cli_backend_plan(self):
        from obsidian_blade_mcp.server import vault_rename

        client = MagicMock()
        client.mutation_plan.return_value = {"op": "rename", "source": "a.md", "destination": "b.md (same folder)"}
        with patch("obsidian_blade_mcp.server._get_client", return_value=client):
            text = await vault_rename(path="a.md", new_name="b")
        assert "Dry run: rename not applied" in text
        assert "destination: b.md (same folder)" in text
        client.rename.assert_not_called()


# ---------------------------------------------------------------------------
# C3 content-hash preconditions
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_file_info_reports_hash(self, vault):
        b = FileBackend(str(vault))
        info = b.file_info(path="notes/Alpha.md")
        assert info["hash"] == content_hash_of((vault / "notes" / "Alpha.md").read_text())
        assert info["hash"].startswith("sha256:")
        assert b.content_hash(path="notes/Alpha.md") == info["hash"]

    async def test_matching_hash_allows_write(self, file_env):
        _enable_writes()
        async with Client(server.mcp) as c:
            info = await c.call_tool("vault_file_info", {"path": "notes/Alpha.md"})
            line = next(ln for ln in info.content[0].text.splitlines() if ln.startswith("hash:"))
            h = line.split(":", 1)[1].strip()
            res = await c.call_tool("vault_append", {"path": "notes/Alpha.md", "content": "more", "if_hash": h})
        assert res.content[0].text.startswith("Appended to")
        assert "more" in (file_env / "notes" / "Alpha.md").read_text()

    async def test_stale_hash_is_conflict(self, file_env):
        _enable_writes()
        b = FileBackend(str(file_env))
        stale = b.content_hash(path="notes/Alpha.md")
        (file_env / "notes" / "Alpha.md").write_text("changed elsewhere\n")
        fresh = b.content_hash(path="notes/Alpha.md")
        async with Client(server.mcp) as c:
            res = await c.call_tool("vault_append", {"path": "notes/Alpha.md", "content": "more", "if_hash": stale})
        text = res.content[0].text
        assert text.startswith("Error: conflict: notes/Alpha.md changed")
        assert stale in text and fresh in text
        assert "more" not in (file_env / "notes" / "Alpha.md").read_text()

    async def test_hash_without_prefix_accepted(self, file_env):
        _enable_writes()
        b = FileBackend(str(file_env))
        h = b.content_hash(path="notes/Alpha.md").removeprefix("sha256:")
        async with Client(server.mcp) as c:
            res = await c.call_tool(
                "vault_property_set", {"path": "notes/Alpha.md", "name": "status", "value": "done", "if_hash": h}
            )
        assert res.content[0].text.startswith("Set status")

    @pytest.mark.parametrize(
        "tool,args",
        [
            ("vault_prepend", {"path": "notes/Alpha.md", "content": "top"}),
            ("vault_property_remove", {"path": "notes/Alpha.md", "name": "status"}),
            ("vault_section_replace", {"path": "notes/Alpha.md", "heading": "Alpha", "content": "body"}),
            ("vault_task_update", {"ref": "notes/Alpha.md:5", "action": "complete"}),
            ("vault_delete", {"path": "notes/Alpha.md", "confirm": True}),
            ("vault_rename", {"path": "notes/Alpha.md", "new_name": "Z", "confirm": True}),
            ("vault_move", {"path": "notes/Alpha.md", "destination": "x", "confirm": True}),
        ],
    )
    async def test_every_guarded_tool_refuses_stale_hash(self, file_env, tool, args):
        _enable_writes()
        before = (file_env / "notes" / "Alpha.md").read_text()
        async with Client(server.mcp) as c:
            res = await c.call_tool(tool, {**args, "if_hash": "sha256:" + "0" * 64})
        assert res.content[0].text.startswith("Error: conflict:")
        assert (file_env / "notes" / "Alpha.md").read_text() == before

    def test_conflict_error_fields(self):
        e = ObsidianConflictError("a.md", "sha256:1", "sha256:2")
        assert e.path == "a.md" and e.expected == "sha256:1" and e.actual == "sha256:2"

    def test_cli_backend_hash_reads_through_cli(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result(stdout="# Hi\n")
        assert cli.content_hash(path="Hi.md") == content_hash_of("# Hi\n")
        args = mock_subprocess.call_args[0][0]
        assert args[-2:] == ["read", "path=Hi.md"]


# ---------------------------------------------------------------------------
# C4 HTTP policy
# ---------------------------------------------------------------------------


class TestHttpPolicy:
    def test_loopback_hosts(self):
        assert is_loopback("127.0.0.1") and is_loopback("localhost") and is_loopback("::1")
        assert not is_loopback("0.0.0.0") and not is_loopback("192.168.1.5")

    def test_loopback_read_only_without_token_ok(self):
        assert check_http_policy("127.0.0.1", None, writes=False) is None

    def test_non_loopback_needs_token(self):
        reason = check_http_policy("0.0.0.0", None, writes=False)
        assert reason and "not loopback" in reason
        assert check_http_policy("0.0.0.0", "secret", writes=False) is None

    def test_writes_over_http_need_token_even_on_loopback(self):
        reason = check_http_policy("127.0.0.1", None, writes=True)
        assert reason and "Writes over HTTP" in reason
        assert check_http_policy("127.0.0.1", "secret", writes=True) is None

    def test_main_refuses_bad_http_bind(self):
        env = {"OBSIDIAN_MCP_API_TOKEN": "", "OBSIDIAN_MCP_WRITES": "1"}
        with (
            patch.dict(os.environ, env),
            patch.object(server, "TRANSPORT", "http"),
            patch.object(server, "HTTP_HOST", "127.0.0.1"),
            patch("obsidian_blade_mcp.auth._BEARER_CHECKED", False),
            patch("obsidian_blade_mcp.auth._BEARER_TOKEN", None),
            patch.object(server.mcp, "run") as run,
        ):
            with pytest.raises(SystemExit) as exc:
                server.main()
            assert exc.value.code == 2
            run.assert_not_called()
        server.apply_write_policy()
