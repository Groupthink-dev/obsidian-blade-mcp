# Changelog

All notable changes to obsidian-blade-mcp. Versions follow the PyPI releases.

## 1.1.0 — 2026-10-09

- The MCP handshake reports the package version instead of the FastMCP library version.
- A file-backend scan that stops at the file or byte bound adds a `[partial: ...]` line before the `[backend: ...]` trailer. Previously the bound was only logged.

## 1.0.0 — 2026-10-09

- Read-only by default. The twelve write tools register only with `OBSIDIAN_MCP_WRITES=1`; a client sees 28 tools otherwise.
- `confirm=` on delete, rename and move. Without it the tool returns a dry-run plan naming source, destination and link rewrites.
- `if_hash=` on every content edit. `vault_file_info` reports `sha256:` hashes; a mismatch refuses the write with both hashes.
- HTTP policy: a non-loopback bind, or writes over HTTP, require `OBSIDIAN_MCP_API_TOKEN`; the server exits 2 otherwise.
- Argument hygiene: bare-word commands, keys and flags only; values travel as `key=value`; a test greps for the shell form.
- README rewritten as the 1.0.0 document. Published to PyPI by trusted publishing from the GitHub push mirror.

## 0.9.0 — 2026-10-09

- File backend: direct vault access when Obsidian is not running. Frontmatter, links, tags, tasks, daily notes, templates.
- Running-app probe. `auto` picks `cli` only when a live Obsidian process is detected; the server never launches Obsidian.
- `[backend: cli|file]` trailer on every response. `vault_daily_read`, `vault_daily_append`, `vault_template_read`. 40 tools.

## 0.8.0 — 2026-10-09

- `vault_lens_*` tools and the `obsidian-lens` dependency removed. Manifest version aligned with the package. Linux lane in CI. Non-affiliation line in the README. Canonical remote moved to Forgejo.
