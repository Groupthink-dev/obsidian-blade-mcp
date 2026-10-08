"""Backend protocol and selection.

Two backends serve the same tool surface:

* ``cli`` — wraps the Obsidian CLI (``client.ObsidianCLI``). Needs the desktop
  app running. Gives Obsidian's own index: search, Bases, tasks, link graph.
* ``file`` — reads and writes the vault directory directly
  (``backends.file.FileBackend``). Works with the app closed, or on a host
  with no Obsidian install at all.

Selection (``select_backend``) never launches the app. The CLI launches the
GUI when it is not already running, so ``auto`` only picks ``cli`` when a live
process is detected *and* the binary is on PATH.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from typing import Any, Protocol

from obsidian_blade_mcp.client import ObsidianCLIError
from obsidian_blade_mcp.models import DEFAULT_CLI_PATH

logger = logging.getLogger(__name__)

BACKEND_ENV = "OBSIDIAN_MCP_BACKEND"
VAULT_PATH_ENV = "OBSIDIAN_VAULT_PATH"


class BackendUnsupportedError(ObsidianCLIError):
    """The selected backend cannot serve this operation.

    Subclasses ``ObsidianCLIError`` so every tool's existing error path
    renders it as ``Error: ...`` without special casing.
    """

    def __init__(self, operation: str, backend: str, needs: str = "cli") -> None:
        super().__init__(
            f"backend_unsupported: {operation} is not available on the {backend} backend; "
            f"it needs the {needs} backend (Obsidian running with the CLI enabled).",
            returncode=1,
        )
        self.operation = operation
        self.backend = backend
        self.needs = needs


class VaultBackend(Protocol):
    """Everything ``server.py`` calls. Both backends implement this surface."""

    name: str

    # F1 discovery
    def vault_info(self, vault: str | None = None) -> Any: ...
    def files(
        self, folder: str | None = None, ext: str | None = None, limit: int | None = None, vault: str | None = None
    ) -> Any: ...
    def file_info(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any: ...
    def folders(self, vault: str | None = None) -> Any: ...
    def recents(self, limit: int | None = None, vault: str | None = None) -> Any: ...

    # F2 content
    def read(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> str: ...
    def create(
        self,
        name: str,
        content: str | None = None,
        path: str | None = None,
        template: str | None = None,
        vault: str | None = None,
        overwrite: bool = False,
        silent: bool = True,
    ) -> str: ...
    def append(
        self, content: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> str: ...
    def prepend(
        self, content: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> str: ...
    def outline(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any: ...
    def section_read(self, path: str, heading: str, vault: str | None = None) -> str: ...
    def section_replace(self, path: str, heading: str, content: str, vault: str | None = None) -> str: ...
    def delete_file(self, path: str, permanent: bool = False, vault: str | None = None) -> str: ...
    def rename(self, path: str, to: str, vault: str | None = None) -> str: ...
    def move(self, path: str, to: str, vault: str | None = None) -> str: ...

    # F3 properties
    def property_read(
        self, name: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> Any: ...
    def property_set(
        self, name: str, value: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> str: ...
    def property_remove(
        self, name: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> str: ...
    def properties(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any: ...
    def query_properties(
        self,
        property: str,
        value: str,
        path: str | None = None,
        fields: str | None = None,
        limit: int = 50,
        vault: str | None = None,
    ) -> list[dict[str, Any]]: ...

    # F4 search
    def search(
        self, query: str, path: str | None = None, case_sensitive: bool = False, vault: str | None = None
    ) -> Any: ...
    def search_context(
        self, query: str, path: str | None = None, case_sensitive: bool = False, vault: str | None = None
    ) -> str: ...

    # F5 graph and tags
    def tags(
        self, file: str | None = None, path: str | None = None, sort_by_count: bool = False, vault: str | None = None
    ) -> Any: ...
    def tag(self, name: str, verbose: bool = False, vault: str | None = None) -> Any: ...
    def links(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any: ...
    def backlinks(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any: ...
    def aliases(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any: ...
    def unresolved(self, path: str | None = None, vault: str | None = None) -> Any: ...
    def orphans(self, path: str | None = None, total_only: bool = True, vault: str | None = None) -> Any: ...
    def deadends(self, path: str | None = None, total_only: bool = True, vault: str | None = None) -> Any: ...

    # F6 bases (cli only beyond listing)
    def bases(self, vault: str | None = None) -> Any: ...
    def base_views(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any: ...
    def base_query(
        self,
        file: str | None = None,
        path: str | None = None,
        view: str | None = None,
        output_format: str = "json",
        vault: str | None = None,
    ) -> Any: ...

    # F7 tasks and bookmarks
    def tasks(
        self, file: str | None = None, path: str | None = None, status: str | None = None, vault: str | None = None
    ) -> Any: ...
    def task_update(self, ref: str, action: str = "toggle", vault: str | None = None) -> str: ...
    def bookmarks(self, vault: str | None = None) -> Any: ...
    def bookmark_add(
        self,
        path: str | None = None,
        search: str | None = None,
        url: str | None = None,
        title: str | None = None,
        vault: str | None = None,
    ) -> str: ...

    # F8 daily notes and templates
    def daily_read(self, vault: str | None = None) -> str: ...
    def daily_append(self, content: str, vault: str | None = None) -> str: ...
    def template_read(self, name: str, vault: str | None = None) -> str: ...


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

_PROCESS_NAMES = {
    "Darwin": ("Obsidian",),
    "Linux": ("obsidian", "Obsidian"),
}


def obsidian_is_running() -> bool:
    """Return True when a live Obsidian desktop process is detected.

    Uses ``pgrep -x`` (exact process name) so the blade's own process name
    (``obsidian-blade-mcp``) never matches. Returns False on any failure:
    a false negative only costs the CLI's richer index, a false positive
    would launch the GUI.
    """
    names = _PROCESS_NAMES.get(platform.system(), ())
    if not names or shutil.which("pgrep") is None:
        return False
    for name in names:
        try:
            result = subprocess.run(
                ["pgrep", "-x", name],
                capture_output=True,
                text=True,
                timeout=3,
                stdin=subprocess.DEVNULL,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        if result.returncode == 0 and result.stdout.strip():
            return True
    return False


def cli_is_installed() -> bool:
    """Return True when the Obsidian CLI binary can be located without running it."""
    if os.environ.get("OBSIDIAN_CLI_PATH"):
        return os.path.isfile(os.environ["OBSIDIAN_CLI_PATH"])
    if shutil.which(DEFAULT_CLI_PATH):
        return True
    return os.path.isfile("/Applications/Obsidian.app/Contents/MacOS/obsidian")


def select_backend() -> VaultBackend:
    """Pick the backend for this process.

    ``OBSIDIAN_MCP_BACKEND``:
        ``auto`` (default) — ``cli`` if Obsidian is running and the CLI is
        installed, else ``file`` if ``OBSIDIAN_VAULT_PATH`` is a directory.
        ``cli`` — force the CLI backend (still never launches the app here;
        the first tool call will, which is the user's explicit choice).
        ``file`` — force the file backend.

    Raises:
        ObsidianCLIError: when nothing can serve the vault.
    """
    mode = os.environ.get(BACKEND_ENV, "auto").strip().lower() or "auto"
    vault_path = os.environ.get(VAULT_PATH_ENV, "").strip()
    vault_dir_ok = bool(vault_path) and os.path.isdir(vault_path)

    if mode == "cli":
        return _cli_backend()
    if mode == "file":
        if not vault_dir_ok:
            raise ObsidianCLIError(
                f"{BACKEND_ENV}=file needs {VAULT_PATH_ENV} to point at the vault directory.",
                returncode=1,
            )
        return _file_backend(vault_path)
    if mode != "auto":
        raise ObsidianCLIError(f"Unknown {BACKEND_ENV}={mode!r}; use auto, cli or file.", returncode=1)

    if obsidian_is_running() and cli_is_installed():
        logger.info("backend=cli (Obsidian running, CLI installed)")
        return _cli_backend()
    if vault_dir_ok:
        logger.info("backend=file (%s)", vault_path)
        return _file_backend(vault_path)
    raise ObsidianCLIError(
        "No backend available: Obsidian is not running (or the CLI is not installed) and "
        f"{VAULT_PATH_ENV} is not set to a vault directory. Set {VAULT_PATH_ENV} for app-free access.",
        returncode=1,
    )


def _cli_backend() -> VaultBackend:
    from obsidian_blade_mcp.client import ObsidianCLI

    return ObsidianCLI()


def _file_backend(vault_path: str) -> VaultBackend:
    from obsidian_blade_mcp.backends.file import FileBackend

    return FileBackend(vault_path)
