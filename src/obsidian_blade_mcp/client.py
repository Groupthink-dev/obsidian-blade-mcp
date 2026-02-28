"""Obsidian CLI subprocess wrapper.

Wraps the Obsidian CLI (v1.12+) as a subprocess, providing typed Python access
to vault operations. The CLI communicates with the running Obsidian desktop app
via IPC — Obsidian must be open for commands to work.

All commands request ``format=json`` where supported for structured output.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any

from obsidian_blade_mcp.models import DEFAULT_CLI_PATH, DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ObsidianCLIError(Exception):
    """Base exception for Obsidian CLI errors."""

    def __init__(self, message: str, returncode: int = 1, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class ObsidianNotRunningError(ObsidianCLIError):
    """Obsidian desktop app is not running."""


class ObsidianNotFoundError(ObsidianCLIError):
    """Obsidian CLI binary not found on PATH."""


class ObsidianVaultError(ObsidianCLIError):
    """Vault not found or not accessible."""


class ObsidianFileNotFoundError(ObsidianCLIError):
    """Requested file does not exist in the vault."""


class ObsidianTimeoutError(ObsidianCLIError):
    """CLI command timed out."""


# ---------------------------------------------------------------------------
# Error message patterns → exception mapping
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: list[tuple[str, type[ObsidianCLIError]]] = [
    ("is not running", ObsidianNotRunningError),
    ("not running", ObsidianNotRunningError),
    ("could not connect", ObsidianNotRunningError),
    ("vault not found", ObsidianVaultError),
    ("no vault", ObsidianVaultError),
    ("file not found", ObsidianFileNotFoundError),
    ("does not exist", ObsidianFileNotFoundError),
    ("not found", ObsidianFileNotFoundError),
]


def _classify_error(stderr: str, returncode: int) -> ObsidianCLIError:
    """Map CLI error output to a typed exception."""
    lower = stderr.lower()
    for pattern, exc_cls in _ERROR_PATTERNS:
        if pattern in lower:
            return exc_cls(stderr.strip(), returncode=returncode, stderr=stderr)
    return ObsidianCLIError(stderr.strip(), returncode=returncode, stderr=stderr)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ObsidianCLI:
    """Subprocess wrapper for the Obsidian CLI.

    Args:
        vault_name: Default vault to target. Overridden by per-call ``vault`` param.
        cli_path: Path to the ``obsidian`` binary. Defaults to ``OBSIDIAN_CLI_PATH``
            env var, then auto-detection via ``shutil.which``.
        timeout: Default subprocess timeout in seconds.
    """

    def __init__(
        self,
        vault_name: str | None = None,
        cli_path: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.vault_name = vault_name or os.environ.get("OBSIDIAN_VAULT_NAME")
        self.cli_path = cli_path or os.environ.get("OBSIDIAN_CLI_PATH") or self._find_cli()
        self.timeout = timeout

    @staticmethod
    def _find_cli() -> str:
        """Locate the Obsidian CLI binary."""
        found = shutil.which(DEFAULT_CLI_PATH)
        if found:
            return found
        # macOS app bundle fallback
        app_path = "/Applications/Obsidian.app/Contents/MacOS/obsidian"
        if os.path.isfile(app_path):
            return app_path
        raise ObsidianNotFoundError(
            "Obsidian CLI not found. Ensure Obsidian v1.12+ is installed and CLI is enabled "
            "at Settings → General, or set OBSIDIAN_CLI_PATH.",
            returncode=1,
        )

    def _build_args(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        vault: str | None = None,
        flags: list[str] | None = None,
    ) -> list[str]:
        """Build the subprocess argument list.

        Args:
            command: CLI command (e.g., ``read``, ``search``, ``property:set``).
            params: Key-value parameters (e.g., ``{"file": "My Note", "limit": 10}``).
            vault: Vault override (uses instance default if None).
            flags: Boolean flags (e.g., ``["silent", "total"]``).
        """
        args = [self.cli_path]

        # Vault targeting — must come first
        effective_vault = vault or self.vault_name
        if effective_vault:
            args.append(f'vault="{effective_vault}"')

        # Command
        args.append(command)

        # Parameters
        if params:
            for key, value in params.items():
                if value is None:
                    continue
                if isinstance(value, bool):
                    if value:
                        args.append(key)
                elif isinstance(value, (int, float)):
                    args.append(f"{key}={value}")
                else:
                    args.append(f'{key}="{value}"')

        # Flags
        if flags:
            for flag in flags:
                args.append(flag)

        return args

    def run(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        vault: str | None = None,
        flags: list[str] | None = None,
        timeout: int | None = None,
    ) -> str:
        """Execute an Obsidian CLI command and return stdout.

        Args:
            command: CLI command name.
            params: Key-value parameters.
            vault: Vault name override.
            flags: Boolean flags.
            timeout: Override default timeout.

        Returns:
            Raw stdout string from the CLI.

        Raises:
            ObsidianCLIError: On non-zero exit code (subclassed by error type).
            ObsidianTimeoutError: On subprocess timeout.
            ObsidianNotFoundError: If the CLI binary is missing.
        """
        args = self._build_args(command, params, vault, flags)
        logger.debug("Running: %s", " ".join(args))

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
            )
        except FileNotFoundError as exc:
            raise ObsidianNotFoundError(f"Obsidian CLI not found at: {self.cli_path}", returncode=1) from exc
        except subprocess.TimeoutExpired as exc:
            raise ObsidianTimeoutError(
                f"Command timed out after {timeout or self.timeout}s: {command}",
                returncode=1,
            ) from exc

        if result.returncode != 0:
            raise _classify_error(result.stderr or result.stdout, result.returncode)

        return result.stdout

    def run_json(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        vault: str | None = None,
        flags: list[str] | None = None,
        timeout: int | None = None,
    ) -> Any:
        """Execute a CLI command and parse JSON output.

        Automatically adds ``format=json`` to params.
        """
        params = dict(params) if params else {}
        params.setdefault("format", "json")
        raw = self.run(command, params, vault, flags, timeout)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Some commands return non-JSON even with format=json
            return raw.strip()

    # -------------------------------------------------------------------
    # Convenience methods for Phase 1 tools
    # -------------------------------------------------------------------

    def vault_info(self, vault: str | None = None) -> Any:
        """Get vault metadata."""
        return self.run_json("vault", vault=vault)

    def read(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> str:
        """Read a note's content.

        Args:
            file: Note name (resolved like a wikilink).
            path: Exact path from vault root.
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run("read", params, vault)

    def create(
        self,
        name: str,
        content: str | None = None,
        path: str | None = None,
        template: str | None = None,
        vault: str | None = None,
        overwrite: bool = False,
        silent: bool = True,
    ) -> str:
        """Create a new note."""
        params: dict[str, Any] = {"name": name}
        if content is not None:
            params["content"] = content
        if path is not None:
            params["path"] = path
        if template is not None:
            params["template"] = template
        flags = []
        if overwrite:
            flags.append("overwrite")
        if silent:
            flags.append("silent")
        return self.run("create", params, vault, flags)

    def append(self, content: str, file: str | None = None, path: str | None = None, vault: str | None = None) -> str:
        """Append content to a note."""
        params: dict[str, Any] = {"content": content}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run("append", params, vault)

    def prepend(self, content: str, file: str | None = None, path: str | None = None, vault: str | None = None) -> str:
        """Prepend content to a note."""
        params: dict[str, Any] = {"content": content}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run("prepend", params, vault)

    def files(self, path: str | None = None, limit: int | None = None, vault: str | None = None) -> Any:
        """List files in the vault."""
        params: dict[str, Any] = {}
        if path:
            params["path"] = path
        if limit:
            params["limit"] = limit
        return self.run_json("files", params, vault)

    def file_info(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        """Get metadata for a specific file."""
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("file", params, vault)

    def folders(self, vault: str | None = None) -> Any:
        """List folders in the vault."""
        return self.run_json("folders", vault=vault)

    def recents(self, limit: int | None = None, vault: str | None = None) -> Any:
        """List recently modified files."""
        params: dict[str, Any] = {}
        if limit:
            params["limit"] = limit
        return self.run_json("recents", params, vault)

    def property_read(
        self, name: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> Any:
        """Read a frontmatter property value."""
        params: dict[str, Any] = {"name": name}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("property:read", params, vault)

    def property_set(
        self,
        name: str,
        value: str,
        file: str | None = None,
        path: str | None = None,
        vault: str | None = None,
    ) -> str:
        """Set a frontmatter property."""
        params: dict[str, Any] = {"name": name, "value": value}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run("property:set", params, vault)

    def property_remove(
        self, name: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> str:
        """Remove a frontmatter property."""
        params: dict[str, Any] = {"name": name}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run("property:remove", params, vault)

    def properties(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        """List all frontmatter properties for a note."""
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("properties", params, vault)
