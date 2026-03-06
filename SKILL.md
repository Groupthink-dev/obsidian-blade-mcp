---
name: obsidian-blade
description: Obsidian vault operations via CLI — read, write, search, properties, structure, tasks, bookmarks, file ops
version: 0.4.0
permissions:
  read:
    - vault_info
    - vault_read
    - vault_files
    - vault_file_info
    - vault_folders
    - vault_recents
    - vault_property_read
    - vault_properties
    - vault_search
    - vault_search_context
    - vault_tags
    - vault_tag
    - vault_bases
    - vault_base_views
    - vault_base_query
    - vault_outline
    - vault_links
    - vault_backlinks
    - vault_aliases
    - vault_unresolved
    - vault_orphans
    - vault_deadends
    - vault_tasks
    - vault_bookmarks
  write:
    - vault_create
    - vault_append
    - vault_prepend
    - vault_property_set
    - vault_property_remove
    - vault_task_update
    - vault_bookmark_add
    - vault_delete
    - vault_rename
    - vault_move
---

# Obsidian Blade MCP — Skill Guide

## Token Efficiency Rules (MANDATORY)

1. **Use `limit=` on list tools** — default is 20, reduce for browsing
2. **Use `vault_file_info` before `vault_read`** — check metadata without loading full content
3. **Use `vault_property_read` for single properties** — don't load all properties when you need one
4. **Use `vault_properties` for metadata overviews** — more efficient than reading the full note
5. **Prefer `file=` over `path=`** — name-based resolution is shorter to type
6. **Use `vault_search` before `vault_search_context`** — paths-only is cheaper; escalate to context only when needed
7. **Use `vault_bases` to discover .base files** — then `vault_base_query path=X` with the exact path
8. **Use `vault_orphans`/`vault_deadends` with `total_only=true` first** — the full list is ~12K items; use `path=` to scope before requesting full list
9. **Use `vault_outline` before `vault_read` for structure** — see headings without loading full content

## Quick Start — 5 Most Common Operations

```
vault_read file="My Note"              → Read note content
vault_create name="New" content="..."  → Create new note
vault_append content="..." file="Log"  → Append to existing note
vault_property_set name="status" value="done" file="Task"  → Set property
vault_search query="Docker" limit=10   → Find notes by content
```

## Tool Reference

### Meta
- **vault_info** — Vault name, path, file/note counts. Health check.

### File Read
- **vault_read** — Full note content. Use `file=` or `path=`.

### File Write
- **vault_create** — New note. Use `path=` for subfolder, `template=` for templates.
- **vault_append** — Add to end of note. Safe for human-written content.
- **vault_prepend** — Add after frontmatter. Status blocks, headings.

### Discovery
- **vault_files** — List files, optionally in a folder. Use `folder=`, `ext=`, `limit=`.
- **vault_file_info** — Metadata for one file (size, timestamps).
- **vault_folders** — All folders. Understand vault structure.
- **vault_recents** — Recently modified files. What's been active.

### Search
- **vault_search** — Find notes matching a query. Returns file paths. Use `path=` to scope.
- **vault_search_context** — Search with matching lines (`path:line: text`). More detail than `vault_search`.

### Tags
- **vault_tags** — List tags with usage counts. Use `sort_by_count=true` for most-used first.
- **vault_tag** — List all files with a specific tag.

### Bases
- **vault_bases** — List all `.base` files in the vault.
- **vault_base_views** — List views in a base (requires base to be active file).
- **vault_base_query** — Query a base for structured data. Use `path=` with `.base` extension.

### Link & Structure
- **vault_outline** — Heading tree with line numbers. Use before `vault_read` to preview structure.
- **vault_links** — Outbound links from a note.
- **vault_backlinks** — Inbound links (backlinks) to a note.
- **vault_aliases** — Aliases for a note (alternative wikilink names).
- **vault_unresolved** — Broken wikilinks across the vault. Use `limit=` and `path=` to scope.
- **vault_orphans** — Notes with no inbound links. Defaults to count-only (`total_only=true`).
- **vault_deadends** — Notes with no outbound links. Defaults to count-only (`total_only=true`).

### Tasks
- **vault_tasks** — List tasks (checkboxes). Use `file=` to scope, `status=` to filter.
- **vault_task_update** — Toggle/complete/uncomplete a task by `ref=path:line`.

### Bookmarks
- **vault_bookmarks** — List all bookmarks (files, folders, searches, URLs).
- **vault_bookmark_add** — Add a bookmark. Use `path=`, `search=`, or `url=`.

### File Operations
- **vault_delete** — Delete a file. Moves to trash by default. Use `permanent=true` to permanently delete (IRREVERSIBLE).
- **vault_rename** — Rename a file. Obsidian updates all wikilinks automatically.
- **vault_move** — Move a file to a new folder. Obsidian updates all wikilinks automatically.

### Properties (Atomic Frontmatter)
- **vault_property_read** — Read one property value.
- **vault_property_set** — Set/create a property. Atomic — safer than YAML editing.
- **vault_property_remove** — Delete a property.
- **vault_properties** — All properties for a note.

## Workflow Examples

### Daily Digest Data Gathering
```
1. vault_recents limit=10               → What changed recently
2. vault_files folder="+/ingest/" limit=20 → Inbox items
3. vault_property_read name="status" file="Effort Note"  → Check effort status
```

### Find and Read Notes
```
1. vault_search query="Docker" limit=5   → Find notes mentioning Docker
2. vault_search_context query="Docker" path="atlas/" limit=10  → See matching lines
3. vault_read file="Docker"              → Read the full note
```

### Explore Tags and Bases
```
1. vault_tags sort_by_count=true limit=10  → Most-used tags
2. vault_tag name="#IT/software"           → Files with that tag
3. vault_bases                             → List all .base files
4. vault_base_query path="efforts/Digital Assistant - jobs.base" view="Phase 5"  → Query a base
```

### Create a New Effort Note
```
1. vault_folders                         → Find correct area path
2. vault_create name="My Effort" path="spaces/Systems/Areas/Knowledge Management/efforts/" content="..."
3. vault_property_set name="kind" value="effort" path="spaces/.../My Effort.md"
4. vault_property_set name="status" value="on" path="spaces/.../My Effort.md"
```

### Vault Health Audit
```
1. vault_orphans total_only=true              → Count orphan notes
2. vault_deadends total_only=true             → Count dead-end notes
3. vault_unresolved limit=10                  → Top broken links
4. vault_orphans path="atlas/" total_only=false limit=10  → Orphans in atlas/
5. vault_outline file="Important Note"        → Check structure before reading
6. vault_links file="Hub Note"                → See what it links to
7. vault_backlinks file="Hub Note"            → See what links to it
```

### Classify and File an Inbox Item
```
1. vault_read path="+/ingest/raw-capture.md"       → Read content
2. vault_properties path="+/ingest/raw-capture.md"  → Check existing metadata
3. vault_property_set name="ai_confidence" value="0.87" path="+/ingest/raw-capture.md"
4. vault_move path="+/ingest/raw-capture.md" destination="spaces/Systems/Areas/..."  → Move to correct area
```

### Task Management
```
1. vault_tasks status="unchecked" limit=10   → List open tasks
2. vault_tasks file="Sprint Plan"            → Tasks in a specific note
3. vault_task_update ref="notes/Todo.md:5" action="complete"  → Check off a task
```

## Common Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `file` | Note name (wikilink resolution) | `file="My Note"` |
| `path` | Exact path from vault root | `path="spaces/Systems/note.md"` |
| `folder` | Filter to folder (vault_files) | `folder="spaces/"` |
| `vault` | Target a different vault | `vault="other-vault"` |
| `limit` | Cap list results (default: 20) | `limit=10` |
| `query` | Search query string | `query="Docker"` |
| `name` | New note name / tag name | `name="New Note"` |
| `content` | Markdown content | `content="# Hello\nBody"` |
| `ref` | Task reference (path:line) | `ref="notes/Todo.md:5"` |
| `destination` | Target folder for move | `destination="spaces/Systems/"` |

## Prerequisites

- **Obsidian v1.12+** must be installed and running
- **CLI enabled** at Settings → General
- Vault must be open in Obsidian
