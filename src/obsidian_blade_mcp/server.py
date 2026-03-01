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
    format_file_list,
    format_folder_list,
    format_properties,
    format_vault_info,
    truncate_content,
)
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
        content = await _run(_get_client().read, file=file, path=path, vault=vault)
        return truncate_content(content)
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
    path: Annotated[str | None, Field(description="Filter to a folder path (e.g., 'spaces/Systems/')")] = None,
    limit: Annotated[int, Field(description="Max files to return (default: 20)")] = DEFAULT_LIMIT,
    vault: Annotated[str | None, Field(description="Vault name override")] = None,
) -> str:
    """List files in the vault, optionally filtered to a folder.

    Returns file paths sorted by modification time (most recent first).
    Use ``limit`` to control output size for token efficiency.
    """
    try:
        result = await _run(_get_client().files, path=path, limit=limit, vault=vault)
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
