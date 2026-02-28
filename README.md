# Obsidian Blade MCP

Precision vault tools via the Obsidian CLI. Each MCP tool is a "blade" — the sharpest instrument for its vault operation.

Wraps the [Obsidian CLI](https://obsidian.md) (v1.12+) as an MCP server using [FastMCP 2.0](https://github.com/jlowin/fastmcp). The CLI communicates with the running Obsidian desktop app via IPC — Obsidian must be open.

## Features

- **13 Phase 1 tools**: read, write, append, prepend, files, folders, recents, properties
- **Token-efficient**: concise output, capped lists, null-field omission
- **Atomic property operations**: set/remove frontmatter without parsing YAML
- **Multi-vault**: target vaults via env var or per-tool override
- **HTTP transport**: bearer token auth for remote access via tunnels
- **SKILL.md**: self-teaching instructions for Claude

## Requirements

- macOS (tested) or Linux
- [Obsidian](https://obsidian.md) v1.12+ with CLI enabled (Settings → General)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Quick Start

```bash
# Install
cd obsidian-blade-mcp
uv sync

# Run (stdio transport)
uv run obsidian-blade-mcp

# Claude Code
claude mcp add obsidian-blade -- uv run --directory ~/code/obsidian-blade-mcp obsidian-blade-mcp

# Claude Desktop (claude_desktop_config.json)
{
  "mcpServers": {
    "obsidian-blade": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/obsidian-blade-mcp", "obsidian-blade-mcp"],
      "env": {
        "OBSIDIAN_VAULT_NAME": "my-vault"
      }
    }
  }
}
```

## Tools (Phase 1)

| Tool | Description |
|------|-------------|
| `vault_info` | Vault metadata (name, path, counts) |
| `vault_read` | Read note content |
| `vault_create` | Create a new note |
| `vault_append` | Append to a note |
| `vault_prepend` | Prepend to a note (after frontmatter) |
| `vault_files` | List files (with limit) |
| `vault_file_info` | File metadata |
| `vault_folders` | List all folders |
| `vault_recents` | Recently modified files |
| `vault_property_read` | Read a frontmatter property |
| `vault_property_set` | Set a frontmatter property |
| `vault_property_remove` | Remove a frontmatter property |
| `vault_properties` | List all properties |

## HTTP Transport

```bash
# Enable HTTP with bearer auth
export OBSIDIAN_MCP_TRANSPORT=http
export OBSIDIAN_MCP_HOST=127.0.0.1
export OBSIDIAN_MCP_PORT=8766
export OBSIDIAN_MCP_API_TOKEN=your-secret-token

uv run obsidian-blade-mcp
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSIDIAN_VAULT_NAME` | (none) | Default vault to target |
| `OBSIDIAN_CLI_PATH` | auto-detect | Path to obsidian binary |
| `OBSIDIAN_MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `http` |
| `OBSIDIAN_MCP_HOST` | `127.0.0.1` | HTTP bind host |
| `OBSIDIAN_MCP_PORT` | `8766` | HTTP bind port |
| `OBSIDIAN_MCP_API_TOKEN` | (none) | Bearer token for HTTP auth |

## Development

```bash
make install-dev    # Install with dev dependencies
make test           # Run unit tests
make check          # Lint + format + type-check
make run            # Start the server
```

## License

MIT
