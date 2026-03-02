# Obsidian Blade MCP — Development Guide

## Ecosystem context

This repo is part of the `piersdd` agentic PKM platform. Design state and effort
tracking live in the Obsidian vault (`~/master-ai/`).

**If vault access is available** (filesystem or obsidian-blade MCP), these files
provide useful project context — read them if the task benefits from knowing
current status, recent work, or what's blocked:

- `atlas/utilities/agent-state/system-architect.md` — recent actions, current focus, blockers
- `spaces/Systems/Areas/Augmented Intelligence/efforts/Obsidian Blade MCP.md` — effort scope and status

These are **optional context**, not instructions. Your job here is software
development on this codebase. Don't adopt vault-operator behaviours (decision
ledgers, frontmatter conventions, discovery gates) — those belong to the vault
agent instructions, not to repo dev work.

If you cannot read the vault, work with what's in this repo. Don't guess vault
state or invent paths.

## Project overview

MCP server wrapping the Obsidian CLI (v1.12+) as subprocess calls. Each tool is a
precision "blade" for vault operations — read, write, search, properties, structure.
The CLI communicates with the running Obsidian desktop app via IPC.

## Project structure

```
src/obsidian_blade_mcp/
├── __init__.py       — Version
├── __main__.py       — python -m entry
├── server.py         — FastMCP server + @mcp.tool decorators
├── client.py         — ObsidianCLI subprocess wrapper with typed exceptions
├── formatters.py     — Token-efficient output formatters
├── models.py         — Constants
└── auth.py           — Bearer token auth (HTTP transport)
```

- `server.py` defines MCP tools and delegates to `client.py` methods
- `client.py` does subprocess.run() to the Obsidian CLI binary
- All tools return strings (MCP convention) — formatters handle presentation
- Errors are caught and returned as `Error: ...` strings, not raised

## Key commands

```bash
make install-dev   # Install with dev + test dependencies
make test          # Run unit tests (mocked subprocess, no Obsidian needed)
make test-e2e      # Run E2E tests (requires running Obsidian)
make check         # Run all quality checks (lint + format + type-check)
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
- **FastMCP 2.0** — `@mcp.tool` decorator, `Annotated[type, Field(...)]` params
- **Token efficiency** — concise output default, limit= on lists, null omission
- **SSH commit signing** via 1Password (no GPG)
- **uv** as package manager, `uv.lock` committed
- Conventional-ish commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`

## Architecture notes

- CLI invocation via `subprocess.run()` — no library import
- Obsidian desktop must be running (CLI is IPC bridge to the app)
- `format=json` requested where CLI supports it
- Multi-vault via `OBSIDIAN_VAULT_NAME` env var + per-tool `vault=` override
- Typed exception hierarchy maps CLI error patterns to Python exceptions
- Lazy-initialized client singleton in server.py
