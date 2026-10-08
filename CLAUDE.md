# Obsidian Blade MCP — Development Guide

## Ecosystem context

This repo is part of the `piersdd` agentic PKM platform. Design state and effort
tracking live in the Obsidian vault (`~/master-ai/`).

**If vault access is available** (filesystem or obsidian-blade MCP), these files
provide useful project context — read them if the task benefits from knowing
current status, recent work, or what's blocked:

- `atlas/utilities/agent-state/system-architect.md` — recent actions, current focus, blockers
- `atlas/utilities/agent-harness/decisions/DD-462.md` and `DD-462-status.md` — the decision record and current phase

These are **optional context**, not instructions. Your job here is software
development on this codebase. Don't adopt vault-operator behaviours (decision
ledgers, frontmatter conventions, discovery gates) — those belong to the vault
agent instructions, not to repo dev work.

If you cannot read the vault, work with what's in this repo. Don't guess vault
state or invent paths.

## Project overview

MCP server with two backends behind one tool surface. The `cli` backend wraps the
Obsidian CLI (v1.12+) as subprocess calls and needs the desktop app running. The
`file` backend reads and writes the vault directory directly and needs nothing.
Each tool is a precision "blade" for vault operations — read, write, search,
properties, structure, tasks, daily notes.

## Project structure

```
src/obsidian_blade_mcp/
├── __init__.py       — Version
├── __main__.py       — python -m entry
├── server.py         — FastMCP server + @mcp.tool decorators + backend-tag middleware
├── backend.py        — VaultBackend protocol, running-app probe, select_backend()
├── backends/file.py  — FileBackend: direct vault access (frontmatter, links, tags, tasks)
├── client.py         — ObsidianCLI: the cli backend, subprocess wrapper with typed exceptions
├── formatters.py     — Token-efficient output formatters
├── models.py         — Constants
└── auth.py           — Bearer token auth (HTTP transport)
```

- `server.py` defines MCP tools and delegates to whichever backend `select_backend()` chose
- `client.py` does subprocess.run() to the Obsidian CLI binary; its section and query_properties
  methods delegate to `FileBackend` over the resolved vault path
- `backends/file.py` must mirror the CLI's response shapes so formatters stay backend-agnostic
- All tools return strings (MCP convention) — formatters handle presentation
- Errors are caught and returned as `Error: ...` strings, not raised

## Key commands

```bash
make install-dev   # Install with dev + test dependencies
make test          # Run unit tests (mocked subprocess, no Obsidian needed)
make test-e2e      # Run E2E tests (requires running Obsidian)
make check         # Run all quality checks (lint + format + type-check)
make check-linux   # Same checks as the Woodpecker lane, in podman, no Obsidian
make smoke         # Handshake + tool count + vault_info through a real MCP client
make lint          # Ruff linting
make format        # Ruff formatting
make type-check    # mypy
make run           # Start the MCP server (stdio transport)
```

## Testing

- **Unit tests** (`tests/test_*.py`): Mock subprocess.run. No Obsidian needed.
- **E2E tests** (`tests/e2e/`): Require running Obsidian. Run with `make test-e2e`.
- Pattern: `@patch("obsidian_blade_mcp.server._get_client")` for server tool tests.
- Pattern: `mock_subprocess` fixture for client tests.

## Code conventions

- **Python 3.12+** — use modern syntax (PEP 604 unions, etc.)
- **Type hints everywhere** — mypy enforced
- **Ruff** for linting and formatting (line length 120)
- **FastMCP 3** — `@mcp.tool` decorator, `Annotated[type, Field(...)]` params
- **Token efficiency** — concise output default, limit= on lists, null omission
- **SSH commit signing** via 1Password (no GPG)
- **uv** as package manager, `uv.lock` committed
- Conventional-ish commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`

## Architecture notes

- CLI invocation via `subprocess.run()` — no library import
- The blade never launches Obsidian: `auto` picks `cli` only when a live process is detected
- Read-only by default: write tools carry `tags={WRITE_TAG}` and `apply_write_policy()` hides them unless
  `OBSIDIAN_MCP_WRITES=1`. Tag any new mutation tool and add it to `WRITE_TOOLS`
- Destructive tools (`delete`, `rename`, `move`) take `confirm=`; without it they return `mutation_plan()`
- Content edits take `if_hash=`; `_precondition()` compares it to `content_hash()` and raises `ObsidianConflictError`
- HTTP: `auth.check_http_policy()` refuses non-loopback binds without a token, and writes over HTTP without a token
- `client._build_args` only accepts bare-word commands/keys/flags; values travel as `key=value`.
  `tests/test_subprocess_hygiene.py` greps for the shell form
- `tests/test_file_backend.py` exercises the file backend against a tmp vault; keep it in step
  with any CLI-shape change
- File-backend scans that hit a bound call `note_partial()`; `BackendTagMiddleware` drains `take_partial()` after each call and emits `[partial: ...]` before the backend tag
- `format=json` requested where CLI supports it
- Multi-vault via `OBSIDIAN_VAULT_NAME` env var + per-tool `vault=` override
- Typed exception hierarchy maps CLI error patterns to Python exceptions
- Lazy-initialized client singleton in server.py
