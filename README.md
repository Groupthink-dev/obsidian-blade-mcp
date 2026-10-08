# Obsidian Blade MCP

An [MCP](https://modelcontextprotocol.io) server that gives any MCP client, such as Claude Desktop, Claude Code or a headless agent, precise tools over an [Obsidian](https://obsidian.md) vault. When Obsidian is running it uses the official Obsidian CLI and Obsidian's own index. When Obsidian is closed, or the host has no Obsidian at all, it reads and writes the vault directory directly. Same 40 tools either way, read-only unless you opt in to writes, and it never launches Obsidian for you.

This project is not affiliated with, endorsed by, or sponsored by Obsidian.md or Dynalist Inc. "Obsidian" is a trademark of its respective owner.

## Contents

- [Why this exists](#why-this-exists)
- [Two backends, one surface](#two-backends-one-surface)
- [Install](#install)
- [Enabling writes](#enabling-writes)
- [Safety model](#safety-model)
- [Tools](#tools)
- [Configuration](#configuration)
- [Limits and known differences](#limits-and-known-differences)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Why this exists

Most Obsidian integrations need the desktop app open, a community plugin installed, or a REST bridge running. That is fine on a laptop and useless on a server, in CI, or on a machine where Obsidian is simply closed. This server works in all of those places. On a desktop with Obsidian open it defers to Obsidian's index, so search, Bases and the link graph are exactly what you see in the app. Everywhere else it falls back to a deterministic parser over the Markdown files: frontmatter, wikilinks, tags, tasks, daily notes and templates, with no embeddings, no inference and no network.

It is also built for agents rather than for people typing commands. Output is compact and capped, every response says which backend answered, writes are off until an operator turns them on, destructive operations dry-run first, and every edit can be guarded by a content hash so an agent never overwrites a note a human changed underneath it.

## Two backends, one surface

The backend is chosen once per process. In the default `auto` mode the server picks `cli` only when it detects a live Obsidian process **and** the CLI binary is installed. Otherwise it picks `file` if `OBSIDIAN_VAULT_PATH` points at a vault directory. It never starts Obsidian: the Obsidian CLI opens the GUI when the app is closed, and a server should not do that behind your back.

| | `cli` backend | `file` backend |
|---|---|---|
| Needs | Obsidian 1.12+ running, CLI enabled in Settings → General | A vault directory (`OBSIDIAN_VAULT_PATH`) |
| Platform | macOS, Linux desktop | Anything with Python 3.12: Linux servers, containers, CI |
| Index | Obsidian's own | Built by the server, cached, rebuilt when files change |
| Search | Obsidian search syntax, tokenised | Literal substring, case-insensitive by default |
| Link graph | Obsidian's resolver | Wikilinks and Markdown links, including links in frontmatter values |
| Bases | List, views, query | List only |
| Bookmarks | List and add | List only |
| Rename and move | Obsidian rewrites links | The server rewrites links |
| Daily notes and templates | Yes | Yes, from the `.obsidian` plugin settings |
| Content hashes for guarded writes | Best effort (read, then write) | Yes |

Every response ends with a trailer, `[backend: cli]` or `[backend: file]`, so an agent always knows which index answered. You can force a backend with `OBSIDIAN_MCP_BACKEND=cli` or `=file`.

## Install

Requirements: Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). The `uvx` launcher that ships with uv runs the package without a checkout. Set `OBSIDIAN_VAULT_PATH` in every recipe. On a desktop with Obsidian running it doubles as a write guard (writes refuse if the CLI's active vault is a different directory). With Obsidian closed it is what the file backend serves.

### Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uvx",
      "args": ["obsidian-blade-mcp"],
      "env": {
        "OBSIDIAN_VAULT_PATH": "/Users/you/Vault"
      }
    }
  }
}
```

Restart Claude Desktop. Ask it to call `vault_info`; the reply ends with `[backend: cli]` if Obsidian is open with the CLI enabled, or `[backend: file]` if not.

### Claude Code

```bash
claude mcp add obsidian --scope user \
  -e OBSIDIAN_VAULT_PATH="$HOME/Vault" \
  -- uvx obsidian-blade-mcp
```

Use `--scope project` to share the config with a repository instead. Claude Code reads the bundled [SKILL.md](SKILL.md) if you copy it into `.claude/skills/obsidian-blade/`; it teaches the model the token-efficient call patterns and the safety rules below.

### Linux server or container, no Obsidian

The file backend needs nothing but the vault files. If you use Obsidian Sync, the official [Obsidian Headless](https://obsidian.md/help/headless) client keeps a server copy current; any other sync (Syncthing, git, rsync) works just as well.

```bash
# optional: keep the vault fresh through Obsidian Sync
npm install -g obsidian-headless
ob login
ob sync-setup --vault "My Vault" --path ~/vault
ob sync --continuous &

export OBSIDIAN_VAULT_PATH=~/vault
uvx obsidian-blade-mcp            # file backend, stdio transport
```

For a long-running HTTP endpoint on the same host:

```bash
export OBSIDIAN_VAULT_PATH=~/vault
export OBSIDIAN_MCP_TRANSPORT=http
export OBSIDIAN_MCP_HOST=127.0.0.1   # loopback: no token needed for read-only
export OBSIDIAN_MCP_PORT=8766
uvx obsidian-blade-mcp
```

Binding anything other than loopback, or enabling writes over HTTP, requires `OBSIDIAN_MCP_API_TOKEN`; the server refuses to start otherwise. Clients send `Authorization: Bearer <token>`.

### From a checkout

```bash
git clone https://git.groupthink.asia/dev/obsidian-blade-mcp.git
cd obsidian-blade-mcp
uv sync
OBSIDIAN_VAULT_PATH=~/Vault uv run obsidian-blade-mcp
```

## Enabling writes

The server starts **read-only**. The twelve write tools are not merely refused; they are absent from the tool list, so a client cannot discover or call them. To enable them, set:

```
OBSIDIAN_MCP_WRITES=1
```

in the server's environment (the `env` block of the client config, or the shell that launches it). With writes on, the client sees all 40 tools. Write tools are: `vault_create`, `vault_append`, `vault_prepend`, `vault_section_replace`, `vault_property_set`, `vault_property_remove`, `vault_task_update`, `vault_bookmark_add`, `vault_daily_append`, `vault_delete`, `vault_rename`, `vault_move`.

## Safety model

Five layers, each independent of the others.

**1. Read-only by default.** Described above. An agent that was not granted writes cannot work around it from the client side; the tools do not exist in that process.

**2. Confirmation for destructive operations.** `vault_delete`, `vault_rename` and `vault_move` do nothing unless called with `confirm=true`. Without it they return a dry-run plan naming the exact source and destination, whether the target already exists, and on the file backend how many notes would have links rewritten:

```
Dry run: rename not applied. Pass confirm=true to apply.
source: projects/Alpha.md
destination: projects/Alpha v2.md
target_exists: False
notes_with_links_to_rewrite: 3
[backend: file]
```

Deletes go to `.trash/` inside the vault by default (recoverable); `permanent=true` is unrecoverable and the plan says so.

**3. Content-hash preconditions.** `vault_file_info` returns `hash: sha256:…` for any note. Pass that value as `if_hash=` to any content-changing tool (`append`, `prepend`, `section_replace`, `property_set`, `property_remove`, `task_update`, `delete`, `rename`, `move`). If the note changed since that read, the call returns `Error: conflict: <path> changed since it was read (expected sha256:…, found sha256:…)` and nothing is written. On the file backend the hash is computed from the bytes on disk. On the cli backend the content is read through the CLI first, so the check is best effort rather than atomic.

**4. Path containment.** The file backend resolves every path against the real vault root and refuses `..`, symlinks that escape the vault, and anything under `.obsidian/`, `.trash/` or `.git/`. Writes are atomic: a temporary file in the same directory followed by a rename, so a crash never leaves a half-written note.

**5. Transport and subprocess hygiene.** HTTP on a loopback address needs no token for read-only use. Any other bind requires `OBSIDIAN_MCP_API_TOKEN`, and so does enabling writes over HTTP on any bind; the server exits with a message instead of starting insecurely. The cli backend only ever builds list-form argument vectors with bare-word commands and `key=value` parameters, never a shell string, and a unit test greps the source to keep it that way.

## Tools

Forty tools in eight families. "Write" tools exist only with `OBSIDIAN_MCP_WRITES=1`. The last column is the file backend; the cli backend serves everything.

| Family | Tool | Write | File backend |
|---|---|---|---|
| Discovery | `vault_info` | | yes |
| | `vault_files` | | yes |
| | `vault_file_info` | | yes, adds `hash` |
| | `vault_folders` | | yes |
| | `vault_recents` | | yes |
| Content | `vault_read` | | yes |
| | `vault_outline` | | yes |
| | `vault_section_read` | | yes |
| | `vault_create` | write | yes |
| | `vault_append` | write | yes |
| | `vault_prepend` | write | yes |
| | `vault_section_replace` | write | yes |
| | `vault_delete` | write, confirm | yes |
| | `vault_rename` | write, confirm | yes, rewrites links |
| | `vault_move` | write, confirm | yes, rewrites path-qualified links |
| Properties | `vault_properties` | | yes |
| | `vault_property_read` | | yes |
| | `vault_query_properties` | | yes |
| | `vault_property_set` | write | yes |
| | `vault_property_remove` | write | yes |
| Search | `vault_search` | | yes, literal |
| | `vault_search_context` | | yes, literal |
| Graph and tags | `vault_links` | | yes |
| | `vault_backlinks` | | yes |
| | `vault_aliases` | | yes |
| | `vault_unresolved` | | yes |
| | `vault_orphans` | | yes |
| | `vault_deadends` | | yes |
| | `vault_tags` | | yes |
| | `vault_tag` | | yes |
| Bases | `vault_bases` | | yes |
| | `vault_base_views` | | no |
| | `vault_base_query` | | no |
| Tasks and bookmarks | `vault_tasks` | | yes |
| | `vault_task_update` | write | yes |
| | `vault_bookmarks` | | yes |
| | `vault_bookmark_add` | write | no |
| Daily and templates | `vault_daily_read` | | yes |
| | `vault_daily_append` | write | yes |
| | `vault_template_read` | | yes |

Unsupported operations return `Error: backend_unsupported: …` naming the backend that can serve them. Every tool takes `file=` (a note name resolved like a wikilink) or `path=` (an exact vault-relative path); the file backend has no "active note", so one of them is required there.

## Configuration

All configuration is environment variables.

| Variable | Default | Meaning |
|---|---|---|
| `OBSIDIAN_VAULT_PATH` | unset | Vault directory. Required for the file backend. On the cli backend, writes refuse if the CLI's active vault is a different directory |
| `OBSIDIAN_MCP_BACKEND` | `auto` | `auto` picks `cli` when Obsidian is running and the CLI is installed, else `file`. `cli` and `file` force one |
| `OBSIDIAN_MCP_WRITES` | unset | `1` registers the twelve write tools. Unset means read-only, 28 tools |
| `OBSIDIAN_VAULT_NAME` | unset | Vault to target on the cli backend when several are open |
| `OBSIDIAN_CLI_PATH` | auto-detect | Path to the `obsidian` binary |
| `OBSIDIAN_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `OBSIDIAN_MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `OBSIDIAN_MCP_PORT` | `8766` | HTTP bind port |
| `OBSIDIAN_MCP_API_TOKEN` | unset | Bearer token. Required for a non-loopback bind and for writes over HTTP |

A `.env.example` with the same table is in the repository.

## Limits and known differences

These apply to the file backend. The cli backend is Obsidian's own behaviour.

- **Search is literal.** `vault_search` matches a substring, case-insensitive unless `case_sensitive=true`. Obsidian tokenises, so a multi-word query that Obsidian matches across a line may not match here, and Obsidian operators such as `tag:` or `path:` are not interpreted. Use `vault_tag` and `vault_query_properties` for structured lookups.
- **Index bounds.** Directory listing stops at 50,000 files and index builds and searches stop after reading 512 MB of Markdown. A single file larger than 20 MB is skipped. When a bound is hit the server returns what it has and appends a `[partial: ...]` line before the `[backend: ...]` trailer, naming the bound that stopped the scan. The same message goes to the server log. A vault of 12,000 files builds its index in a few seconds and then serves from cache until a file changes.
- **Link resolution** follows Obsidian's rules closely but not perfectly: shortest path wins for a bare `[[name]]`, aliases resolve, links inside frontmatter values are indexed, Markdown links to absolute paths and `file:` URLs are ignored. Obscure cases (duplicate names across folders with embeds, non-Markdown link targets) may differ.
- **Tags** are read from `#tag` in bodies and from `tags` in frontmatter. Nested tags are reported as written.
- **Tasks** are `- [ ]` and `- [x]` items; custom status characters are reported but only `toggle`, `complete`, `uncomplete` and `status=<char>` are accepted by `vault_task_update`.
- **Bases** files are listed, not evaluated. Views and queries need Obsidian.
- **Bookmarks** are read from `.obsidian/bookmarks.json`; adding needs Obsidian.
- **Daily notes and templates** honour `.obsidian/daily-notes.json` and `.obsidian/templates.json`, including the Moment-style date format. Templater syntax is not evaluated; `{{date}}`, `{{time}}` and `{{title}}` are.
- **Excluded directories.** `.obsidian/`, `.trash/` and `.git/` are never listed, read or written.

## Troubleshooting

**The reply says `[backend: file]` but Obsidian is open.** The CLI is not enabled or not on `PATH`. Enable it in Settings → General and make sure the `obsidian` binary resolves, or set `OBSIDIAN_CLI_PATH`. The server never launches Obsidian, so it will not switch backends until you restart it.

**`No backend available`.** Obsidian is not running (or the CLI is missing) and `OBSIDIAN_VAULT_PATH` is unset or not a directory. Set it.

**A write tool is missing from the tool list.** The server was started without `OBSIDIAN_MCP_WRITES=1`. That is the read-only default, not a bug.

**`Error: conflict: … changed since it was read`.** The note changed between your `vault_file_info` and the write. Read again and pass the new hash.

**`Dry run: … not applied`.** Delete, rename and move need `confirm=true`. Read the plan, then call again with it.

**The server refuses to start on HTTP.** You bound a non-loopback address, or enabled writes over HTTP, without `OBSIDIAN_MCP_API_TOKEN`. Set a token or bind `127.0.0.1`.

**Results look incomplete on a very large vault.** Check the server log for a `bound reached` warning; the vault exceeded a scan bound. Narrow with `folder=` or `path=`, or move large attachments out of the vault.

**Search finds nothing on the file backend for a query that works in Obsidian.** The query uses Obsidian operators or spans tokens. Use a plain substring, or use `vault_tag`, `vault_query_properties` and `vault_links` for structured questions.

**macOS: the cli backend hangs.** The Obsidian CLI finds the running app through a socket under `$TMPDIR`. Some launchers strip that variable; the server restores it from `getconf DARWIN_USER_TEMP_DIR`, but if you wrap the server in another sandbox, pass `TMPDIR` through.

## Development

Release notes live in [CHANGELOG.md](CHANGELOG.md).

```bash
make install-dev    # uv sync with dev and test groups
make check          # ruff lint, ruff format --check, mypy
make test           # 361 unit tests, no Obsidian needed
make check-linux    # the same checks as CI, in a python:3.13 container with no Obsidian
make test-e2e       # end-to-end tests against a running Obsidian
```

CI runs on every push and pull request on [Woodpecker](https://ci.groupthink.asia) (Linux, Python 3.13, no Obsidian binary). The GitHub workflow in `.github/workflows/` is for a future mirror.

The canonical repository is `https://git.groupthink.asia/dev/obsidian-blade-mcp`. Releases are tagged `vX.Y.Z` with the version in `pyproject.toml` and published to PyPI with `make publish`.

## License

MIT. See [LICENSE](LICENSE).

This project is not affiliated with, endorsed by, or sponsored by Obsidian.md or Dynalist Inc. "Obsidian" is a trademark of its respective owner.
