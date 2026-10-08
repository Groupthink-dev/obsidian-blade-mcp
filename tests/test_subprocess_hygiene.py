"""C5: the CLI backend only ever builds list-form argv with bare-word commands and ``key=value`` params."""

from __future__ import annotations

import pathlib
import re

import pytest

from obsidian_blade_mcp.client import ObsidianCLIError

CLIENT_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "obsidian_blade_mcp" / "client.py"
BACKEND_SRC = CLIENT_SRC.with_name("backend.py")


class TestSourceLint:
    def test_no_shell_true_anywhere(self):
        for src in (CLIENT_SRC, BACKEND_SRC):
            text = src.read_text()
            assert "shell=" not in text, f"{src.name} passes shell= to subprocess"
            assert "os.system(" not in text and "os.popen(" not in text

    def test_every_subprocess_call_is_list_form(self):
        text = CLIENT_SRC.read_text()
        calls = re.findall(r"subprocess\.run\(\s*\n?\s*([^\n,]+)", text)
        assert calls, "expected subprocess.run calls in client.py"
        for first_arg in calls:
            first_arg = first_arg.strip()
            assert first_arg.startswith("[") or first_arg in {"args", "script_args"}, first_arg


class TestArgv:
    def test_values_travel_as_key_equals_value(self, cli):
        args = cli._build_args("append", {"path": "a.md", "content": "- item\n--flag"})
        assert args[1:] == ["vault=test-vault", "append", "path=a.md", "content=- item\n--flag"]
        assert not any(a.startswith("-") for a in args[1:])

    @pytest.mark.parametrize("bad", ["-rf", "read\nrm", "read;ls", "Read", "", "re ad"])
    def test_unsafe_command_rejected(self, cli, bad):
        with pytest.raises(ObsidianCLIError, match="unsafe CLI command"):
            cli._build_args(bad)

    @pytest.mark.parametrize("bad", ["-x", "x\n", "a b"])
    def test_unsafe_parameter_key_rejected(self, cli, bad):
        with pytest.raises(ObsidianCLIError, match="unsafe CLI parameter"):
            cli._build_args("read", {bad: "v"})

    def test_unsafe_flag_rejected(self, cli):
        with pytest.raises(ObsidianCLIError, match="unsafe CLI flag"):
            cli._build_args("delete", {"path": "a.md"}, flags=["--permanent"])

    def test_nul_in_value_rejected(self, cli):
        with pytest.raises(ObsidianCLIError, match="NUL"):
            cli._build_args("read", {"path": "a\0b.md"})

    def test_generated_targets_use_path_param(self, cli, mock_subprocess, successful_result):
        """Mutations on generated targets name the file by exact ``path=``, never a wikilink guess."""
        mock_subprocess.return_value = successful_result(stdout="")
        cli.delete_file(path="notes/x.md")
        cli.rename(path="notes/x.md", to="y")
        cli.move(path="notes/x.md", to="archive")
        mutations = [c[0][0] for c in mock_subprocess.call_args_list if {"delete", "rename", "move"} & set(c[0][0])]
        assert len(mutations) == 3
        for argv in mutations:
            assert any(a.startswith("path=") for a in argv), argv
