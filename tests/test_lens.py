"""Tests for lens integration — tools, connection management, formatting."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from obsidian_blade_mcp.lens import (
    format_connections,
    format_lens_results,
    heartbeat_warning,
)

# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestFormatLensResults:
    def test_empty(self):
        assert format_lens_results([], label="matches") == "No matches found."

    def test_single_result(self):
        r = MagicMock()
        r.path = "notes/test.md"
        r.title = "Test Note"
        r.score = 0.1234
        r.kind = "note"
        r.status = "on"
        r.snippet = "some matching text"

        out = format_lens_results([r], label="matches")
        assert "1 matches:" in out
        assert "notes/test.md" in out
        assert "«Test Note»" in out
        assert "score=0.1234" in out
        assert "kind=note" in out
        assert "some matching text" in out

    def test_no_snippet(self):
        r = MagicMock()
        r.path = "a.md"
        r.title = "a.md"
        r.score = 0.0
        r.kind = None
        r.status = None
        r.snippet = ""

        out = format_lens_results([r])
        assert "a.md" in out
        assert "«" not in out  # title matches path, omitted


class TestFormatConnections:
    def test_empty(self):
        assert format_connections([]) == "No connections found."

    def test_single(self):
        out = format_connections([{
            "path": "notes/linked.md",
            "raw": "linked",
            "alias": None,
            "direction": "outgoing",
            "depth": 1,
        }])
        assert "1 connections:" in out
        assert "notes/linked.md" in out
        assert "dir=outgoing" in out
        assert "depth=1" in out

    def test_with_alias(self):
        out = format_connections([{
            "path": "notes/a.md",
            "raw": "a",
            "alias": "Alpha",
            "direction": "incoming",
            "depth": 2,
        }])
        assert "alias=Alpha" in out


# ---------------------------------------------------------------------------
# Heartbeat warning tests
# ---------------------------------------------------------------------------


class TestHeartbeatWarning:
    def test_no_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        result = heartbeat_warning(conn)
        assert "missing" in result

    def test_no_row(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE heartbeat (id INTEGER PRIMARY KEY, last_beat TEXT, status TEXT)")
        result = heartbeat_warning(conn)
        assert "never run" in result

    def test_fresh_heartbeat(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE heartbeat (id INTEGER PRIMARY KEY, last_beat TEXT, status TEXT)")
        now = datetime.now(UTC).isoformat()
        conn.execute("INSERT INTO heartbeat VALUES (1, ?, 'running')", (now,))
        result = heartbeat_warning(conn)
        assert result == ""

    def test_stale_heartbeat(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE heartbeat (id INTEGER PRIMARY KEY, last_beat TEXT, status TEXT)")
        old = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
        conn.execute("INSERT INTO heartbeat VALUES (1, ?, 'running')", (old,))
        result = heartbeat_warning(conn)
        assert "stale" in result


# ---------------------------------------------------------------------------
# Tool tests
# ---------------------------------------------------------------------------


class TestVaultLensFts:
    @patch("obsidian_blade_mcp.server.heartbeat_warning", return_value="")
    @patch("obsidian_blade_mcp.server.get_lens_connection")
    async def test_fts_success(self, mock_conn, mock_hb):
        from obsidian_blade_mcp.server import vault_lens_fts

        mock_result = MagicMock()
        mock_result.path = "notes/test.md"
        mock_result.title = "Test"
        mock_result.score = -1.5
        mock_result.kind = "note"
        mock_result.status = None
        mock_result.snippet = "matching text"

        with patch("obsidian_lens.query.fts", return_value=[mock_result]):
            result = await vault_lens_fts(query="test")
            assert "notes/test.md" in result
            assert "1 matches:" in result

    @patch("obsidian_blade_mcp.server.get_lens_connection", side_effect=RuntimeError("no OBSIDIAN_VAULT_PATH"))
    async def test_fts_no_db(self, mock_conn):
        from obsidian_blade_mcp.server import vault_lens_fts

        result = await vault_lens_fts(query="test")
        assert "Error" in result
        assert "OBSIDIAN_VAULT_PATH" in result


class TestVaultLensSearch:
    @patch("obsidian_blade_mcp.server.heartbeat_warning", return_value="")
    @patch("obsidian_blade_mcp.server.get_lens_connection")
    async def test_search_success(self, mock_conn, mock_hb):
        from obsidian_blade_mcp.server import vault_lens_search

        mock_result = MagicMock()
        mock_result.path = "notes/semantic.md"
        mock_result.title = "Semantic"
        mock_result.score = 0.0321
        mock_result.kind = None
        mock_result.status = None
        mock_result.snippet = "related content"

        with patch("obsidian_lens.query.hybrid", return_value=[mock_result]):
            result = await vault_lens_search(query="container orchestration")
            assert "notes/semantic.md" in result


class TestVaultLensRelated:
    @patch("obsidian_blade_mcp.server.heartbeat_warning", return_value="")
    @patch("obsidian_blade_mcp.server.get_lens_connection")
    async def test_related_success(self, mock_conn, mock_hb):
        from obsidian_blade_mcp.server import vault_lens_related

        mock_result = MagicMock()
        mock_result.path = "notes/similar.md"
        mock_result.title = "Similar"
        mock_result.score = 0.85
        mock_result.kind = "note"
        mock_result.status = None
        mock_result.snippet = ""

        with patch("obsidian_lens.query.related", return_value=[mock_result]):
            result = await vault_lens_related(path="notes/source.md")
            assert "notes/similar.md" in result
            assert "similar notes" in result

    @patch("obsidian_blade_mcp.server.heartbeat_warning", return_value="")
    @patch("obsidian_blade_mcp.server.get_lens_connection")
    async def test_related_empty(self, mock_conn, mock_hb):
        from obsidian_blade_mcp.server import vault_lens_related

        with patch("obsidian_lens.query.related", return_value=[]):
            result = await vault_lens_related(path="notes/orphan.md")
            assert "No similar notes found" in result


class TestVaultLensConnections:
    @patch("obsidian_blade_mcp.server.heartbeat_warning", return_value="")
    @patch("obsidian_blade_mcp.server.get_lens_connection")
    async def test_connections_success(self, mock_conn, mock_hb):
        from obsidian_blade_mcp.server import vault_lens_connections

        mock_results = [
            {"path": "notes/linked.md", "raw": "linked", "alias": None, "direction": "outgoing", "depth": 1},
        ]

        with patch("obsidian_lens.query.connections", return_value=mock_results):
            result = await vault_lens_connections(path="notes/source.md")
            assert "notes/linked.md" in result
            assert "1 connections:" in result


class TestVaultLensStatus:
    @patch("obsidian_blade_mcp.server.heartbeat_warning", return_value="")
    @patch("obsidian_blade_mcp.server.get_lens_connection")
    async def test_status_success(self, mock_conn, mock_hb):
        from obsidian_blade_mcp.server import vault_lens_status

        summary = {
            "note_count": 6908,
            "link_count": 45000,
            "kind_counts": {"note": 5000, "effort": 200},
            "heartbeat": {"status": "running", "last_beat": "2026-03-14T10:00:00+00:00", "pid": 12345},
        }

        with patch("obsidian_lens.query.status_summary", return_value=summary):
            result = await vault_lens_status()
            assert "Notes: 6908" in result
            assert "Links: 45000" in result
            assert "note=5000" in result
            assert "effort=200" in result
            assert "pid=12345" in result

    @patch("obsidian_blade_mcp.server.get_lens_connection", side_effect=RuntimeError("DB not found"))
    async def test_status_no_db(self, mock_conn):
        from obsidian_blade_mcp.server import vault_lens_status

        result = await vault_lens_status()
        assert "Error" in result
        assert "DB not found" in result
