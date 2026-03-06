"""Token-efficient output formatters for Obsidian vault data.

Design principles:
- Concise by default (one line per item)
- Null fields omitted
- Lists capped and annotated with total count
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from obsidian_blade_mcp.models import DEFAULT_LIMIT


def format_file_concise(entry: dict[str, Any] | str) -> str:
    """Format a file entry as a single concise line.

    Handles both dict entries (with path/size/modified) and plain strings (CLI output).
    Example: ``notes/My Note.md (2.3 KB, 2026-03-01)``
    """
    if isinstance(entry, str):
        return entry.strip()
    path = entry.get("path", entry.get("name", "unknown"))
    parts = [path]
    if size := entry.get("size"):
        parts.append(f"({_human_size(size)})")
    if modified := entry.get("modified") or entry.get("mtime"):
        parts.append(str(modified)[:10])
    return " ".join(parts)


def format_file_list(
    files: Sequence[dict[str, Any] | str],
    limit: int = DEFAULT_LIMIT,
    total: int | None = None,
) -> str:
    """Format a list of files with limit and total annotation."""
    if not files:
        return "No files found."

    actual_total = total if total is not None else len(files)
    shown = files[:limit]
    lines = [format_file_concise(f) for f in shown]

    if actual_total > len(shown):
        lines.append(f"… {actual_total - len(shown)} more (use limit= to see more)")

    return "\n".join(lines)


def format_folder_list(folders: list[str] | list[dict[str, Any]]) -> str:
    """Format a list of folders."""
    if not folders:
        return "No folders found."

    lines = []
    for f in folders:
        if isinstance(f, dict):
            lines.append(f.get("path", str(f)))
        else:
            lines.append(str(f))

    return "\n".join(lines)


def format_properties(props: dict[str, Any] | list[dict[str, Any]]) -> str:
    """Format frontmatter properties concisely.

    Example::

        kind: effort
        status: on
        rank: 8
        tags: [#IT/software, #PKM/workflow]
    """
    if isinstance(props, list):
        # List of {name, value} dicts
        lines = []
        for p in props:
            name = p.get("name", p.get("key", "?"))
            value = p.get("value", "")
            lines.append(f"{name}: {_format_value(value)}")
        return "\n".join(lines) if lines else "No properties."

    if isinstance(props, dict):
        lines = []
        for key, value in props.items():
            if value is not None:
                lines.append(f"{key}: {_format_value(value)}")
        return "\n".join(lines) if lines else "No properties."

    return str(props)


def format_vault_info(info: dict[str, Any] | str) -> str:
    """Format vault metadata concisely.

    Handles both JSON dicts and tab-separated CLI output.
    """
    if isinstance(info, str):
        # CLI returns tab-separated key\tvalue lines — format as key: value
        lines = []
        for line in info.strip().split("\n"):
            parts = line.split("\t", 1)
            if len(parts) == 2:
                lines.append(f"{parts[0]}: {parts[1]}")
            else:
                lines.append(line)
        return "\n".join(lines) if lines else info

    lines = []
    if name := info.get("name"):
        lines.append(f"Vault: {name}")
    if path := info.get("path"):
        lines.append(f"Path: {path}")
    if file_count := info.get("fileCount") or info.get("files"):
        lines.append(f"Files: {file_count}")
    if note_count := info.get("noteCount") or info.get("notes"):
        lines.append(f"Notes: {note_count}")

    # Include any other top-level keys
    shown_keys = {"name", "path", "fileCount", "files", "noteCount", "notes"}
    for key, value in info.items():
        if key not in shown_keys and value is not None:
            lines.append(f"{key}: {_format_value(value)}")

    return "\n".join(lines) if lines else str(info)


def format_search_results(
    results: list[str] | str,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Format search results (JSON path array or string fallback).

    The CLI returns a JSON array of path strings for ``search format=json``.
    Falls back to newline-delimited string if JSON parsing failed in client.
    """
    if isinstance(results, str):
        paths = [line.strip() for line in results.strip().split("\n") if line.strip()]
    elif isinstance(results, list):
        paths = [str(p) for p in results]
    else:
        return str(results)

    if not paths:
        return "No results found."

    total = len(paths)
    shown = paths[:limit]
    lines = list(shown)

    if total > len(shown):
        lines.append(f"… {total - len(shown)} more (use vault_search_context for detail)")

    return "\n".join(lines)


def format_search_context(
    text: str,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Format search context results (``path:line: text`` per match).

    Each line from the CLI is ``path:linenum: matching text``. Truncate to
    ``limit`` matches.
    """
    if not text or not text.strip():
        return "No results found."

    lines = [line for line in text.strip().split("\n") if line.strip()]
    total = len(lines)
    shown = lines[:limit]

    result_lines = list(shown)
    if total > len(shown):
        result_lines.append(f"… {total - len(shown)} more matches")

    return "\n".join(result_lines)


def format_tag_list(
    tags: list[dict[str, str]] | str,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Format tag listing with counts.

    Input: JSON array of ``{"tag": "#name", "count": "N"}`` objects.
    Output: ``#tag (N)`` per line, truncated to limit.
    """
    if isinstance(tags, str):
        # Fallback: plaintext
        lines = [line.strip() for line in tags.strip().split("\n") if line.strip()]
        if not lines:
            return "No tags found."
        total = len(lines)
        shown = lines[:limit]
        if total > len(shown):
            shown.append(f"… {total - len(shown)} more tags")
        return "\n".join(shown)

    if not tags:
        return "No tags found."

    total = len(tags)
    visible = tags[:limit]
    formatted = [f"{t.get('tag', '?')} ({t.get('count', '0')})" for t in visible]

    if total > len(visible):
        formatted.append(f"… {total - len(visible)} more tags")

    return "\n".join(formatted)


def format_outline(
    headings: list[dict[str, Any]] | str,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Format a heading outline as an indented tree.

    Input: JSON list of ``{"level": N, "heading": "...", "line": N}`` or string.
    Output: indented heading tree, e.g. ``  ## Heading (line 5)``.
    String fallback: return as-is (already tree-formatted by CLI).
    """
    if isinstance(headings, str):
        return headings.strip() if headings.strip() else "No headings found."

    if not headings:
        return "No headings found."

    total = len(headings)
    visible = headings[:limit]
    lines: list[str] = []
    for h in visible:
        level = h.get("level", 1)
        heading = h.get("heading", "?")
        line_num = h.get("line")
        indent = "  " * (level - 1)
        hashes = "#" * level
        suffix = f" (line {line_num})" if line_num is not None else ""
        lines.append(f"{indent}{hashes} {heading}{suffix}")

    if total > len(visible):
        lines.append(f"… {total - len(visible)} more headings")

    return "\n".join(lines)


def format_link_list(
    items: list[str] | list[dict[str, Any]] | str,
    limit: int = DEFAULT_LIMIT,
    label: str = "links",
) -> str:
    """Format a list of links, backlinks, aliases, or unresolved links.

    Input: list of strings, list of dicts (unresolved has ``{"link": "..."}``),
    or newline-delimited string.
    Output: one item per line, capped at limit, with "N more" annotation.
    """
    if isinstance(items, str):
        entries = [line.strip() for line in items.strip().split("\n") if line.strip()]
    elif isinstance(items, list):
        entries = []
        for item in items:
            if isinstance(item, dict):
                entries.append(str(item.get("link") or item.get("path") or item))
            else:
                entries.append(str(item))
    else:
        return str(items)

    if not entries:
        return f"No {label} found."

    total = len(entries)
    shown = entries[:limit]
    lines = list(shown)

    if total > len(shown):
        lines.append(f"… {total - len(shown)} more {label}")

    return "\n".join(lines)


def format_task_list(
    tasks: list[dict[str, Any]] | str,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Format a task listing.

    Input: JSON array of task objects or string fallback.
    Output: ``- [x] task text (path:line)`` per line, capped at limit.
    """
    if isinstance(tasks, str):
        raw_lines = [line.strip() for line in tasks.strip().split("\n") if line.strip()]
        if not raw_lines:
            return "No tasks found."
        total = len(raw_lines)
        shown = raw_lines[:limit]
        if total > len(shown):
            shown.append(f"… {total - len(shown)} more tasks")
        return "\n".join(shown)

    if not tasks:
        return "No tasks found."

    total = len(tasks)
    visible = tasks[:limit]
    lines: list[str] = []
    for t in visible:
        status = t.get("status", "unchecked")
        checkbox = "[x]" if status in ("checked", "complete", "done") else "[ ]"
        text = t.get("text", t.get("content", "?"))
        location = ""
        task_path = t.get("path", "")
        task_line = t.get("line")
        if task_path and task_line is not None:
            location = f" ({task_path}:{task_line})"
        elif task_path:
            location = f" ({task_path})"
        lines.append(f"- {checkbox} {text}{location}")

    if total > len(visible):
        lines.append(f"… {total - len(visible)} more tasks")

    return "\n".join(lines)


def format_bookmark_list(
    bookmarks: list[dict[str, Any]] | str,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Format a bookmark listing.

    Input: JSON array of bookmark objects or string fallback.
    Output: ``type: title — path/query/url`` per line, capped at limit.
    """
    if isinstance(bookmarks, str):
        raw_lines = [line.strip() for line in bookmarks.strip().split("\n") if line.strip()]
        if not raw_lines:
            return "No bookmarks found."
        total = len(raw_lines)
        shown = raw_lines[:limit]
        if total > len(shown):
            shown.append(f"… {total - len(shown)} more bookmarks")
        return "\n".join(shown)

    if not bookmarks:
        return "No bookmarks found."

    total = len(bookmarks)
    visible = bookmarks[:limit]
    lines: list[str] = []
    for b in visible:
        bm_type = b.get("type", "file")
        title = b.get("title", b.get("name", ""))
        target = b.get("path") or b.get("query") or b.get("url") or ""
        if title and target:
            lines.append(f"{bm_type}: {title} — {target}")
        elif title:
            lines.append(f"{bm_type}: {title}")
        elif target:
            lines.append(f"{bm_type}: {target}")
        else:
            lines.append(f"{bm_type}: (untitled)")

    if total > len(visible):
        lines.append(f"… {total - len(visible)} more bookmarks")

    return "\n".join(lines)


def truncate_content(content: str, max_lines: int = 100) -> str:
    """Truncate long content with annotation."""
    lines = content.split("\n")
    if len(lines) <= max_lines:
        return content
    truncated = "\n".join(lines[:max_lines])
    return f"{truncated}\n\n… ({len(lines) - max_lines} more lines, use vault_read for full content)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _human_size(size_bytes: int | float) -> str:
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{int(size_bytes)} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _format_value(value: Any) -> str:
    """Format a property value for display."""
    if isinstance(value, list):
        return f"[{', '.join(str(v) for v in value)}]"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
