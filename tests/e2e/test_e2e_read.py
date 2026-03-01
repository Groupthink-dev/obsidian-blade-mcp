"""E2E tests for Phase 1 read operations against a real Obsidian vault."""

from __future__ import annotations

import pytest

from obsidian_blade_mcp.client import ObsidianCLI

pytestmark = pytest.mark.e2e


class TestVaultInfo:
    """Test vault_info against live Obsidian."""

    def test_vault_info_returns_data(self, e2e_cli: ObsidianCLI) -> None:
        info = e2e_cli.vault_info()
        assert info is not None
        # Should have vault name and path at minimum
        if isinstance(info, dict):
            assert "name" in info or "path" in info

    def test_vault_info_has_counts(self, e2e_cli: ObsidianCLI) -> None:
        info = e2e_cli.vault_info()
        if isinstance(info, dict):
            assert info.get("fileCount") or info.get("files") or info.get("noteCount")


class TestFiles:
    """Test files listing against live vault."""

    def test_files_returns_list(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.files(limit=5)
        items = result if isinstance(result, list) else result.strip().split("\n")
        assert len(items) > 0

    def test_files_with_folder(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.files(folder="atlas/", limit=5)
        items = result if isinstance(result, list) else result.strip().split("\n")
        assert len(items) > 0


class TestFolders:
    """Test folder listing against live vault."""

    def test_folders_returns_list(self, e2e_cli: ObsidianCLI) -> None:
        result = e2e_cli.folders()
        items = result if isinstance(result, list) else result.strip().split("\n")
        assert len(items) > 0


class TestRead:
    """Test reading notes from live vault."""

    def test_read_scratch_note(self, e2e_cli: ObsidianCLI, e2e_scratch_note: str) -> None:
        content = e2e_cli.read(file=e2e_scratch_note)
        assert "E2E Test Note" in content
