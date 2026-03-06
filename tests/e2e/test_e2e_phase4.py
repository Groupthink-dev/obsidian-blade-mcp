"""E2E tests for Phase 4: tasks, bookmarks, file operations against a real Obsidian vault."""

from __future__ import annotations

import uuid

import pytest

from obsidian_blade_mcp.client import ObsidianCLI, ObsidianCLIError

pytestmark = pytest.mark.e2e


class TestTasks:
    """Test task operations against live Obsidian."""

    def test_tasks_with_scratch_note(self, e2e_cli: ObsidianCLI) -> None:
        """Create a note with tasks, list them, toggle one."""
        note_name = f"_e2e_tasks_{uuid.uuid4().hex[:8]}"
        content = "# Task Test\n\n- [ ] First task\n- [ ] Second task\n- [x] Done task\n"
        e2e_cli.create(name=note_name, content=content, path="+/")

        try:
            # List tasks for this note
            tasks = e2e_cli.tasks(file=note_name)
            if isinstance(tasks, list):
                assert len(tasks) >= 2
                unchecked = [t for t in tasks if t.get("status") in ("unchecked", "open")]
                assert len(unchecked) >= 2

            # List only unchecked tasks
            unchecked_tasks = e2e_cli.tasks(file=note_name, status="unchecked")
            if isinstance(unchecked_tasks, list):
                assert len(unchecked_tasks) >= 2

        finally:
            try:
                e2e_cli.delete_file(path=f"+/{note_name}.md")
            except ObsidianCLIError:
                pass

    def test_task_update_toggle(self, e2e_cli: ObsidianCLI) -> None:
        """Create a note with a task and toggle it."""
        note_name = f"_e2e_toggle_{uuid.uuid4().hex[:8]}"
        content = "# Toggle Test\n\n- [ ] Toggle me\n"
        e2e_cli.create(name=note_name, content=content, path="+/")

        try:
            # Get tasks to find the line number
            tasks = e2e_cli.tasks(file=note_name)
            if isinstance(tasks, list) and tasks:
                task = tasks[0]
                ref = f"{task.get('path', f'+/{note_name}.md')}:{task.get('line', 3)}"
                # Toggle the task
                e2e_cli.task_update(ref=ref, action="complete")

                # Verify it's now checked
                updated_tasks = e2e_cli.tasks(file=note_name, status="checked")
                if isinstance(updated_tasks, list):
                    assert len(updated_tasks) >= 1
        finally:
            try:
                e2e_cli.delete_file(path=f"+/{note_name}.md")
            except ObsidianCLIError:
                pass


class TestBookmarks:
    """Test bookmark operations against live Obsidian."""

    def test_bookmarks_list(self, e2e_cli: ObsidianCLI) -> None:
        """List existing bookmarks — should not error."""
        result = e2e_cli.bookmarks()
        # Result can be a list (JSON) or string (fallback) — both are valid
        assert result is not None


class TestFileOperations:
    """Test delete, rename, move against live Obsidian."""

    def test_rename_and_verify(self, e2e_cli: ObsidianCLI) -> None:
        """Create → rename → verify → cleanup."""
        uid = uuid.uuid4().hex[:8]
        original_name = f"_e2e_rename_orig_{uid}"
        new_name = f"_e2e_rename_new_{uid}"
        e2e_cli.create(name=original_name, content="# Rename Test", path="+/")

        try:
            e2e_cli.rename(path=f"+/{original_name}.md", to=new_name)

            # Verify the new file exists by reading it
            content = e2e_cli.read(file=new_name)
            assert "Rename Test" in content
        finally:
            # Cleanup — try both names
            for name in [new_name, original_name]:
                try:
                    e2e_cli.delete_file(path=f"+/{name}.md")
                except ObsidianCLIError:
                    pass

    def test_move_and_verify(self, e2e_cli: ObsidianCLI) -> None:
        """Create in +/ → move to +/ingest/ → verify → cleanup."""
        uid = uuid.uuid4().hex[:8]
        note_name = f"_e2e_move_{uid}"
        e2e_cli.create(name=note_name, content="# Move Test", path="+/")

        try:
            e2e_cli.move(path=f"+/{note_name}.md", to="+/ingest/")

            # Verify at new location
            content = e2e_cli.read(path=f"+/ingest/{note_name}.md")
            assert "Move Test" in content
        finally:
            # Cleanup — try both locations
            for p in [f"+/ingest/{note_name}.md", f"+/{note_name}.md"]:
                try:
                    e2e_cli.delete_file(path=p)
                except ObsidianCLIError:
                    pass

    def test_delete_to_trash(self, e2e_cli: ObsidianCLI) -> None:
        """Create → delete (trash) → verify gone."""
        uid = uuid.uuid4().hex[:8]
        note_name = f"_e2e_delete_{uid}"
        e2e_cli.create(name=note_name, content="# Delete Test", path="+/")

        e2e_cli.delete_file(path=f"+/{note_name}.md")

        # Verify file is gone (should raise file-not-found)
        with pytest.raises(ObsidianCLIError):
            e2e_cli.read(file=note_name)

    def test_delete_nonexistent_raises(self, e2e_cli: ObsidianCLI) -> None:
        """Deleting a nonexistent file should raise."""
        with pytest.raises(ObsidianCLIError):
            e2e_cli.delete_file(path="+/_e2e_nonexistent_file.md")

    def test_full_lifecycle(self, e2e_cli: ObsidianCLI) -> None:
        """Create → rename → move → delete: full lifecycle test."""
        uid = uuid.uuid4().hex[:8]
        orig_name = f"_e2e_lifecycle_{uid}"
        renamed = f"_e2e_lifecycle_renamed_{uid}"
        e2e_cli.create(name=orig_name, content="# Lifecycle Test", path="+/")

        try:
            # Rename
            e2e_cli.rename(path=f"+/{orig_name}.md", to=renamed)

            # Move
            e2e_cli.move(path=f"+/{renamed}.md", to="+/ingest/")

            # Verify at final location
            content = e2e_cli.read(path=f"+/ingest/{renamed}.md")
            assert "Lifecycle Test" in content

            # Delete
            e2e_cli.delete_file(path=f"+/ingest/{renamed}.md")

            # Verify gone
            with pytest.raises(ObsidianCLIError):
                e2e_cli.read(path=f"+/ingest/{renamed}.md")
        except ObsidianCLIError:
            # Cleanup — try all possible locations
            for p in [f"+/ingest/{renamed}.md", f"+/{renamed}.md", f"+/{orig_name}.md"]:
                try:
                    e2e_cli.delete_file(path=p)
                except ObsidianCLIError:
                    pass
            raise
