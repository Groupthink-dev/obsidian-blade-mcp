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


class TestVaultSearch:
    """Test vault_search tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_search_success(self, mock_get_client, sample_search_results):
        from obsidian_blade_mcp.server import vault_search

        mock_client = MagicMock()
        mock_client.search.return_value = sample_search_results
        mock_get_client.return_value = mock_client

        result = await vault_search(query="Docker")
        assert "Docker.md" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_search_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_search

        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_get_client.return_value = mock_client

        result = await vault_search(query="nonexistent")
        assert "No results" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_search_with_limit(self, mock_get_client, sample_search_results):
        from obsidian_blade_mcp.server import vault_search

        mock_client = MagicMock()
        mock_client.search.return_value = sample_search_results
        mock_get_client.return_value = mock_client

        result = await vault_search(query="test", limit=1)
        assert "2 more" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_search_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianNotRunningError
        from obsidian_blade_mcp.server import vault_search

        mock_client = MagicMock()
        mock_client.search.side_effect = ObsidianNotRunningError("not running")
        mock_get_client.return_value = mock_client

        result = await vault_search(query="test")
        assert "Error" in result


class TestVaultSearchContext:
    """Test vault_search_context tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_search_context_success(self, mock_get_client, sample_search_context):
        from obsidian_blade_mcp.server import vault_search_context

        mock_client = MagicMock()
        mock_client.search_context.return_value = sample_search_context
        mock_get_client.return_value = mock_client

        result = await vault_search_context(query="Docker")
        assert "Docker.md:5:" in result
        assert "Docker is a containerization" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_search_context_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_search_context

        mock_client = MagicMock()
        mock_client.search_context.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_search_context(query="nonexistent")
        assert "No results" in result


class TestVaultTags:
    """Test vault_tags tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tags_success(self, mock_get_client, sample_tags):
        from obsidian_blade_mcp.server import vault_tags

        mock_client = MagicMock()
        mock_client.tags.return_value = sample_tags
        mock_get_client.return_value = mock_client

        result = await vault_tags()
        assert "#IT/software/Docker (15)" in result
        assert "#PKM/workflow (42)" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tags_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_tags

        mock_client = MagicMock()
        mock_client.tags.return_value = []
        mock_get_client.return_value = mock_client

        result = await vault_tags()
        assert "No tags" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tags_with_limit(self, mock_get_client, sample_tags):
        from obsidian_blade_mcp.server import vault_tags

        mock_client = MagicMock()
        mock_client.tags.return_value = sample_tags
        mock_get_client.return_value = mock_client

        result = await vault_tags(limit=2)
        assert "2 more tags" in result


class TestVaultTag:
    """Test vault_tag tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tag_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_tag

        mock_client = MagicMock()
        mock_client.tag.return_value = "atlas/cards/Docker.md\nspaces/note.md"
        mock_get_client.return_value = mock_client

        result = await vault_tag(name="#IT/software")
        assert "Docker.md" in result


class TestVaultBases:
    """Test vault_bases tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_bases_success(self, mock_get_client, sample_bases):
        from obsidian_blade_mcp.server import vault_bases

        mock_client = MagicMock()
        mock_client.bases.return_value = sample_bases
        mock_get_client.return_value = mock_client

        result = await vault_bases()
        assert "jobs.base" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_bases_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_bases

        mock_client = MagicMock()
        mock_client.bases.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_bases()
        assert "No files" in result


class TestVaultBaseQuery:
    """Test vault_base_query tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_base_query_json(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_base_query

        mock_client = MagicMock()
        mock_client.base_query.return_value = [{"name": "Task 1", "status": "done"}]
        mock_get_client.return_value = mock_client

        result = await vault_base_query(path="file.base")
        assert "Task 1" in result
        assert "done" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_base_query_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_base_query

        mock_client = MagicMock()
        mock_client.base_query.return_value = []
        mock_get_client.return_value = mock_client

        result = await vault_base_query(path="file.base")
        assert "No data" in result
