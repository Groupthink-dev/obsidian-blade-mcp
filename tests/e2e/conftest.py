"""E2E test fixtures — require a running Obsidian instance.

All E2E tests are gated on the ``OBSIDIAN_E2E=1`` environment variable.
They require Obsidian desktop to be running with an open vault and CLI enabled.
"""

from __future__ import annotations

import os
import uuid

import pytest

from obsidian_blade_mcp.client import ObsidianCLI, ObsidianCLIError


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    """Skip all E2E tests unless OBSIDIAN_E2E=1."""
    if os.environ.get("OBSIDIAN_E2E") != "1":
        skip_marker = pytest.mark.skip(reason="E2E tests require OBSIDIAN_E2E=1")
        for item in items:
            if "e2e" in str(item.fspath):
                item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def e2e_cli() -> ObsidianCLI:
    """Session-scoped CLI client — verifies Obsidian is running, fails fast if not."""
    cli = ObsidianCLI()
    try:
        info = cli.vault_info()
        assert info, "vault_info returned empty — is Obsidian running with a vault open?"
    except ObsidianCLIError as exc:
        pytest.fail(f"Obsidian CLI health check failed: {exc}")
    return cli


@pytest.fixture
def e2e_scratch_note(e2e_cli: ObsidianCLI) -> str:
    """Create a temporary note for testing; attempt cleanup on teardown.

    Yields the note name (without .md extension).
    """
    note_name = f"_e2e_test_{uuid.uuid4().hex[:8]}"
    e2e_cli.create(name=note_name, content="# E2E Test Note\n\nCreated by obsidian-blade-mcp E2E tests.", path="+/")
    yield note_name
    # Cleanup — best-effort delete via CLI if available
    try:
        e2e_cli.run("delete", params={"file": note_name}, flags=["silent"])
    except ObsidianCLIError:
        pass  # CLI may not support delete; note left in +/ for manual cleanup
