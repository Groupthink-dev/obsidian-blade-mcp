# Obsidian Blade MCP

Precision vault tools for any MCP client. Each tool is a "blade" — the sharpest instrument for its vault operation.

Two backends behind one 40-tool surface, built on [FastMCP](https://github.com/jlowin/fastmcp):

| Backend | When | What you get |
|---|---|---|
| **cli** | Obsidian desktop is running with the [CLI](https://obsidian.md/help/cli) enabled (v1.12+) | Obsidian's own index: search, Bases, tasks, link graph, templates, daily notes |
| **file** | Obsidian is closed, or the host has no Obsidian at all (a Linux server, a CI box) | Direct vault access from `OBSIDIAN_VAULT_PATH`: everything except Bases queries and bookmark creation |

The backend is selected once per process and the blade **never launches Obsidian**. Every response ends with `[backend: cli]` or `[backend: file]`.

## Features

- **40 tools**: read, write, search, properties, sections, link graph, tags, tasks, bookmarks, Bases, daily notes, templates
- **Works without the app**: the file backend parses Markdown, YAML frontmatter, wikilinks, `#tags` and `- [ ]` tasks deterministically. No embeddings, no inference, no network.
- **Token-efficient**: concise output, capped lists, null-field omission
- **Atomic property operations**: set/remove frontmatter without hand-editing YAML
- **Safe writes on the file backend**: atomic temp-and-rename, trash instead of delete, path containment (no `..`, no symlink escapes, no `.obsidian/` writes)
- **Multi-vault**: target vaults via env var or per-tool override
- **HTTP transport**: bearer token auth for remote access via tunnels
- **SKILL.md**: self-teaching instructions for Claude

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- For the `cli` backend: [Obsidian](https://obsidian.md) v1.12+ with CLI enabled (Settings → General), on macOS or Linux
- For the `file` backend: a vault directory. On a server, [Obsidian Headless](https://obsidian.md/help/headless) (`ob sync --continuous`) keeps it current if you use Obsidian Sync.

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

## Tools

| Family | Tools | file backend |
|---|---|---|
| Discovery | `vault_info` `vault_files` `vault_file_info` `vault_folders` `vault_recents` | yes |
| Content | `vault_read` `vault_create` `vault_append` `vault_prepend` `vault_outline` `vault_section_read` `vault_section_replace` `vault_delete` `vault_rename` `vault_move` | yes |
| Properties | `vault_property_read` `vault_property_set` `vault_property_remove` `vault_properties` `vault_query_properties` | yes |
| Search | `vault_search` `vault_search_context` | yes (literal, bounded) |
| Graph and tags | `vault_links` `vault_backlinks` `vault_aliases` `vault_unresolved` `vault_orphans` `vault_deadends` `vault_tags` `vault_tag` | yes |
| Bases | `vault_bases` `vault_base_views` `vault_base_query` | listing only |
| Tasks and bookmarks | `vault_tasks` `vault_task_update` `vault_bookmarks` `vault_bookmark_add` | all but `bookmark_add` |
| Daily and templates | `vault_daily_read` `vault_daily_append` `vault_template_read` | yes |

Unsupported operations return `Error: backend_unsupported: ...` naming the backend that can serve them.

## Headless server recipe

```bash
npm install -g obsidian-headless && ob login && ob sync-setup --vault "My Vault" --path ~/vault
ob sync --continuous &          # optional: keep the vault fresh via Obsidian Sync
export OBSIDIAN_VAULT_PATH=~/vault
uvx obsidian-blade-mcp          # file backend, stdio
```

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
| `OBSIDIAN_VAULT_PATH` | (none) | Vault directory. Required for the file backend; on the cli backend, writes refuse if the CLI's vault differs |
| `OBSIDIAN_MCP_BACKEND` | `auto` | `auto` (cli if Obsidian is running, else file), `cli`, or `file` |
| `OBSIDIAN_VAULT_NAME` | (none) | Default vault to target (cli backend) |
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

This project is not affiliated with, endorsed by, or sponsored by Obsidian.md or Dynalist Inc. "Obsidian" is a trademark of its respective owner.
