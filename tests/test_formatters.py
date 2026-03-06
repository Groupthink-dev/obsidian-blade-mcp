"""Tests for token-efficient output formatters."""

from __future__ import annotations

from obsidian_blade_mcp.formatters import (
    format_bookmark_list,
    format_file_concise,
    format_file_list,
    format_folder_list,
    format_link_list,
    format_outline,
    format_properties,
    format_search_context,
    format_search_results,
    format_tag_list,
    format_task_list,
    format_vault_info,
    truncate_content,
)


class TestFormatFileConcise:
    """Test single-file concise formatting."""

    def test_full_entry(self):
        entry = {"path": "notes/Test.md", "size": 2345, "modified": "2026-03-01T10:00:00"}
        result = format_file_concise(entry)
        assert "notes/Test.md" in result
        assert "2.3 KB" in result
        assert "2026-03-01" in result

    def test_minimal_entry(self):
        result = format_file_concise({"path": "test.md"})
        assert result == "test.md"

    def test_name_fallback(self):
        result = format_file_concise({"name": "Test Note"})
        assert "Test Note" in result


class TestFormatFileList:
    """Test file list formatting with limits."""

    def test_empty_list(self):
        assert format_file_list([]) == "No files found."

    def test_within_limit(self, sample_files):
        result = format_file_list(sample_files, limit=10)
        assert "Note A.md" in result
        assert "more" not in result

    def test_exceeds_limit(self, sample_files):
        result = format_file_list(sample_files, limit=2)
        assert "1 more" in result

    def test_custom_total(self):
        files = [{"path": "a.md"}, {"path": "b.md"}]
        result = format_file_list(files, limit=2, total=100)
        assert "98 more" in result


class TestFormatFolderList:
    """Test folder list formatting."""

    def test_empty(self):
        assert format_folder_list([]) == "No folders found."

    def test_string_list(self, sample_folders):
        result = format_folder_list(sample_folders)
        assert "atlas/" in result
        assert "spaces/" in result

    def test_dict_list(self):
        folders = [{"path": "atlas/"}, {"path": "spaces/"}]
        result = format_folder_list(folders)
        assert "atlas/" in result


class TestFormatProperties:
    """Test property formatting."""

    def test_dict_properties(self, sample_properties):
        result = format_properties(sample_properties)
        assert "kind: effort" in result
        assert "status: on" in result
        assert "rank: 8" in result
        assert "tags: [#IT/software, #PKM/workflow]" in result

    def test_list_properties(self):
        props = [
            {"name": "status", "value": "on"},
            {"name": "rank", "value": 8},
        ]
        result = format_properties(props)
        assert "status: on" in result
        assert "rank: 8" in result

    def test_empty_dict(self):
        result = format_properties({})
        assert "No properties" in result

    def test_none_values_omitted(self):
        result = format_properties({"kind": "effort", "empty": None})
        assert "kind: effort" in result
        assert "empty" not in result


class TestFormatVaultInfo:
    """Test vault info formatting."""

    def test_full_info(self, sample_vault_info):
        result = format_vault_info(sample_vault_info)
        assert "test-vault" in result
        assert "1234" in result

    def test_string_passthrough(self):
        assert format_vault_info("raw output") == "raw output"


class TestTruncateContent:
    """Test content truncation."""

    def test_short_content(self):
        content = "Short\ncontent"
        assert truncate_content(content) == content

    def test_long_content(self):
        content = "\n".join(f"Line {i}" for i in range(200))
        result = truncate_content(content, max_lines=100)
        assert "100 more lines" in result
        assert "Line 0" in result
        assert "Line 99" in result
        assert "Line 100" not in result.split("…")[0]


class TestFormatSearchResults:
    """Test search result formatting."""

    def test_empty_results(self):
        assert format_search_results([]) == "No results found."

    def test_list_results(self, sample_search_results):
        result = format_search_results(sample_search_results)
        assert "Docker.md" in result
        assert "raw-capture.md" in result

    def test_string_fallback(self):
        text = "atlas/cards/Docker.md\nspaces/note.md\n"
        result = format_search_results(text)
        assert "Docker.md" in result
        assert "note.md" in result

    def test_limit_truncation(self, sample_search_results):
        result = format_search_results(sample_search_results, limit=1)
        assert "2 more" in result

    def test_empty_string(self):
        assert format_search_results("") == "No results found."


class TestFormatSearchContext:
    """Test search context formatting."""

    def test_empty(self):
        assert format_search_context("") == "No results found."

    def test_normal(self, sample_search_context):
        result = format_search_context(sample_search_context)
        assert "Docker.md:5:" in result
        assert "Docker.md:12:" in result

    def test_limit(self, sample_search_context):
        result = format_search_context(sample_search_context, limit=1)
        assert "2 more matches" in result


class TestFormatTagList:
    """Test tag list formatting."""

    def test_empty(self):
        assert format_tag_list([]) == "No tags found."

    def test_normal(self, sample_tags):
        result = format_tag_list(sample_tags)
        assert "#IT/software/Docker (15)" in result
        assert "#PKM/workflow (42)" in result

    def test_limit(self, sample_tags):
        result = format_tag_list(sample_tags, limit=2)
        assert "2 more tags" in result

    def test_string_fallback(self):
        text = "#IT/software\n#PKM/workflow\n"
        result = format_tag_list(text)
        assert "#IT/software" in result


# ===========================================================================
# Phase 3 — format_outline, format_link_list
# ===========================================================================


class TestFormatOutline:
    """Test outline formatting."""

    def test_json_headings(self, sample_outline):
        result = format_outline(sample_outline)
        assert "# My Note (line 1)" in result
        assert "  ## Introduction (line 5)" in result
        assert "    ### Sub-detail (line 15)" in result
        assert "  ## Conclusion (line 25)" in result

    def test_empty_list(self):
        assert format_outline([]) == "No headings found."

    def test_string_fallback(self):
        text = "# Title\n  ## Section\n    ### Sub"
        result = format_outline(text)
        assert "# Title" in result
        assert "## Section" in result

    def test_empty_string(self):
        assert format_outline("") == "No headings found."


class TestFormatLinkList:
    """Test link list formatting."""

    def test_normal_list(self):
        items = ["Target A", "Target B", "Target C"]
        result = format_link_list(items)
        assert "Target A" in result
        assert "Target B" in result
        assert "Target C" in result

    def test_limit(self):
        items = ["A", "B", "C", "D", "E"]
        result = format_link_list(items, limit=2)
        assert "A" in result
        assert "B" in result
        assert "3 more links" in result

    def test_empty(self):
        result = format_link_list([], label="backlinks")
        assert "No backlinks found." == result

    def test_dict_items(self):
        items = [{"link": "Missing Note"}, {"link": "Another"}]
        result = format_link_list(items, label="unresolved links")
        assert "Missing Note" in result
        assert "Another" in result

    def test_string_input(self):
        text = "Link A\nLink B\nLink C"
        result = format_link_list(text)
        assert "Link A" in result
        assert "Link C" in result

    def test_custom_label(self):
        result = format_link_list([], label="aliases")
        assert "No aliases found." == result


# ===========================================================================
# Phase 4 — format_task_list, format_bookmark_list
# ===========================================================================


class TestFormatTaskList:
    """Test task list formatting."""

    def test_normal(self, sample_tasks):
        result = format_task_list(sample_tasks)
        assert "- [ ] Buy groceries (notes/Todo.md:5)" in result
        assert "- [x] Review PR (notes/Todo.md:8)" in result
        assert "- [ ] Deploy v0.4 (notes/Sprint.md:3)" in result
        assert "- [x] Write tests (notes/Sprint.md:7)" in result

    def test_empty(self):
        assert format_task_list([]) == "No tasks found."

    def test_limit(self, sample_tasks):
        result = format_task_list(sample_tasks, limit=2)
        assert "Buy groceries" in result
        assert "Review PR" in result
        assert "2 more tasks" in result

    def test_string_fallback(self):
        text = "- [ ] Task one\n- [x] Task two\n"
        result = format_task_list(text)
        assert "Task one" in result
        assert "Task two" in result

    def test_string_empty(self):
        assert format_task_list("") == "No tasks found."

    def test_task_without_line(self):
        tasks = [{"text": "No line info", "status": "unchecked", "path": "notes/Todo.md"}]
        result = format_task_list(tasks)
        assert "- [ ] No line info (notes/Todo.md)" in result


class TestFormatBookmarkList:
    """Test bookmark list formatting."""

    def test_normal(self, sample_bookmarks):
        result = format_bookmark_list(sample_bookmarks)
        assert "file: Important Note" in result
        assert "folder: Projects" in result
        assert "search: Docker refs" in result
        assert "url: Anthropic" in result

    def test_empty(self):
        assert format_bookmark_list([]) == "No bookmarks found."

    def test_limit(self, sample_bookmarks):
        result = format_bookmark_list(sample_bookmarks, limit=2)
        assert "Important Note" in result
        assert "Projects" in result
        assert "2 more bookmarks" in result

    def test_string_fallback(self):
        text = "file: Note A\nfolder: Projects\n"
        result = format_bookmark_list(text)
        assert "Note A" in result
        assert "Projects" in result

    def test_string_empty(self):
        assert format_bookmark_list("") == "No bookmarks found."

    def test_untitled_bookmark(self):
        bookmarks = [{"type": "file"}]
        result = format_bookmark_list(bookmarks)
        assert "file: (untitled)" in result
