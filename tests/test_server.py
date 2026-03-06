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
    async def test_read_returns_full_content(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_read

        mock_client = MagicMock()
        long_content = "\n".join(f"Line {i}" for i in range(200))
        mock_client.read.return_value = long_content
        mock_get_client.return_value = mock_client

        result = await vault_read(file="Long")
        assert result == long_content


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


# ===========================================================================
# Phase 3 — Link & Structure Tools
# ===========================================================================


class TestVaultOutline:
    """Test vault_outline tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_outline_success(self, mock_get_client, sample_outline):
        from obsidian_blade_mcp.server import vault_outline

        mock_client = MagicMock()
        mock_client.outline.return_value = sample_outline
        mock_get_client.return_value = mock_client

        result = await vault_outline(file="My Note")
        assert "# My Note" in result
        assert "## Introduction" in result
        assert "### Sub-detail" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_outline_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianFileNotFoundError
        from obsidian_blade_mcp.server import vault_outline

        mock_client = MagicMock()
        mock_client.outline.side_effect = ObsidianFileNotFoundError("not found")
        mock_get_client.return_value = mock_client

        result = await vault_outline(file="Missing")
        assert "Error" in result


class TestVaultLinks:
    """Test vault_links tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_links_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_links

        mock_client = MagicMock()
        mock_client.links.return_value = "Target A\nTarget B\nTarget C"
        mock_get_client.return_value = mock_client

        result = await vault_links(file="My Note")
        assert "Target A" in result
        assert "Target B" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_links_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_links

        mock_client = MagicMock()
        mock_client.links.return_value = "No links found."
        mock_get_client.return_value = mock_client

        result = await vault_links(file="Isolated")
        assert "No links found." in result


class TestVaultBacklinks:
    """Test vault_backlinks tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_backlinks_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_backlinks

        mock_client = MagicMock()
        mock_client.backlinks.return_value = "Source A\nSource B"
        mock_get_client.return_value = mock_client

        result = await vault_backlinks(file="My Note")
        assert "Source A" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_backlinks_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_backlinks

        mock_client = MagicMock()
        mock_client.backlinks.return_value = "No backlinks found."
        mock_get_client.return_value = mock_client

        result = await vault_backlinks(file="Orphan")
        assert "No backlinks found." in result


class TestVaultAliases:
    """Test vault_aliases tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_aliases_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_aliases

        mock_client = MagicMock()
        mock_client.aliases.return_value = "Alias One\nAlias Two"
        mock_get_client.return_value = mock_client

        result = await vault_aliases(file="My Note")
        assert "Alias One" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_aliases_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_aliases

        mock_client = MagicMock()
        mock_client.aliases.return_value = "No aliases found."
        mock_get_client.return_value = mock_client

        result = await vault_aliases(file="No Aliases")
        assert "No aliases found." in result


class TestVaultUnresolved:
    """Test vault_unresolved tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_unresolved_success(self, mock_get_client, sample_unresolved):
        from obsidian_blade_mcp.server import vault_unresolved

        mock_client = MagicMock()
        mock_client.unresolved.return_value = sample_unresolved
        mock_get_client.return_value = mock_client

        result = await vault_unresolved(limit=2)
        assert "Missing Note" in result
        assert "2 more" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_unresolved_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianNotRunningError
        from obsidian_blade_mcp.server import vault_unresolved

        mock_client = MagicMock()
        mock_client.unresolved.side_effect = ObsidianNotRunningError("not running")
        mock_get_client.return_value = mock_client

        result = await vault_unresolved()
        assert "Error" in result


class TestVaultOrphans:
    """Test vault_orphans tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_orphans_total_only(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_orphans

        mock_client = MagicMock()
        mock_client.orphans.return_value = "12271"
        mock_get_client.return_value = mock_client

        result = await vault_orphans(total_only=True)
        assert "12271" in result
        assert "Orphan" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_orphans_full_list(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_orphans

        mock_client = MagicMock()
        mock_client.orphans.return_value = ["notes/a.md", "notes/b.md", "notes/c.md"]
        mock_get_client.return_value = mock_client

        result = await vault_orphans(total_only=False, limit=2)
        assert "notes/a.md" in result
        assert "1 more" in result


class TestVaultDeadends:
    """Test vault_deadends tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_deadends_total_only(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_deadends

        mock_client = MagicMock()
        mock_client.deadends.return_value = "12933"
        mock_get_client.return_value = mock_client

        result = await vault_deadends(total_only=True)
        assert "12933" in result
        assert "Dead-end" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_deadends_full_list(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_deadends

        mock_client = MagicMock()
        mock_client.deadends.return_value = ["x.md", "y.md"]
        mock_get_client.return_value = mock_client

        result = await vault_deadends(total_only=False)
        assert "x.md" in result


# ===========================================================================
# Phase 4 — Task, Bookmark, File Operation Tools
# ===========================================================================


class TestVaultTasks:
    """Test vault_tasks tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tasks_success(self, mock_get_client, sample_tasks):
        from obsidian_blade_mcp.server import vault_tasks

        mock_client = MagicMock()
        mock_client.tasks.return_value = sample_tasks
        mock_get_client.return_value = mock_client

        result = await vault_tasks()
        assert "Buy groceries" in result
        assert "[ ]" in result
        assert "[x]" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tasks_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_tasks

        mock_client = MagicMock()
        mock_client.tasks.return_value = []
        mock_get_client.return_value = mock_client

        result = await vault_tasks()
        assert "No tasks" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tasks_with_limit(self, mock_get_client, sample_tasks):
        from obsidian_blade_mcp.server import vault_tasks

        mock_client = MagicMock()
        mock_client.tasks.return_value = sample_tasks
        mock_get_client.return_value = mock_client

        result = await vault_tasks(limit=2)
        assert "2 more tasks" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_tasks_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianNotRunningError
        from obsidian_blade_mcp.server import vault_tasks

        mock_client = MagicMock()
        mock_client.tasks.side_effect = ObsidianNotRunningError("not running")
        mock_get_client.return_value = mock_client

        result = await vault_tasks()
        assert "Error" in result


class TestVaultTaskUpdate:
    """Test vault_task_update tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_task_update_toggle(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_task_update

        mock_client = MagicMock()
        mock_client.task_update.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_task_update(ref="notes/Todo.md:5")
        assert "Task updated" in result
        assert "toggle" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_task_update_complete(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_task_update

        mock_client = MagicMock()
        mock_client.task_update.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_task_update(ref="notes/Todo.md:5", action="complete")
        assert "complete" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_task_update_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianFileNotFoundError
        from obsidian_blade_mcp.server import vault_task_update

        mock_client = MagicMock()
        mock_client.task_update.side_effect = ObsidianFileNotFoundError("not found")
        mock_get_client.return_value = mock_client

        result = await vault_task_update(ref="missing:1")
        assert "Error" in result


class TestVaultBookmarks:
    """Test vault_bookmarks tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_bookmarks_success(self, mock_get_client, sample_bookmarks):
        from obsidian_blade_mcp.server import vault_bookmarks

        mock_client = MagicMock()
        mock_client.bookmarks.return_value = sample_bookmarks
        mock_get_client.return_value = mock_client

        result = await vault_bookmarks()
        assert "Important Note" in result
        assert "Projects" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_bookmarks_empty(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_bookmarks

        mock_client = MagicMock()
        mock_client.bookmarks.return_value = []
        mock_get_client.return_value = mock_client

        result = await vault_bookmarks()
        assert "No bookmarks" in result


class TestVaultBookmarkAdd:
    """Test vault_bookmark_add tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_bookmark_add_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_bookmark_add

        mock_client = MagicMock()
        mock_client.bookmark_add.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_bookmark_add(path="notes/Important.md", title="My Bookmark")
        assert "Bookmarked" in result


class TestVaultDelete:
    """Test vault_delete tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_delete_to_trash(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_delete

        mock_client = MagicMock()
        mock_client.delete_file.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_delete(path="notes/Old.md")
        assert "Deleted" in result
        assert "trash" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_delete_permanent(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_delete

        mock_client = MagicMock()
        mock_client.delete_file.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_delete(path="notes/Old.md", permanent=True)
        assert "Permanently deleted" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_delete_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianFileNotFoundError
        from obsidian_blade_mcp.server import vault_delete

        mock_client = MagicMock()
        mock_client.delete_file.side_effect = ObsidianFileNotFoundError("not found")
        mock_get_client.return_value = mock_client

        result = await vault_delete(path="missing.md")
        assert "Error" in result


class TestVaultRename:
    """Test vault_rename tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_rename_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_rename

        mock_client = MagicMock()
        mock_client.rename.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_rename(path="notes/Old.md", new_name="New Name")
        assert "Renamed" in result
        assert "Old.md" in result
        assert "New Name" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_rename_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianFileNotFoundError
        from obsidian_blade_mcp.server import vault_rename

        mock_client = MagicMock()
        mock_client.rename.side_effect = ObsidianFileNotFoundError("not found")
        mock_get_client.return_value = mock_client

        result = await vault_rename(path="missing.md", new_name="New")
        assert "Error" in result


class TestVaultMove:
    """Test vault_move tool."""

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_move_success(self, mock_get_client):
        from obsidian_blade_mcp.server import vault_move

        mock_client = MagicMock()
        mock_client.move.return_value = ""
        mock_get_client.return_value = mock_client

        result = await vault_move(path="notes/Note.md", destination="archive/")
        assert "Moved" in result
        assert "Note.md" in result
        assert "archive/" in result

    @patch("obsidian_blade_mcp.server._get_client")
    async def test_move_error(self, mock_get_client):
        from obsidian_blade_mcp.client import ObsidianFileNotFoundError
        from obsidian_blade_mcp.server import vault_move

        mock_client = MagicMock()
        mock_client.move.side_effect = ObsidianFileNotFoundError("not found")
        mock_get_client.return_value = mock_client

        result = await vault_move(path="missing.md", destination="archive/")
        assert "Error" in result
