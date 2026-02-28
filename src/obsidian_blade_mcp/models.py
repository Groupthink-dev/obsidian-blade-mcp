"""Shared constants and type definitions for Obsidian Blade MCP server."""

from __future__ import annotations

# Default limit for list operations (token efficiency)
DEFAULT_LIMIT = 20

# Obsidian CLI binary — auto-detected via PATH or explicit env var
DEFAULT_CLI_PATH = "obsidian"

# Default subprocess timeout in seconds
DEFAULT_TIMEOUT = 30

# File extensions considered notes
NOTE_EXTENSIONS = {".md", ".canvas", ".base"}

# CLI exit codes
EXIT_OK = 0
EXIT_ERROR = 1
