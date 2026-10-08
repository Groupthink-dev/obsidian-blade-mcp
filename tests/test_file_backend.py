"""Tests for the direct-file backend against a temporary vault."""

from __future__ import annotations

import json
import os
import textwrap
from datetime import datetime

import pytest

from obsidian_blade_mcp.backend import BackendUnsupportedError
from obsidian_blade_mcp.backends.file import (
    FileBackend,
    moment_to_strftime,
    parse_heading,
    split_frontmatter,
)
from obsidian_blade_mcp.client import ObsidianCLIError, ObsidianFileNotFoundError, ObsidianVaultError


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "daily-notes.json").write_text(
        json.dumps({"folder": "calendar/logs", "format": "YYYY-MM-DD", "template": "templates/daily"})
    )
    (tmp_path / ".obsidian" / "templates.json").write_text(json.dumps({"folder": "templates"}))
    (tmp_path / ".obsidian" / "bookmarks.json").write_text(
        json.dumps(
            {
                "items": [
                    {"type": "file", "path": "notes/Alpha.md", "title": "Alpha"},
                    {
                        "type": "group",
                        "title": "Work",
                        "items": [{"type": "search", "query": "status: on"}, {"type": "url", "url": "https://x.y"}],
                    },
                ]
            }
        )
    )
    (tmp_path / ".obsidian" / "workspace.json").write_text("{}")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "daily.md").write_text("# {{title}}\n\n## Log\n")
    (tmp_path / "templates" / "effort.md").write_text("---\nkind: effort\n---\n# {{title}}\n")
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "Alpha.md").write_text(
        textwrap.dedent(
            """\
            ---
            kind: card
            status: on
            rank: 8
            tags: [IT/software, PKM]
            aliases:
              - Alpha Note
            ---
            # Alpha

            Links to [[Beta]] and [[Gamma|the gamma]] and [[Missing Note]] #inline/tag.

            ## Tasks

            - [ ] first task
            - [x] done task
            - [ ] another #inline/tag

            ```
            - [ ] not a task, inside a fence
            [[NotALink]]
            ```

            ## Section B

            body b
            """
        )
    )
    (notes / "Beta.md").write_text("---\nkind: card\nstatus: off\n---\n# Beta\n\nSee [[Alpha]].\n")
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "Gamma.md").write_text("# Gamma\n\nNo links here, Docker mention.\n")
    (tmp_path / "deep" / "Beta.md").write_text("# Deep Beta\n")
    (tmp_path / "atlas").mkdir()
    (tmp_path / "atlas" / "DD.base").write_text("views: []\n")
    (tmp_path / ".trash").mkdir()
    (tmp_path / ".trash" / "old.md").write_text("x")
    return tmp_path


@pytest.fixture
def fb(vault):
    return FileBackend(str(vault))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_heading(self):
        assert parse_heading("## Title\n") == (2, "Title")
        assert parse_heading("#NoSpace") is None
        assert parse_heading("####### too deep") is None
        assert parse_heading("text") is None

    def test_split_frontmatter(self):
        y, body = split_frontmatter("---\na: 1\n---\nbody\n")
        assert y == "a: 1"
        assert body == "body\n"
        assert split_frontmatter("no fm\n") == (None, "no fm\n")
        assert split_frontmatter("---\nunterminated\n") == (None, "---\nunterminated\n")

    def test_moment_to_strftime(self):
        assert moment_to_strftime("YYYY-MM-DD") == "%Y-%m-%d"
        assert moment_to_strftime("[Week] YYYY") == "Week %Y"
        assert datetime(2026, 10, 9).strftime(moment_to_strftime("YYYY-MM-DD dddd")) == "2026-10-09 Friday"


# ---------------------------------------------------------------------------
# Construction and path safety
# ---------------------------------------------------------------------------


class TestPaths:
    def test_missing_vault(self, tmp_path):
        with pytest.raises(ObsidianVaultError):
            FileBackend(str(tmp_path / "nope"))

    def test_escape_refused(self, fb):
        with pytest.raises(ObsidianCLIError):
            fb.read(path="../etc/passwd")

    def test_reserved_dir_refused(self, fb):
        with pytest.raises(ObsidianCLIError):
            fb.read(path=".obsidian/workspace.json")

    def test_symlink_escape_refused(self, fb, vault, tmp_path):
        outside = tmp_path.parent / "outside.md"
        outside.write_text("secret")
        os.symlink(outside, vault / "notes" / "link.md")
        with pytest.raises(ObsidianCLIError):
            fb.read(path="notes/link.md")
        assert "notes/link.md" not in [e["path"] for e in fb.files()]

    def test_path_without_extension(self, fb):
        assert "# Alpha" in fb.read(path="notes/Alpha")

    def test_file_resolves_like_wikilink(self, fb):
        assert fb.resolve_name("alpha") == "notes/Alpha.md"
        assert fb.resolve_name("Beta") == "deep/Beta.md"  # ambiguous: shortest path, then alphabetical
        assert fb.resolve_name("deep/Beta") == "deep/Beta.md"
        assert fb.resolve_name("Alpha Note") == "notes/Alpha.md"  # alias
        assert fb.resolve_name("Nope") is None

    def test_no_target_errors(self, fb):
        with pytest.raises(ObsidianCLIError, match="file= or path="):
            fb.read()


# ---------------------------------------------------------------------------
# F1 discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_vault_info(self, fb, vault):
        info = fb.vault_info()
        assert info["name"] == vault.name
        assert info["files"] == 7  # 4 notes + 2 templates + 1 base; .obsidian and .trash excluded
        assert info["backend"] == "file"

    def test_files_filters(self, fb):
        assert {e["path"] for e in fb.files(folder="notes")} == {"notes/Alpha.md", "notes/Beta.md"}
        assert [e["path"] for e in fb.files(ext="base")] == ["atlas/DD.base"]
        assert all({"path", "size", "modified"} <= set(e) for e in fb.files())

    def test_folders(self, fb):
        assert fb.folders() == ["atlas", "deep", "notes", "templates"]

    def test_file_info(self, fb):
        info = fb.file_info(path="notes/Alpha.md")
        assert info["name"] == "Alpha"
        assert info["extension"] == "md"
        assert info["frontmatter"]["kind"] == "card"
        with pytest.raises(ObsidianFileNotFoundError):
            fb.file_info(path="notes/Nope.md")

    def test_recents(self, fb):
        assert len(fb.recents(limit=2)) == 2


# ---------------------------------------------------------------------------
# F2 content
# ---------------------------------------------------------------------------


class TestContent:
    def test_create_and_overwrite(self, fb, vault):
        assert fb.create("New", content="hi", path="notes") == "Created: notes/New.md"
        assert (vault / "notes" / "New.md").read_text() == "hi"
        with pytest.raises(ObsidianCLIError, match="already exists"):
            fb.create("New", path="notes")
        fb.create("New", content="again", path="notes", overwrite=True)
        assert (vault / "notes" / "New.md").read_text() == "again"

    def test_create_from_template(self, fb, vault):
        fb.create("Effort X", template="effort")
        assert (vault / "Effort X.md").read_text().startswith("---\nkind: effort\n---\n# Effort X\n")

    def test_append_prepend_preserve_frontmatter(self, fb, vault):
        fb.append("tail", path="notes/Beta.md")
        fb.prepend("head", path="notes/Beta.md")
        text = (vault / "notes" / "Beta.md").read_text()
        assert text.startswith("---\nkind: card\nstatus: off\n---\nhead\n# Beta")
        assert text.endswith("See [[Alpha]].\ntail\n")

    def test_outline_line_numbers_include_frontmatter(self, fb):
        out = fb.outline(path="notes/Alpha.md")
        assert out[0] == {"level": 1, "heading": "Alpha", "line": 9}
        assert [h["heading"] for h in out] == ["Alpha", "Tasks", "Section B"]

    def test_section_read_and_replace(self, fb, vault):
        assert fb.section_read("notes/Alpha.md", "Section B") == "\nbody b"
        fb.section_replace("notes/Alpha.md", "Tasks", "replaced\n")
        text = (vault / "notes" / "Alpha.md").read_text()
        assert "## Tasks\nreplaced\n## Section B" in text
        with pytest.raises(ObsidianCLIError, match="not found"):
            fb.section_read("notes/Alpha.md", "Nope")

    def test_delete_to_trash_and_permanent(self, fb, vault):
        assert fb.delete_file("deep/Gamma.md") == "Moved to trash: deep/Gamma.md"
        assert (vault / ".trash" / "Gamma.md").exists()
        fb.delete_file("deep/Beta.md", permanent=True)
        assert not (vault / "deep" / "Beta.md").exists()

    def test_rename_rewrites_links(self, fb, vault):
        msg = fb.rename("notes/Beta.md", "Bravo")
        assert msg.startswith("Renamed: notes/Beta.md → notes/Bravo.md")
        assert "[[Bravo]]" in (vault / "notes" / "Alpha.md").read_text()
        assert "1 links updated" in msg

    def test_move_keeps_bare_links(self, fb, vault):
        fb.move("notes/Beta.md", "deep/sub")
        assert (vault / "deep" / "sub" / "Beta.md").exists()
        assert "[[Beta]]" in (vault / "notes" / "Alpha.md").read_text()
        # bare [[Beta]] now has two candidates; the shortest path wins, as in Obsidian
        assert fb.links(path="notes/Alpha.md")[0] == "deep/Beta.md"

    def test_atomic_write_leaves_no_temp(self, fb, vault):
        fb.append("x", path="notes/Beta.md")
        assert not [p for p in os.listdir(vault / "notes") if p.startswith(".blade-")]


# ---------------------------------------------------------------------------
# F3 properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_read(self, fb):
        assert fb.property_read("rank", path="notes/Alpha.md") == 8
        assert fb.property_read("status", path="notes/Alpha.md") == "on"  # YAML 1.1 bool stays string
        with pytest.raises(ObsidianCLIError):
            fb.property_read("nope", path="notes/Alpha.md")

    def test_set_preserves_order_and_body(self, fb, vault):
        fb.property_set("status", "done", path="notes/Alpha.md")
        fb.property_set("new", "[a, b]", path="notes/Alpha.md")
        text = (vault / "notes" / "Alpha.md").read_text()
        head = text.split("---\n")[1]
        assert head.index("kind:") < head.index("status:") < head.index("rank:") < head.index("new:")
        assert "- a\n- b" in head
        assert "# Alpha\n\nLinks to" in text

    def test_set_on_note_without_frontmatter(self, fb, vault):
        fb.property_set("kind", "card", path="deep/Gamma.md")
        assert (vault / "deep" / "Gamma.md").read_text().startswith("---\nkind: card\n---\n# Gamma")

    def test_remove(self, fb, vault):
        fb.property_remove("rank", path="notes/Alpha.md")
        assert "rank" not in (vault / "notes" / "Alpha.md").read_text()
        fb.property_remove("kind", path="notes/Beta.md")
        fb.property_remove("status", path="notes/Beta.md")
        assert (vault / "notes" / "Beta.md").read_text().startswith("# Beta")

    def test_properties_for_file_and_vault(self, fb):
        assert fb.properties(path="notes/Alpha.md")["kind"] == "card"
        names = {p["name"]: p["count"] for p in fb.properties()}
        assert names["kind"] == 3  # Alpha, Beta, templates/effort

    def test_query_properties(self, fb):
        rows = fb.query_properties("status", "on", path="notes", fields="kind,status")
        assert rows == [{"file": "notes/Alpha.md", "properties": {"kind": "card", "status": "on"}}]
        assert fb.query_properties("kind", "card") and len(fb.query_properties("kind", "card", limit=1)) == 1


# ---------------------------------------------------------------------------
# F4 search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search(self, fb):
        assert fb.search("docker") == ["deep/Gamma.md"]
        assert fb.search("docker", case_sensitive=True) == []
        assert fb.search("Beta", path="notes") == ["notes/Alpha.md", "notes/Beta.md"]

    def test_search_context(self, fb):
        out = fb.search_context("Docker")
        assert out == "deep/Gamma.md:3: No links here, Docker mention."


# ---------------------------------------------------------------------------
# F5 graph and tags
# ---------------------------------------------------------------------------


class TestGraph:
    def test_links_resolution_and_fence_exclusion(self, fb):
        assert fb.links(path="notes/Alpha.md") == ["notes/Beta.md", "deep/Gamma.md"]

    def test_backlinks(self, fb):
        assert fb.backlinks(path="notes/Beta.md") == [{"file": "notes/Alpha.md"}]
        assert fb.backlinks(path="deep/Gamma.md") == [{"file": "notes/Alpha.md"}]

    def test_unresolved(self, fb):
        assert fb.unresolved() == [{"link": "Missing Note"}]
        assert fb.unresolved(path="deep") == []

    def test_orphans_and_deadends(self, fb):
        # Alpha <- Beta, Beta <- Alpha, Gamma <- Alpha; the rest have no inbound links
        assert fb.orphans() == "3"
        assert set(fb.orphans(total_only=False)) == {"deep/Beta.md", "templates/daily.md", "templates/effort.md"}
        assert fb.deadends(path="deep") == "2"

    def test_tags(self, fb):
        tags = {t["tag"]: t["count"] for t in fb.tags()}
        assert tags == {"#IT/software": "1", "#PKM": "1", "#inline/tag": "2"}
        assert fb.tags(sort_by_count=True)[0]["tag"] == "#inline/tag"
        assert fb.tag("inline/tag") == ["notes/Alpha.md"]
        assert fb.tag("#PKM") == ["notes/Alpha.md"]

    def test_aliases(self, fb):
        assert fb.aliases(path="notes/Alpha.md") == ["Alpha Note"]
        assert fb.aliases(path="notes/Beta.md") == []

    def test_index_refreshes_after_write(self, fb):
        assert fb.backlinks(path="deep/Gamma.md") == [{"file": "notes/Alpha.md"}]
        fb.append("[[Gamma]]", path="notes/Beta.md")
        assert {b["file"] for b in fb.backlinks(path="deep/Gamma.md")} == {"notes/Alpha.md", "notes/Beta.md"}


# ---------------------------------------------------------------------------
# F6 bases
# ---------------------------------------------------------------------------


class TestBases:
    def test_bases_listing(self, fb):
        assert fb.bases() == ["atlas/DD.base"]

    def test_query_unsupported(self, fb):
        with pytest.raises(BackendUnsupportedError, match="backend_unsupported"):
            fb.base_query(path="atlas/DD.base")
        with pytest.raises(BackendUnsupportedError):
            fb.base_views(path="atlas/DD.base")
        with pytest.raises(BackendUnsupportedError):
            fb.bookmark_add(path="notes/Alpha.md")


# ---------------------------------------------------------------------------
# F7 tasks and bookmarks
# ---------------------------------------------------------------------------


class TestTasks:
    def test_tasks(self, fb):
        tasks = fb.tasks(path="notes/Alpha.md")
        assert [(t["text"], t["status"], t["line"]) for t in tasks] == [
            ("first task", "unchecked", 15),
            ("done task", "checked", 16),
            ("another #inline/tag", "unchecked", 17),
        ]
        assert len(fb.tasks(status="checked")) == 1
        assert len(fb.tasks(status="todo")) == 2

    def test_task_update(self, fb, vault):
        assert fb.task_update("notes/Alpha.md:15", "complete") == "Task updated: notes/Alpha.md:15 ([x])"
        fb.task_update("notes/Alpha.md:16", "toggle")
        text = (vault / "notes" / "Alpha.md").read_text()
        assert "- [x] first task" in text and "- [ ] done task" in text
        with pytest.raises(ObsidianCLIError, match="No task"):
            fb.task_update("notes/Alpha.md:10")

    def test_bookmarks_flatten_groups(self, fb):
        bms = fb.bookmarks()
        assert bms[0] == {"type": "file", "title": "Alpha", "path": "notes/Alpha.md"}
        assert bms[1] == {"type": "search", "query": "status: on", "group": "Work"}
        assert bms[2]["url"] == "https://x.y"

    def test_bookmarks_absent(self, tmp_path):
        assert FileBackend(str(tmp_path)).bookmarks() == []


# ---------------------------------------------------------------------------
# F8 daily and templates
# ---------------------------------------------------------------------------


class TestDailyAndTemplates:
    def test_daily_path(self, fb):
        assert fb.daily_path(datetime(2026, 10, 9)) == "calendar/logs/2026-10-09.md"

    def test_daily_read_missing(self, fb):
        with pytest.raises(ObsidianFileNotFoundError):
            fb.daily_read()

    def test_daily_append_creates_from_template(self, fb, vault):
        fb.daily_append("- note")
        rel = fb.daily_path()
        text = (vault / rel).read_text()
        assert text.startswith(f"# {os.path.basename(rel)[:-3]}\n\n## Log\n")
        assert text.endswith("- note\n")
        fb.daily_append("- second")
        assert (vault / rel).read_text().endswith("- note\n- second\n")

    def test_template_read(self, fb):
        assert fb.template_read("effort").startswith("---\nkind: effort")
        assert fb.template_read("templates/daily").startswith("# {{title}}")
        with pytest.raises(ObsidianFileNotFoundError):
            fb.template_read("nope")

    def test_defaults_without_config(self, tmp_path):
        fb = FileBackend(str(tmp_path))
        assert fb.daily_path(datetime(2026, 1, 2)) == "2026-01-02.md"


class TestFrontmatterLinks:
    def test_links_in_frontmatter_values_are_indexed(self, vault):
        (vault / "notes" / "Child.md").write_text(
            '---\nup: "[[Alpha]]"\nrelated:\n  - "[[Beta]]"\n  - "[[Missing]]"\n---\nbody\n'
        )
        fb = FileBackend(str(vault))
        assert fb.links(path="notes/Child.md") == ["notes/Alpha.md", "notes/Beta.md"]
        assert {d["file"] for d in fb.backlinks(path="notes/Alpha.md")} >= {"notes/Child.md"}
        assert any(u["link"] == "Missing" for u in fb.unresolved(path="notes"))
