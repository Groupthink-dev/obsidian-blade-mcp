"""Tests for the ObsidianCLI subprocess wrapper."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from obsidian_blade_mcp.client import (
    ObsidianCLI,
    ObsidianCLIError,
    ObsidianFileNotFoundError,
    ObsidianNotFoundError,
    ObsidianNotRunningError,
    ObsidianTimeoutError,
    ObsidianVaultError,
)


class TestCLIInit:
    """Test ObsidianCLI initialization."""

    def test_init_with_explicit_path(self):
        cli = ObsidianCLI(cli_path="/usr/bin/obsidian", vault_name="my-vault")
        assert cli.cli_path == "/usr/bin/obsidian"
        assert cli.vault_name == "my-vault"

    @patch("obsidian_blade_mcp.client.shutil.which", return_value="/usr/local/bin/obsidian")
    def test_init_auto_detect(self, mock_which):
        cli = ObsidianCLI()
        assert cli.cli_path == "/usr/local/bin/obsidian"

    @patch("obsidian_blade_mcp.client.shutil.which", return_value=None)
    @patch("obsidian_blade_mcp.client.os.path.isfile", return_value=True)
    def test_init_macos_fallback(self, mock_isfile, mock_which):
        cli = ObsidianCLI()
        assert cli.cli_path == "/Applications/Obsidian.app/Contents/MacOS/obsidian"

    @patch("obsidian_blade_mcp.client.shutil.which", return_value=None)
    @patch("obsidian_blade_mcp.client.os.path.isfile", return_value=False)
    def test_init_not_found(self, mock_isfile, mock_which):
        with pytest.raises(ObsidianNotFoundError):
            ObsidianCLI()

    @patch.dict("os.environ", {"OBSIDIAN_VAULT_NAME": "env-vault"})
    def test_init_vault_from_env(self):
        cli = ObsidianCLI(cli_path="/usr/bin/obsidian")
        assert cli.vault_name == "env-vault"

    def test_init_vault_explicit_overrides_env(self):
        cli = ObsidianCLI(cli_path="/usr/bin/obsidian", vault_name="explicit")
        assert cli.vault_name == "explicit"


class TestBuildArgs:
    """Test argument building."""

    def test_simple_command(self, cli):
        args = cli._build_args("read")
        assert args == ["/usr/local/bin/obsidian", "vault=test-vault", "read"]

    def test_command_with_params(self, cli):
        args = cli._build_args("read", params={"file": "My Note"})
        assert "file=My Note" in args

    def test_command_with_numeric_param(self, cli):
        args = cli._build_args("files", params={"limit": 10})
        assert "limit=10" in args

    def test_command_with_bool_flag(self, cli):
        args = cli._build_args("create", params={"name": "Test"}, flags=["silent", "overwrite"])
        assert "silent" in args
        assert "overwrite" in args

    def test_command_with_none_params(self, cli):
        args = cli._build_args("read", params={"file": None, "path": "test.md"})
        assert "path=test.md" in args
        assert "file" not in " ".join(args)

    def test_no_vault(self):
        cli = ObsidianCLI(cli_path="/usr/bin/obsidian")
        cli.vault_name = None
        args = cli._build_args("vault")
        assert args == ["/usr/bin/obsidian", "vault"]

    def test_vault_override(self, cli):
        args = cli._build_args("read", vault="other-vault")
        assert "vault=other-vault" in args


class TestRun:
    """Test subprocess execution."""

    def test_successful_command(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("Hello world\n")
        result = cli.run("read", params={"file": "Test"})
        assert result == "Hello world\n"
        mock_subprocess.assert_called_once()

    def test_command_failure(self, cli, mock_subprocess, failed_result):
        mock_subprocess.return_value = failed_result(stderr="file not found")
        with pytest.raises(ObsidianFileNotFoundError):
            cli.run("read", params={"file": "Missing"})

    def test_not_running_error(self, cli, mock_subprocess, failed_result):
        mock_subprocess.return_value = failed_result(stderr="Obsidian is not running")
        with pytest.raises(ObsidianNotRunningError):
            cli.run("vault")

    def test_vault_error(self, cli, mock_subprocess, failed_result):
        mock_subprocess.return_value = failed_result(stderr="vault not found: bad-vault")
        with pytest.raises(ObsidianVaultError):
            cli.run("vault", vault="bad-vault")

    def test_timeout(self, cli, mock_subprocess):
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="obsidian", timeout=30)
        with pytest.raises(ObsidianTimeoutError):
            cli.run("read")

    def test_binary_not_found(self, cli, mock_subprocess):
        mock_subprocess.side_effect = FileNotFoundError()
        with pytest.raises(ObsidianNotFoundError):
            cli.run("vault")

    def test_generic_error(self, cli, mock_subprocess, failed_result):
        mock_subprocess.return_value = failed_result(stderr="something went wrong")
        with pytest.raises(ObsidianCLIError):
            cli.run("vault")


class TestRunJSON:
    """Test JSON output parsing."""

    def test_json_response(self, cli, mock_subprocess, successful_result):
        data = {"name": "test-vault", "path": "/tmp/vault"}
        mock_subprocess.return_value = successful_result(json.dumps(data))
        result = cli.run_json("vault")
        assert result == data

    def test_json_adds_format(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("{}")
        cli.run_json("vault")
        call_args = mock_subprocess.call_args[0][0]
        assert "format=json" in call_args

    def test_non_json_fallback(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("plain text output")
        result = cli.run_json("vault")
        assert result == "plain text output"


class TestConvenienceMethods:
    """Test convenience methods dispatch correctly."""

    def test_vault_info(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('{"name":"test"}')
        result = cli.vault_info()
        assert result == {"name": "test"}

    def test_read_by_file(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("# Hello\nContent here")
        result = cli.read(file="My Note")
        assert "Hello" in result

    def test_read_by_path(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("# Test")
        result = cli.read(path="folder/test.md")
        assert "Test" in result

    def test_create(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("")
        cli.create(name="New Note", content="# New\nBody")
        call_args = mock_subprocess.call_args[0][0]
        assert "create" in call_args
        assert "silent" in call_args

    def test_append(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("")
        cli.append(content="New line", file="Existing")
        call_args = mock_subprocess.call_args[0][0]
        assert "append" in call_args

    def test_prepend(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("")
        cli.prepend(content="Top line", file="Existing")
        call_args = mock_subprocess.call_args[0][0]
        assert "prepend" in call_args

    def test_files(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('[{"path":"a.md"}]')
        result = cli.files(limit=10)
        assert isinstance(result, list)

    def test_files_uses_folder_param(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('[{"path":"spaces/a.md"}]')
        cli.files(folder="spaces/")
        call_args = mock_subprocess.call_args[0][0]
        assert "folder=spaces/" in call_args
        assert "path=" not in " ".join(call_args)

    def test_files_ext_param(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('[{"path":"a.base"}]')
        cli.files(ext="base")
        call_args = mock_subprocess.call_args[0][0]
        assert "ext=base" in call_args

    def test_file_info(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('{"path":"a.md","size":100}')
        result = cli.file_info(file="A")
        assert result["size"] == 100

    def test_folders(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('["atlas/","spaces/"]')
        result = cli.folders()
        assert "atlas/" in result

    def test_recents(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('[{"path":"recent.md"}]')
        result = cli.recents(limit=5)
        assert isinstance(result, list)

    def test_property_read(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('{"value":"on"}')
        result = cli.property_read(name="status", file="Note")
        assert result["value"] == "on"

    def test_property_set(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("")
        cli.property_set(name="status", value="done", file="Note")
        call_args = mock_subprocess.call_args[0][0]
        assert "property:set" in call_args

    def test_property_remove(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("")
        cli.property_remove(name="old_field", file="Note")
        call_args = mock_subprocess.call_args[0][0]
        assert "property:remove" in call_args

    def test_properties(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('{"kind":"effort","status":"on"}')
        result = cli.properties(file="Note")
        assert result["kind"] == "effort"


class TestPhase2Methods:
    """Test Phase 2 convenience methods (search, tags, bases)."""

    def test_search(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('["atlas/cards/Docker.md","spaces/note.md"]')
        result = cli.search(query="Docker")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_search_does_not_pass_limit(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("[]")
        cli.search(query="test")
        call_args = mock_subprocess.call_args[0][0]
        assert not any(arg.startswith("limit=") for arg in call_args)

    def test_search_with_path(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("[]")
        cli.search(query="test", path="atlas/")
        call_args = mock_subprocess.call_args[0][0]
        assert "path=atlas/" in call_args

    def test_search_case_sensitive(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("[]")
        cli.search(query="Test", case_sensitive=True)
        call_args = mock_subprocess.call_args[0][0]
        assert "case-sensitive" in call_args

    def test_search_context(self, cli, mock_subprocess, successful_result):
        ctx_output = "atlas/cards/Docker.md:5: Docker is great\n"
        mock_subprocess.return_value = successful_result(ctx_output)
        result = cli.search_context(query="Docker")
        assert "Docker" in result
        assert isinstance(result, str)

    def test_search_context_does_not_pass_limit(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("")
        cli.search_context(query="test")
        call_args = mock_subprocess.call_args[0][0]
        assert not any(arg.startswith("limit=") for arg in call_args)

    def test_tags(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('[{"tag":"#IT/software","count":"5"}]')
        result = cli.tags()
        assert isinstance(result, list)
        assert result[0]["tag"] == "#IT/software"

    def test_tags_always_passes_counts(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("[]")
        cli.tags()
        call_args = mock_subprocess.call_args[0][0]
        assert "counts" in call_args

    def test_tags_sort_by_count(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("[]")
        cli.tags(sort_by_count=True)
        call_args = mock_subprocess.call_args[0][0]
        assert "sort" in call_args

    def test_tag(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("atlas/cards/Docker.md\nspaces/note.md")
        result = cli.tag(name="#IT/software")
        # run_json fallback to string
        assert "Docker" in result

    def test_bases(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("path/to/file.base\npath/to/other.base")
        result = cli.bases()
        assert "file.base" in result

    def test_base_views(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('["All","Phase 1"]')
        result = cli.base_views(file="My Base")
        assert isinstance(result, list)
        assert "All" in result

    def test_base_query_json(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result('[{"name":"Task 1","status":"done"}]')
        result = cli.base_query(path="file.base", output_format="json")
        assert isinstance(result, list)
        assert result[0]["name"] == "Task 1"

    def test_base_query_non_json(self, cli, mock_subprocess, successful_result):
        mock_subprocess.return_value = successful_result("| Name | Status |\n| Task 1 | done |")
        result = cli.base_query(path="file.base", output_format="md")
        assert "Task 1" in result
        assert isinstance(result, str)
