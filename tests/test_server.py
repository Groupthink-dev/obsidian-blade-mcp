"""Tests for the MCP server tool functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestVaultInfo:
    """Test vault_info tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_vault_info_success(self, mock_get_client, sample_vault_info):
        from obsidian_blade_mcp.server import vault_info

        mock_client = MagicMock()
        mock_client.vault_info.return_value = sample_vault_info
        mock_get_client.return_value = mock_client

        result = await vault_info()
        assert "test-vault" in result
        assert "1234" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_vault_info_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianNotRunningError
        from obsidian_blade_mcp.server import vault_info

        mock_client = MagicMock()
        mock_client.vault_info.side_effect = ObsidianNotRunningError("Obsidian is not running")
        mock_get_client.return_value = mock_client

        result = await vault_info()
        assert "Error" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_vault_info_unexpected_error(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_info

        mock_client = MagicMock()
        mock_client.vault_info.side_effect = RuntimeError("something broke")
        mock_get_client.return_value = mock_client

        result = await vault_info()
        assert "Error" in result
        assert "something broke" in result


class TestVaultRead:
    """Test vault_read tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_read_by_file(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_read

        mock_client = MagicMock()
        mock_client.read.return_value = "# Hello\nWorld"
        mock_get_client.return_value = mock_client

        result = await vault_read(file="Hello")
        assert "Hello" in result
        assert "World" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_read_by_path(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_read

        mock_client = MagicMock()
        mock_client.read.return_value = "Content"
        mock_get_client.return_value = mock_client

        result = await vault_read(path="folder/note.md")
        assert "Content" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_read_truncates_long_content(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_read

        mock_client = MagicMock()
        mock_client.read.return_value = "\n".join(f"Line {i}" for i in range(200))
        mock_get_client.return_value = mock_client

        result = await vault_read(file="Long")
        assert "more lines" in result


class TestVaultCreate:
    """Test vault_create tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_create_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_create

        mock_client = MagicMock()
        mock_client.create.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_create(name="New Note", content="# Hello")
        assert "Created" in result
        assert "New Note" in result


class TestVaultAppend:
    """Test vault_append tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_append_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_append

        mock_client = MagicMock()
        mock_client.append.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_append(content="New paragraph", file="My Note")
        assert "Appended" in result


class TestVaultFiles:
    """Test vault_files tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_files_list(self, mock_get_client, sample_files):
        from obsidian_blade_mcp.server import vault_files

        mock_client = MagicMock()
        mock_client.files.return_value = sample_files
        mock_get_client.return_value = mock_client

        result = await vault_files(limit=20)
        assert "Note A.md" in result
        assert "Note B.md" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_files_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_files

        mock_client = MagicMock()
        mock_client.files.return_value = []
        mock_get_client.return_value = mock_client

        result = await vault_files()
        assert "No files" in result


class TestVaultFolders:
    """Test vault_folders tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_folders_list(self, mock_get_client, sample_folders):
        from obsidian_blade_mcp.server import vault_folders

        mock_client = MagicMock()
        mock_client.folders.return_value = sample_folders
        mock_get_client.return_value = mock_client

        result = await vault_folders()
        assert "atlas/" in result
        assert "spaces/" in result


class TestVaultProperties:
    """Test property tools."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_properties_list(self, mock_get_client, sample_properties):
        from obsidian_blade_mcp.server import vault_properties

        mock_client = MagicMock()
        mock_client.properties.return_value = sample_properties
        mock_get_client.return_value = mock_client

        result = await vault_properties(file="Test")
        assert "kind: effort" in result
        assert "status: on" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_property_read(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_property_read

        mock_client = MagicMock()
        mock_client.property_read.return_value = {"value": "on"}
        mock_get_client.return_value = mock_client

        result = await vault_property_read(name="status", file="Test")
        assert "status" in result
        assert "on" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_property_set(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_property_set

        mock_client = MagicMock()
        mock_client.property_set.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_property_set(name="status", value="done", file="Test")
        assert "Set" in result
        assert "status" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_property_remove(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_property_remove

        mock_client = MagicMock()
        mock_client.property_remove.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_property_remove(name="old_field", file="Test")
        assert "Removed" in result
