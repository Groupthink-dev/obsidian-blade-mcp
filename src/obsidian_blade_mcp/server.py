"""Obsidian Blade MCP Server — precision vault tools via subprocess.

Wraps the Obsidian CLI (v1.12+) as MCP tools. Token-efficient by default:
concise output, capped lists, null-field omission.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from obsidian_blade_mcp.client import ObsidianCLI, ObsidianCLIError
from obsidian_blade_mcp.formatters import (
    format_bookmark_list,
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
)
from obsidian_blade_mcp.lens import format_lens_results, get_lens_connection, heartbeat_warning
from obsidian_blade_mcp.models import DEFAULT_LIMIT

logger = logging.getLogger(__name__)


def _to_list(result: object) -> list[str]:
    """Convert CLI output to a list — handles both JSON lists and newline-delimited strings."""
    if isinstance(result, list):
        return result
    if isinstance(result, str):
        return [line for line in result.strip().split("\n") if line.strip()]
    return [str(result)]


# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------

TRANSPORT = os.environ.get("OBSIDIAN_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("OBSIDIAN_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("OBSIDIAN_MCP_PORT", "8766"))

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "ObsidianBlade",
    instructions=(
        "Obsidian vault operations via CLI. All tools target the vault set by OBSIDIAN_VAULT_NAME "
        "or the per-tool vault= parameter. Use vault_files with limit= to browse, vault_read for content, "
        "vault_search for finding notes. Property tools provide atomic frontmatter operations. "
        "Obsidian desktop must be running."
    ),
)

# Lazy-initialized client
_client: ObsidianCLI | None = None


def _get_client() -> ObsidianCLI:
    """Get or create the ObsidianCLI client singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = ObsidianCLI()
        logger.info("Obsidian CLI: binary=%s, vault=%s", _client.cli_path, _client.vault_name or "(default)")
    return _client


def _error_response(e: ObsidianCLIError) -> str:
    """Format a CLI error as a user-friendly string."""
    return f"Error: {e}"


async def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a blocking client method in a thread to avoid blocking the event loop.

    This is critical for MCP-over-stdio: if the event loop is blocked during a
    long subprocess timeout, the transport degrades and subsequent responses fail.
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


# ===========================================================================
# META TOOLS
# ===========================================================================


@mcp.tool
async def vault_info(
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Get vault metadata: name, path, file/note counts.

    Use this as a health check and to confirm which vault you're targeting.
    """
    try:
        result = await _run(_get_client().vault_info, vault=vault)
        return format_vault_info(result)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_info")
        return f"Error: {e}"


# ===========================================================================
# FILE READ TOOLS
# ===========================================================================


@mcp.tool
async def vault_read(
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root (e.g., 'folder/note.md')")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Read the full content of a note.

    Specify either ``file`` (name-based, like a wikilink) or ``path`` (exact path).
    Without either, reads the currently active note in Obsidian.
    """
    try:
        content: str = await _run(_get_client().read, file=file, path=path, vault=vault)
        return content
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_read")
        return f"Error: {e}"


# ===========================================================================
# FILE WRITE TOOLS
# ===========================================================================


@mcp.tool
async def vault_create(
    name: Annotated[str, Field(description="Note name (without .md extension)")],
    content: Annotated[str | None, Field(description="Note content (Markdown). Use \\n for newlines.")] = None,
    path: Annotated[str | None, Field(description="Folder path to create in (e.g., 'spaces/Systems/')")] = None,
    template: Annotated[str | None, Field(description="Template name to use")] = None,
    overwrite: Annotated[bool, Field(description="Overwrite if exists (default: false)")] = False,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Create a new note in the vault.

    The note is created silently (not opened in Obsidian).
    Specify ``path`` for subfolder placement. Use ``template`` to apply a vault template.
    """
    try:
        result = await _run(
            _get_client().create,
            name=name,
            content=content,
            path=path,
            template=template,
            overwrite=overwrite,
            vault=vault,
        )
        result_str = str(result).strip()
        return result_str if result_str else f"Created: {name}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_create")
        return f"Error: {e}"


@mcp.tool
async def vault_append(
    content: Annotated[str, Field(description="Content to append (Markdown). Use \\n for newlines.")],
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Append content to the end of a note.

    Safe for human-written notes — adds content without modifying existing body text.
    """
    try:
        result = await _run(_get_client().append, content=content, file=file, path=path, vault=vault)
        target = file or path or "active note"
        result_str = str(result).strip()
        return result_str if result_str else f"Appended to: {target}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_append")
        return f"Error: {e}"


@mcp.tool
async def vault_prepend(
    content: Annotated[str, Field(description="Content to prepend (Markdown). Use \\n for newlines.")],
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Prepend content to the beginning of a note (after frontmatter).

    Useful for adding headings or status blocks at the top of a note.
    """
    try:
        result = await _run(_get_client().prepend, content=content, file=file, path=path, vault=vault)
        target = file or path or "active note"
        result_str = str(result).strip()
        return result_str if result_str else f"Prepended to: {target}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_prepend")
        return f"Error: {e}"


# ===========================================================================
# DISCOVERY TOOLS
# ===========================================================================


@mcp.tool
async def vault_files(
    folder: Annotated[str | None, Field(description="Filter to a folder path (e.g., 'spaces/Systems/')")] = None,
    ext: Annotated[str | None, Field(description="Filter by file extension (e.g., 'md', 'canvas', 'base')")] = None,
    limit: Annotated[int, Field(description="Max files to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List files in the vault, optionally filtered to a folder or extension.

    Returns file paths sorted by modification time (most recent first).
    Use ``limit`` to control output size for token efficiency.
    """
    try:
        result = await _run(_get_client().files, folder=folder, ext=ext, limit=limit, vault=vault)
        return format_file_list(_to_list(result), limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_files")
        return f"Error: {e}"


@mcp.tool
async def vault_file_info(
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Get metadata for a specific file: size, timestamps, frontmatter summary.

    Use this before reading to check if the file exists and see its properties
    without loading full content.
    """
    try:
        result = await _run(_get_client().file_info, file=file, path=path, vault=vault)
        if isinstance(result, dict):
            return format_properties(result)
        return str(result)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_file_info")
        return f"Error: {e}"


@mcp.tool
async def vault_folders(
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List all folders in the vault.

    Useful for understanding vault structure and finding correct paths
    for file creation or listing.
    """
    try:
        result = await _run(_get_client().folders, vault=vault)
        return format_folder_list(_to_list(result))
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_folders")
        return f"Error: {e}"


@mcp.tool
async def vault_recents(
    limit: Annotated[int, Field(description="Max files to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List recently modified files.

    Sorted by modification time, most recent first. Useful for seeing
    what's been worked on recently.
    """
    try:
        result = await _run(_get_client().recents, limit=limit, vault=vault)
        return format_file_list(_to_list(result), limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_recents")
        return f"Error: {e}"


# ===========================================================================
# PROPERTY TOOLS — atomic frontmatter operations
# ===========================================================================


@mcp.tool
async def vault_property_read(
    name: Annotated[str, Field(description="Property name to read (e.g., 'status', 'kind', 'tags')")],
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Read a single frontmatter property value.

    Returns the raw value of the specified property. Use ``vault_properties``
    to see all properties at once.
    """
    try:
        result = await _run(_get_client().property_read, name=name, file=file, path=path, vault=vault)
        if isinstance(result, dict):
            value = result.get("value", result.get(name, result))
            return f"{name}: {value}"
        return f"{name}: {result}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_property_read")
        return f"Error: {e}"


@mcp.tool
async def vault_property_set(
    name: Annotated[str, Field(description="Property name to set (e.g., 'status', 'kind')")],
    value: Annotated[str, Field(description="Property value to set")],
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Set a frontmatter property to a value.

    Creates the property if it doesn't exist, updates it if it does.
    This is an atomic operation — safer than editing YAML frontmatter by hand.
    """
    try:
        result = await _run(_get_client().property_set, name=name, value=value, file=file, path=path, vault=vault)
        target = file or path or "active note"
        result_str = str(result).strip()
        return result_str if result_str else f"Set {name}={value} on {target}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_property_set")
        return f"Error: {e}"


@mcp.tool
async def vault_property_remove(
    name: Annotated[str, Field(description="Property name to remove")],
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Remove a frontmatter property entirely.

    Deletes the property key and value from the note's frontmatter.
    """
    try:
        result = await _run(_get_client().property_remove, name=name, file=file, path=path, vault=vault)
        target = file or path or "active note"
        result_str = str(result).strip()
        return result_str if result_str else f"Removed {name} from {target}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_property_remove")
        return f"Error: {e}"


@mcp.tool
async def vault_properties(
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List all frontmatter properties for a note.

    Returns all key-value pairs from the note's YAML frontmatter.
    More efficient than reading the full note when you only need metadata.
    """
    try:
        result = await _run(_get_client().properties, file=file, path=path, vault=vault)
        return format_properties(result)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_properties")
        return f"Error: {e}"


# ===========================================================================
# SEARCH TOOLS
# ===========================================================================


@mcp.tool
async def vault_search(
    query: Annotated[str, Field(description="Search query string")],
    path: Annotated[str | None, Field(description="Limit search to a folder path")] = None,
    case_sensitive: Annotated[bool, Field(description="Case-sensitive search (default: false)")] = False,
    limit: Annotated[int, Field(description="Max results to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Search vault for notes matching a query. Returns matching file paths.

    Use ``vault_search_context`` for matching lines with context.
    ``limit`` is applied client-side (the CLI's limit= is broken).
    """
    try:
        result = await _run(_get_client().search, query=query, path=path, case_sensitive=case_sensitive, vault=vault)
        return format_search_results(result, limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_search")
        return f"Error: {e}"


@mcp.tool
async def vault_search_context(
    query: Annotated[str, Field(description="Search query string")],
    path: Annotated[str | None, Field(description="Limit search to a folder path")] = None,
    case_sensitive: Annotated[bool, Field(description="Case-sensitive search (default: false)")] = False,
    limit: Annotated[int, Field(description="Max matching lines to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Search vault with matching context lines (path:line: text per match).

    More detailed than ``vault_search`` — shows where each match occurs.
    ``limit`` is applied client-side (the CLI's limit= is broken).
    """
    try:
        result = await _run(
            _get_client().search_context, query=query, path=path, case_sensitive=case_sensitive, vault=vault
        )
        return format_search_context(result, limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_search_context")
        return f"Error: {e}"


# ===========================================================================
# TAG TOOLS
# ===========================================================================


@mcp.tool
async def vault_tags(
    file: Annotated[str | None, Field(description="Note name to get tags for (all tags if omitted)")] = None,
    path: Annotated[str | None, Field(description="Filter tags to a folder path")] = None,
    sort_by_count: Annotated[bool, Field(description="Sort by usage count descending")] = False,
    limit: Annotated[int, Field(description="Max tags to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List tags in the vault (or for a specific file) with usage counts.

    Returns ``#tag (count)`` per line. Use ``sort_by_count=true`` to see
    most-used tags first.
    """
    try:
        result = await _run(_get_client().tags, file=file, path=path, sort_by_count=sort_by_count, vault=vault)
        return format_tag_list(result, limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_tags")
        return f"Error: {e}"


@mcp.tool
async def vault_tag(
    name: Annotated[str, Field(description="Tag name (with or without #, e.g., '#IT/software' or 'IT/software')")],
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List all files with a specific tag.

    Returns file paths, one per line.
    """
    try:
        result = await _run(_get_client().tag, name=name, vault=vault)
        return format_file_list(_to_list(result))
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_tag")
        return f"Error: {e}"


# ===========================================================================
# BASE TOOLS
# ===========================================================================


@mcp.tool
async def vault_bases(
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List all ``.base`` files in the vault.

    Base files are Obsidian's structured data views (tables, cards, etc.).
    """
    try:
        result = await _run(_get_client().bases, vault=vault)
        return format_file_list(_to_list(result))
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_bases")
        return f"Error: {e}"


@mcp.tool
async def vault_base_views(
    file: Annotated[str | None, Field(description="Base name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path to .base file")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List views in a base file.

    Note: The CLI requires the base to be the active (open) file in Obsidian.
    This limits utility for programmatic access — prefer ``vault_base_query``
    with a known view name instead.
    """
    try:
        result = await _run(_get_client().base_views, file=file, path=path, vault=vault)
        if isinstance(result, list):
            if not result:
                return "No views found."
            return "\n".join(str(v) for v in result)
        return str(result)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_base_views")
        return f"Error: {e}"


@mcp.tool
async def vault_base_query(
    file: Annotated[str | None, Field(description="Base name (wikilink resolution — may resolve to .md)")] = None,
    path: Annotated[str | None, Field(description="Exact path to .base file (preferred — use .base extension)")] = None,
    view: Annotated[str | None, Field(description="Named view within the base")] = None,
    output_format: Annotated[
        str, Field(description="Output format: json, md, csv, tsv, paths (default: json)")
    ] = "json",
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Query a base file for its structured data.

    Prefer ``path=`` with ``.base`` extension for reliable targeting (``file=``
    uses wikilink resolution which may resolve to ``.md`` instead).
    Use ``view=`` to select a specific named view.
    """
    try:
        result = await _run(
            _get_client().base_query,
            file=file,
            path=path,
            view=view,
            output_format=output_format,
            vault=vault,
        )
        if isinstance(result, str):
            return result.strip() if result.strip() else "No data returned."
        if isinstance(result, list):
            if not result:
                return "No data returned."
            # JSON output — format concisely
            import json

            return json.dumps(result, indent=2)
        if isinstance(result, dict):
            import json

            return json.dumps(result, indent=2)
        return str(result)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_base_query")
        return f"Error: {e}"


# ===========================================================================
# QUERY TOOLS — bulk frontmatter operations
# ===========================================================================


@mcp.tool
async def vault_query_properties(
    property: Annotated[str, Field(description="Frontmatter property to match (e.g. 'status', 'kind')")],
    value: Annotated[str, Field(description="Substring to match (case-insensitive, e.g. 'on')")],
    path: Annotated[str | None, Field(description="Restrict to folder path (e.g. 'spaces/')")] = None,
    fields: Annotated[
        str | None, Field(description="Comma-separated fields to return (e.g. 'kind,status,rank')")
    ] = None,
    limit: Annotated[int, Field(description="Max results (default: 50)")] = 50,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Query notes by frontmatter property, returning metadata without reading bodies.

    Returns one line per matching note: ``path | field1=val1 | field2=val2``.
    Sorted by ``rank`` descending when present. Use this instead of reading
    individual notes when you only need frontmatter summaries.

    Example: ``vault_query_properties(property="status", value="on", path="spaces/", fields="kind,status,rank")``
    returns all active efforts with their rank in a single call.
    """
    try:
        results = await _run(
            _get_client().query_properties,
            property=property,
            value=value,
            path=path,
            fields=fields,
            limit=limit,
            vault=vault,
        )
        if not results:
            return "No matching notes found."

        lines = []
        for entry in results:
            file_path = entry["file"]
            props = entry["properties"]
            prop_parts = [f"{k}={_format_prop_value(v)}" for k, v in props.items()]
            lines.append(f"{file_path} | {' | '.join(prop_parts)}")

        total_line = f"\n({len(results)} results)" if len(results) == limit else ""
        return "\n".join(lines) + total_line
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_query_properties")
        return f"Error: {e}"


def _format_prop_value(value: Any) -> str:
    """Format a property value for compact display."""
    if isinstance(value, list):
        return f"[{', '.join(str(v) for v in value)}]"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


# ===========================================================================
# SECTION TOOLS — heading-scoped read/write
# ===========================================================================


@mcp.tool
async def vault_section_read(
    path: Annotated[str, Field(description="Vault-relative path (e.g., 'atlas/note.md')")],
    heading: Annotated[str, Field(description="Heading text without # prefix (e.g., 'Current Focus')")],
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Read content under a specific heading.

    Returns the section body — all content from the heading until the next
    heading of the same or higher level. The heading line itself is not included.
    Operates directly on the filesystem (does not require Obsidian running).

    Use ``vault_outline`` first to discover heading names in a note.
    """
    try:
        result = await _run(_get_client().section_read, path=path, heading=heading, vault=vault)
        return result if result else f"(empty section: {heading})"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_section_read")
        return f"Error: {e}"


@mcp.tool
async def vault_section_replace(
    path: Annotated[str, Field(description="Vault-relative path (e.g., 'atlas/note.md')")],
    heading: Annotated[str, Field(description="Heading text without # prefix (e.g., 'Current Focus')")],
    content: Annotated[str, Field(description="Markdown content for the section (use \\n for newlines).")],
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Replace content under a specific heading, preserving the rest of the file.

    Finds the heading, removes the existing section body, and inserts ``content``
    in its place. The heading line and all content outside the section are preserved.
    Operates directly on the filesystem (does not require Obsidian running).

    Use ``vault_section_read`` to inspect the current section before replacing.
    """
    try:
        result = await _run(_get_client().section_replace, path=path, heading=heading, content=content, vault=vault)
        return str(result)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_section_replace")
        return f"Error: {e}"


# ===========================================================================
# LINK & STRUCTURE TOOLS
# ===========================================================================


@mcp.tool
async def vault_outline(
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Get the heading outline of a note.

    Returns an indented heading tree with line numbers. Use before ``vault_read``
    to understand note structure without loading full content.
    """
    try:
        result = await _run(_get_client().outline, file=file, path=path, vault=vault)
        return format_outline(result)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_outline")
        return f"Error: {e}"


@mcp.tool
async def vault_links(
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List outbound links from a note.

    Returns link targets (notes this note links to), one per line.
    """
    try:
        result = await _run(_get_client().links, file=file, path=path, vault=vault)
        return format_link_list(_to_list(result), label="links")
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_links")
        return f"Error: {e}"


@mcp.tool
async def vault_backlinks(
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List inbound links (backlinks) to a note.

    Returns source notes that link to this note, one per line.
    """
    try:
        result = await _run(_get_client().backlinks, file=file, path=path, vault=vault)
        return format_link_list(_to_list(result), label="backlinks")
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_backlinks")
        return f"Error: {e}"


@mcp.tool
async def vault_aliases(
    file: Annotated[str | None, Field(description="Note name (resolved like a wikilink)")] = None,
    path: Annotated[str | None, Field(description="Exact path from vault root")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List aliases for a note.

    Aliases are alternative names for a note used in wikilink resolution.
    """
    try:
        result = await _run(_get_client().aliases, file=file, path=path, vault=vault)
        return format_link_list(_to_list(result), label="aliases")
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_aliases")
        return f"Error: {e}"


@mcp.tool
async def vault_unresolved(
    path: Annotated[str | None, Field(description="Scope to a folder path")] = None,
    limit: Annotated[int, Field(description="Max results to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List unresolved (broken) links in the vault.

    Returns wikilinks that point to notes which don't exist.
    Use ``path=`` to scope to a folder. Large vaults may have thousands.
    """
    try:
        result = await _run(_get_client().unresolved, path=path, vault=vault)
        if isinstance(result, list):
            return format_link_list(result, limit=limit, label="unresolved links")
        return format_link_list(_to_list(result), limit=limit, label="unresolved links")
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_unresolved")
        return f"Error: {e}"


@mcp.tool
async def vault_orphans(
    path: Annotated[str | None, Field(description="Scope to a folder path")] = None,
    total_only: Annotated[
        bool, Field(description="Return count only (default: true — full list is ~12K items)")
    ] = True,
    limit: Annotated[int, Field(description="Max results for full list (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List orphan notes (no inbound links).

    Defaults to count-only (``total_only=true``) because the full list can be
    massive (~12K items). Use ``path=`` to scope before requesting full list.
    """
    try:
        result = await _run(_get_client().orphans, path=path, total_only=total_only, vault=vault)
        if total_only:
            count = str(result).strip()
            return f"Orphan notes: {count}"
        return format_file_list(_to_list(result), limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_orphans")
        return f"Error: {e}"


@mcp.tool
async def vault_deadends(
    path: Annotated[str | None, Field(description="Scope to a folder path")] = None,
    total_only: Annotated[
        bool, Field(description="Return count only (default: true — full list is ~12K items)")
    ] = True,
    limit: Annotated[int, Field(description="Max results for full list (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List dead-end notes (no outbound links).

    Defaults to count-only (``total_only=true``) because the full list can be
    massive (~12K items). Use ``path=`` to scope before requesting full list.
    """
    try:
        result = await _run(_get_client().deadends, path=path, total_only=total_only, vault=vault)
        if total_only:
            count = str(result).strip()
            return f"Dead-end notes: {count}"
        return format_file_list(_to_list(result), limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_deadends")
        return f"Error: {e}"


# ===========================================================================
# TASK TOOLS
# ===========================================================================


@mcp.tool
async def vault_tasks(
    file: Annotated[str | None, Field(description="Note name to scope tasks to")] = None,
    path: Annotated[str | None, Field(description="Exact path to scope tasks to")] = None,
    status: Annotated[str | None, Field(description="Filter by status: 'checked', 'unchecked'")] = None,
    limit: Annotated[int, Field(description="Max tasks to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List tasks (checkboxes) in the vault.

    Returns ``- [x] task text (path:line)`` per line. Use ``file=`` or ``path=``
    to scope to a specific note. Use ``status=`` to filter (e.g., ``unchecked``).
    """
    try:
        result = await _run(_get_client().tasks, file=file, path=path, status=status, vault=vault)
        return format_task_list(result, limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_tasks")
        return f"Error: {e}"


@mcp.tool
async def vault_task_update(
    ref: Annotated[str, Field(description="Task reference in path:line format (e.g., 'notes/Todo.md:5')")],
    action: Annotated[
        str, Field(description="Action: 'toggle', 'complete', or 'uncomplete' (default: toggle)")
    ] = "toggle",
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Toggle, complete, or uncomplete a task by reference.

    The ``ref`` is ``path:line`` from ``vault_tasks`` output. Use ``action=complete``
    to check, ``action=uncomplete`` to uncheck, or ``action=toggle`` to flip.
    """
    try:
        result = await _run(_get_client().task_update, ref=ref, action=action, vault=vault)
        result_str = str(result).strip()
        return result_str if result_str else f"Task updated: {ref} ({action})"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_task_update")
        return f"Error: {e}"


# ===========================================================================
# BOOKMARK TOOLS
# ===========================================================================


@mcp.tool
async def vault_bookmarks(
    limit: Annotated[int, Field(description="Max bookmarks to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List all bookmarks in the vault (files, folders, searches, URLs).

    Returns ``type: title — target`` per line.
    """
    try:
        result = await _run(_get_client().bookmarks, vault=vault)
        return format_bookmark_list(result, limit=limit)
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_bookmarks")
        return f"Error: {e}"


@mcp.tool
async def vault_bookmark_add(
    path: Annotated[str | None, Field(description="File or folder path to bookmark")] = None,
    search: Annotated[str | None, Field(description="Search query to bookmark")] = None,
    url: Annotated[str | None, Field(description="URL to bookmark")] = None,
    title: Annotated[str | None, Field(description="Display title for the bookmark")] = None,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Add a bookmark. Specify one of ``path=``, ``search=``, or ``url=``.

    Use ``title=`` to set a display name for the bookmark.
    """
    try:
        result = await _run(_get_client().bookmark_add, path=path, search=search, url=url, title=title, vault=vault)
        target = path or search or url or "bookmark"
        result_str = str(result).strip()
        return result_str if result_str else f"Bookmarked: {target}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_bookmark_add")
        return f"Error: {e}"


# ===========================================================================
# FILE OPERATION TOOLS
# ===========================================================================


@mcp.tool
async def vault_delete(
    path: Annotated[str, Field(description="Path to the file to delete (from vault root)")],
    permanent: Annotated[
        bool, Field(description="Permanently delete instead of moving to trash (IRREVERSIBLE, default: false)")
    ] = False,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Delete a file from the vault.

    By default, moves to the system trash (recoverable). Set ``permanent=true``
    to permanently delete — THIS IS IRREVERSIBLE.
    """
    try:
        result = await _run(_get_client().delete_file, path=path, permanent=permanent, vault=vault)
        action = "Permanently deleted" if permanent else "Deleted (moved to trash)"
        result_str = str(result).strip()
        return result_str if result_str else f"{action}: {path}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_delete")
        return f"Error: {e}"


@mcp.tool
async def vault_rename(
    path: Annotated[str, Field(description="Current file path (from vault root)")],
    new_name: Annotated[str, Field(description="New filename (without folder path)")],
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Rename a file. Obsidian updates all wikilinks automatically.

    Specify the current ``path`` and the ``new_name`` (just the filename, not the full path).
    """
    try:
        result = await _run(_get_client().rename, path=path, to=new_name, vault=vault)
        result_str = str(result).strip()
        return result_str if result_str else f"Renamed: {path} → {new_name}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_rename")
        return f"Error: {e}"


@mcp.tool
async def vault_move(
    path: Annotated[str, Field(description="Current file path (from vault root)")],
    destination: Annotated[str, Field(description="Destination folder path (e.g., 'spaces/Systems/')")],
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """Move a file to a new folder. Obsidian updates all wikilinks automatically.

    Specify the current ``path`` and the ``destination`` folder.
    """
    try:
        result = await _run(_get_client().move, path=path, to=destination, vault=vault)
        result_str = str(result).strip()
        return result_str if result_str else f"Moved: {path} → {destination}"
    except ObsidianCLIError as e:
        return _error_response(e)
    except Exception as e:
        logger.exception("Unexpected error in vault_move")
        return f"Error: {e}"


# ===========================================================================
# LENS TOOLS (obsidian-lens SQLite index)
# ===========================================================================


@mcp.tool
async def vault_lens_fts(
    query: Annotated[str, Field(description="FTS5 search query (supports AND, OR, NOT, phrase quotes)")],
    kind: Annotated[str | None, Field(description="Filter by frontmatter kind (e.g., 'effort', 'note')")] = None,
    status: Annotated[str | None, Field(description="Filter by frontmatter status (e.g., 'on', 'done')")] = None,
    folder: Annotated[str | None, Field(description="Filter by folder path substring")] = None,
    limit: Annotated[int, Field(description="Max results (default: 20)")] = DEFAULT_LIMIT,
) -> str:
    """BM25 keyword search over the vault index.

    Fast full-text search using SQLite FTS5. Supports boolean operators
    (AND, OR, NOT) and phrase queries ("exact phrase"). Use ``kind=``,
    ``status=``, ``folder=`` to narrow results. Returns ranked results
    with snippets.
    """
    try:
        conn = await _run(get_lens_connection)
        warning = await _run(heartbeat_warning, conn)

        from obsidian_lens.query import Filters, fts

        filters = Filters(kind=kind, status=status, folder=folder)
        results = await _run(fts, conn, query, filters=filters, limit=limit)
        return warning + format_lens_results(results, label="matches")
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in vault_lens_fts")
        return f"Error: {e}"


@mcp.tool
async def vault_lens_search(
    query: Annotated[str, Field(description="Natural language search query")],
    k: Annotated[int, Field(description="Number of results (default: 10)")] = 10,
    kind: Annotated[str | None, Field(description="Filter by frontmatter kind")] = None,
    status: Annotated[str | None, Field(description="Filter by frontmatter status")] = None,
) -> str:
    """Hybrid search combining keyword (BM25) and semantic (embedding) similarity.

    Uses Reciprocal Rank Fusion to merge FTS5 and vector search results.
    Best for natural language queries where you want both exact matches and
    semantically related notes. Requires embeddings to be indexed.
    """
    try:
        conn = await _run(get_lens_connection)
        warning = await _run(heartbeat_warning, conn)

        from obsidian_lens.query import Filters, hybrid

        filters = Filters(kind=kind, status=status)
        results = await _run(hybrid, conn, query, k=k, filters=filters)
        return warning + format_lens_results(results, label="results")
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in vault_lens_search")
        return f"Error: {e}"


@mcp.tool
async def vault_lens_related(
    path: Annotated[str, Field(description="Vault-relative path of the note (e.g., 'spaces/Systems/note.md')")],
    k: Annotated[int, Field(description="Number of similar notes (default: 10)")] = 10,
) -> str:
    """Find notes similar to a given note by embedding similarity.

    Returns notes ranked by semantic similarity, regardless of whether they
    are linked. Useful for discovering related content. Requires embeddings.
    """
    try:
        conn = await _run(get_lens_connection)
        warning = await _run(heartbeat_warning, conn)

        from obsidian_lens.query import related

        results = await _run(related, conn, path, k=k)
        return warning + format_lens_results(results, label="similar notes")
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in vault_lens_related")
        return f"Error: {e}"


@mcp.tool
async def vault_lens_connections(
    path: Annotated[str, Field(description="Vault-relative path of the starting note")],
    hops: Annotated[int, Field(description="Number of link hops to traverse (1-3, default: 1)")] = 1,
    direction: Annotated[
        str, Field(description="Link direction: 'outgoing', 'incoming', or 'both' (default: 'both')")
    ] = "both",
) -> str:
    """N-hop graph traversal from a note via the materialised wikilink graph.

    Returns all notes reachable within N hops, with direction and depth.
    Uses recursive CTE for efficient traversal. Max 3 hops.
    """
    try:
        conn = await _run(get_lens_connection)
        warning = await _run(heartbeat_warning, conn)

        from obsidian_lens.query import connections

        results = await _run(connections, conn, path, hops=hops, direction=direction)

        from obsidian_blade_mcp.lens import format_connections

        return warning + format_connections(results)
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in vault_lens_connections")
        return f"Error: {e}"


@mcp.tool
async def vault_lens_status() -> str:
    """Index health: note/link counts, kind distribution, daemon heartbeat.

    Use to verify the lens index is current before running search queries.
    """
    try:
        conn = await _run(get_lens_connection)

        from obsidian_lens.query import status_summary

        summary = await _run(status_summary, conn)

        lines: list[str] = [
            f"Notes: {summary['note_count']}",
            f"Links: {summary['link_count']}",
        ]

        if summary.get("kind_counts"):
            kinds = ", ".join(f"{k}={v}" for k, v in summary["kind_counts"].items())
            lines.append(f"Kinds: {kinds}")

        hb = summary.get("heartbeat")
        if hb:
            lines.append(
                f"Daemon: status={hb.get('status', '?')}, "
                f"last_beat={hb.get('last_beat', '?')}, pid={hb.get('pid', '?')}"
            )
        else:
            lines.append("Daemon: no heartbeat recorded")

        warning = await _run(heartbeat_warning, conn)
        return warning + "\n".join(lines)
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in vault_lens_status")
        return f"Error: {e}"


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Main entry point for the Obsidian Blade MCP server."""
    if TRANSPORT == "http":
        from starlette.middleware import Middleware

        from obsidian_blade_mcp.auth import BearerAuthMiddleware, get_bearer_token

        bearer = get_bearer_token()
        logger.info("Starting HTTP transport on %s:%s", HTTP_HOST, HTTP_PORT)
        if bearer:
            logger.info("Bearer token auth enabled (OBSIDIAN_MCP_API_TOKEN is set)")
        else:
            logger.info("Bearer token auth disabled (no OBSIDIAN_MCP_API_TOKEN)")
        mcp.run(
            transport="http",
            host=HTTP_HOST,
            port=HTTP_PORT,
            middleware=[Middleware(BearerAuthMiddleware)],
        )
    else:
        mcp.run()
