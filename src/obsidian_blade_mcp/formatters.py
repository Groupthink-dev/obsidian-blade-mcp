"""Token-efficient output formatters for Obsidian vault data.

Design principles:
- Concise by default (one line per item)
- Null fields omitted
- Lists capped and annotated with total count
"""

from __future__ import annotations

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
    files: list[dict[str, Any] | str],
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
