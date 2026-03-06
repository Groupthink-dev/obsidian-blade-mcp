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
import platform
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
        self._env = self._build_subprocess_env()

    @staticmethod
    def _build_subprocess_env() -> dict[str, str]:
        """Build the environment dict for subprocess calls.

        The Obsidian CLI is an Electron app that locates the running instance
        via an IPC socket inside the user's per-session temp directory
        (``$TMPDIR``).  When launched by hosts that strip environment variables
        (e.g. Claude Desktop's ``disclaimer`` sandbox), ``TMPDIR`` may be
        missing, causing the CLI to hang indefinitely.

        On macOS we recover the correct value via ``getconf DARWIN_USER_TEMP_DIR``.
        """
        env = os.environ.copy()
        if not env.get("TMPDIR") and platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["getconf", "DARWIN_USER_TEMP_DIR"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                tmpdir = result.stdout.strip()
                if tmpdir:
                    env["TMPDIR"] = tmpdir
                    logger.info("Injected TMPDIR=%s for Electron IPC", tmpdir)
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                logger.warning("Could not determine TMPDIR via getconf")
        return env

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
            args.append(f"vault={effective_vault}")

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
                    args.append(f"{key}={value}")

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
        effective_timeout = timeout or self.timeout
        logger.debug("Running: %s", " ".join(args))

        # search/search:context only produce output on a TTY (CLI bug)
        if command in self._PTY_COMMANDS:
            return self._run_pty(args, effective_timeout)

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                stdin=subprocess.DEVNULL,
                env=self._env,
            )
        except FileNotFoundError as exc:
            raise ObsidianNotFoundError(f"Obsidian CLI not found at: {self.cli_path}", returncode=1) from exc
        except subprocess.TimeoutExpired as exc:
            raise ObsidianTimeoutError(
                f"Command timed out after {effective_timeout}s: {command}",
                returncode=1,
            ) from exc

        if result.returncode != 0:
            raise _classify_error(result.stderr or result.stdout, result.returncode)

        return result.stdout

    # Commands whose output only appears on a TTY (Obsidian CLI bug).
    _PTY_COMMANDS = frozenset({"search", "search:context", "unresolved"})

    def _run_pty(self, args: list[str], timeout: int) -> str:
        """Run a command via ``script(1)`` to force TTY output.

        The Obsidian CLI ``search`` and ``search:context`` commands only write
        to a TTY — ``subprocess.run`` with pipes gets empty stdout.  The CLI
        binary (Electron) forks internally, so even ``pty.openpty()`` on the
        parent process doesn't help.  ``script -q /dev/null`` forces a real
        controlling terminal around the child process tree.
        """
        script_args = ["script", "-q", "/dev/null"] + args
        logger.debug("Running (PTY): %s", " ".join(script_args))

        try:
            result = subprocess.run(
                script_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=self._env,
            )
        except FileNotFoundError as exc:
            raise ObsidianNotFoundError(f"Obsidian CLI not found at: {self.cli_path}", returncode=1) from exc
        except subprocess.TimeoutExpired as exc:
            raise ObsidianTimeoutError(
                f"Command timed out after {timeout}s",
                returncode=1,
            ) from exc

        # script(1) wraps output with \r\n and may prepend TTY control chars
        stdout = result.stdout.replace("\r\n", "\n").replace("\r", "\n")
        # Strip TTY noise: the CLI echoes ^D (0x5e 0x44) + backspaces (0x08)
        # that appear before the actual output
        while stdout and ord(stdout[0]) in (0x08, 0x00, 0x04):
            stdout = stdout[1:]
        # Strip literal "^D" prefix (the caret + D echo)
        if stdout.startswith("^D"):
            stdout = stdout[2:]
        # Strip any remaining leading backspaces
        while stdout and ord(stdout[0]) == 0x08:
            stdout = stdout[1:]

        if result.returncode != 0:
            raise _classify_error(stdout or result.stderr, result.returncode)

        return stdout

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

    def files(
        self, folder: str | None = None, ext: str | None = None, limit: int | None = None, vault: str | None = None
    ) -> Any:
        """List files in the vault.

        Args:
            folder: Filter to a folder path (CLI param is ``folder=``).
            ext: Filter by file extension (e.g., ``md``, ``canvas``).
            limit: Max results.
        """
        params: dict[str, Any] = {}
        if folder:
            params["folder"] = folder
        if ext:
            params["ext"] = ext
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
        """List recently modified files.

        Note: The CLI ignores ``limit=`` for ``recents``; truncation is applied
        client-side in the formatter.
        """
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

    # -------------------------------------------------------------------
    # Convenience methods for Phase 2 tools (search, tags, bases)
    # -------------------------------------------------------------------

    def search(
        self,
        query: str,
        path: str | None = None,
        case_sensitive: bool = False,
        vault: str | None = None,
    ) -> Any:
        """Search vault for notes matching a query.

        Returns a JSON array of matching file paths.

        Note: The CLI's ``limit=`` parameter is broken for ``search`` (returns
        zero results). Do NOT pass limit to the CLI — apply client-side
        truncation in the formatter instead.
        """
        params: dict[str, Any] = {"query": query}
        if path:
            params["path"] = path
        flags: list[str] = []
        if case_sensitive:
            flags.append("case-sensitive")
        return self.run_json("search", params, vault, flags)

    def search_context(
        self,
        query: str,
        path: str | None = None,
        case_sensitive: bool = False,
        vault: str | None = None,
    ) -> str:
        """Search vault with matching context lines.

        Returns text in ``path:line: matching text`` format (one line per match).
        Uses text format because it's more structured than JSON for this command.

        Note: The CLI's ``limit=`` parameter is broken for ``search:context``
        (returns zero results). Do NOT pass limit — truncate client-side.
        """
        params: dict[str, Any] = {"query": query}
        if path:
            params["path"] = path
        flags: list[str] = []
        if case_sensitive:
            flags.append("case-sensitive")
        return self.run("search:context", params, vault, flags)

    def tags(
        self,
        file: str | None = None,
        path: str | None = None,
        sort_by_count: bool = False,
        vault: str | None = None,
    ) -> Any:
        """List tags in the vault or for a specific file.

        Returns JSON array of ``{"tag": "#name", "count": "N"}`` objects.
        Always passes ``counts`` flag for usage data.
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        flags = ["counts"]
        if sort_by_count:
            flags.append("sort")
        return self.run_json("tags", params, vault, flags)

    def tag(self, name: str, verbose: bool = False, vault: str | None = None) -> Any:
        """List files with a specific tag.

        Returns newline-delimited file paths. ``run_json`` falls back to string
        because the CLI has no JSON support for this command.
        """
        params: dict[str, Any] = {"name": name}
        if verbose:
            params["verbose"] = True
        return self.run_json("tag", params, vault)

    def bases(self, vault: str | None = None) -> Any:
        """List all ``.base`` files in the vault.

        Returns newline-delimited paths. ``run_json`` falls back to string
        because the CLI has no JSON support for this command.
        """
        return self.run_json("bases", vault=vault)

    def base_views(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        """List views in a base file.

        Note: The CLI requires the base to be the active file in Obsidian.
        This limits utility for programmatic access.
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("base:views", params, vault)

    def base_query(
        self,
        file: str | None = None,
        path: str | None = None,
        view: str | None = None,
        output_format: str = "json",
        vault: str | None = None,
    ) -> Any:
        """Query a base file for its data.

        Args:
            file: Base name (wikilink resolution — resolves to .md, unreliable).
            path: Exact path with ``.base`` extension (preferred for reliable targeting).
            view: Named view within the base.
            output_format: Output format — ``json``, ``md``, ``csv``, ``tsv``, ``paths``.
        """
        params: dict[str, Any] = {"format": output_format}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        if view:
            params["view"] = view
        if output_format == "json":
            raw = self.run("base:query", params, vault)
            try:
                import json as _json

                return _json.loads(raw)
            except (ValueError, TypeError):
                return raw.strip()
        return self.run("base:query", params, vault)

    # -------------------------------------------------------------------
    # Convenience methods for Phase 3 tools (links & structure)
    # -------------------------------------------------------------------

    def outline(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        """Get the heading outline of a note.

        Returns a JSON array of ``{"level": N, "heading": "...", "line": N}`` objects.
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("outline", params, vault)

    def links(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        """Get outbound links from a note.

        Returns newline-delimited link targets. ``run_json`` falls back to string
        because the CLI has no JSON support for this command.
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("links", params, vault)

    def backlinks(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        """Get inbound links (backlinks) to a note.

        Returns newline-delimited source paths. ``run_json`` falls back to string
        because the CLI has no JSON support for this command.
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("backlinks", params, vault)

    def aliases(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        """Get aliases for a note.

        Returns newline-delimited aliases. ``run_json`` falls back to string
        because the CLI has no JSON support for this command.
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        return self.run_json("aliases", params, vault)

    def unresolved(self, path: str | None = None, vault: str | None = None) -> Any:
        """Get unresolved (broken) links in the vault.

        Returns a JSON array of ``{"link": "..."}`` objects. Uses PTY wrapper
        (Electron TTY bug). No server-side limit — truncate client-side.
        """
        params: dict[str, Any] = {}
        if path:
            params["path"] = path
        return self.run_json("unresolved", params, vault)

    def orphans(self, path: str | None = None, total_only: bool = True, vault: str | None = None) -> Any:
        """Get orphan notes (no inbound links).

        Args:
            path: Scope to a folder.
            total_only: If True, return just the count (default). The full list
                is ~12K items and would blow the context window.
        """
        params: dict[str, Any] = {}
        if path:
            params["path"] = path
        if total_only:
            return self.run("orphans", params, vault, flags=["total"])
        return self.run_json("orphans", params, vault)

    def deadends(self, path: str | None = None, total_only: bool = True, vault: str | None = None) -> Any:
        """Get dead-end notes (no outbound links).

        Args:
            path: Scope to a folder.
            total_only: If True, return just the count (default). The full list
                is ~12K items and would blow the context window.
        """
        params: dict[str, Any] = {}
        if path:
            params["path"] = path
        if total_only:
            return self.run("deadends", params, vault, flags=["total"])
        return self.run_json("deadends", params, vault)

    # -------------------------------------------------------------------
    # Convenience methods for Phase 4 tools (tasks, bookmarks, file ops)
    # -------------------------------------------------------------------

    def tasks(
        self,
        file: str | None = None,
        path: str | None = None,
        status: str | None = None,
        vault: str | None = None,
    ) -> Any:
        """List tasks (checkboxes) in the vault.

        Args:
            file: Note name to scope tasks to.
            path: Exact path to scope tasks to.
            status: Filter by status (e.g., ``checked``, ``unchecked``).
        """
        params: dict[str, Any] = {}
        if file:
            params["file"] = file
        if path:
            params["path"] = path
        if status:
            params["status"] = status
        return self.run_json("tasks", params, vault)

    def task_update(self, ref: str, action: str = "toggle", vault: str | None = None) -> str:
        """Toggle, complete, or uncomplete a task by reference.

        Args:
            ref: Task reference in ``path:line`` format.
            action: One of ``toggle``, ``complete``, ``uncomplete``.
        """
        params: dict[str, Any] = {"ref": ref}
        flags = [action]
        return self.run("task", params, vault, flags)

    def bookmarks(self, vault: str | None = None) -> Any:
        """List all bookmarks (files, folders, searches, URLs)."""
        return self.run_json("bookmarks", vault=vault)

    def bookmark_add(
        self,
        path: str | None = None,
        search: str | None = None,
        url: str | None = None,
        title: str | None = None,
        vault: str | None = None,
    ) -> str:
        """Add a bookmark.

        Args:
            path: File or folder path to bookmark.
            search: Search query to bookmark.
            url: URL to bookmark.
            title: Display title for the bookmark.
        """
        params: dict[str, Any] = {}
        if path:
            params["path"] = path
        if search:
            params["search"] = search
        if url:
            params["url"] = url
        if title:
            params["title"] = title
        return self.run("bookmark", params, vault)

    def delete_file(self, path: str, permanent: bool = False, vault: str | None = None) -> str:
        """Delete a file from the vault.

        Method named ``delete_file`` to avoid shadowing builtins.

        Args:
            path: Path to the file to delete.
            permanent: If True, permanently delete. Otherwise move to trash.
        """
        params: dict[str, Any] = {"path": path}
        flags = ["permanent"] if permanent else []
        return self.run("delete", params, vault, flags)

    def rename(self, path: str, to: str, vault: str | None = None) -> str:
        """Rename a file. Obsidian updates all wikilinks automatically.

        Args:
            path: Current file path.
            to: New name (not full path — just the new filename).
        """
        params: dict[str, Any] = {"path": path, "to": to}
        return self.run("rename", params, vault)

    def move(self, path: str, to: str, vault: str | None = None) -> str:
        """Move a file to a new folder. Obsidian updates all wikilinks automatically.

        Args:
            path: Current file path.
            to: Destination folder path.
        """
        params: dict[str, Any] = {"path": path, "to": to}
        return self.run("move", params, vault)
