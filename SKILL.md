---
name: obsidian-blade
description: Obsidian vault operations via CLI — read, write, search, properties, structure
version: 0.1.0
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
  write:
    - vault_create
    - vault_append
    - vault_prepend
    - vault_property_set
    - vault_property_remove
---

# Obsidian Blade MCP — Skill Guide

## Token Efficiency Rules (MANDATORY)

1. **Use `limit=` on list tools** — default is 20, reduce for browsing
2. **Use `vault_file_info` before `vault_read`** — check metadata without loading full content
3. **Use `vault_property_read` for single properties** — don't load all properties when you need one
4. **Use `vault_properties` for metadata overviews** — more efficient than reading the full note
5. **Prefer `file=` over `path=`** — name-based resolution is shorter to type

## Quick Start — 5 Most Common Operations

```
vault_read file="My Note"              → Read note content
vault_create name="New" content="..."  → Create new note
vault_append content="..." file="Log"  → Append to existing note
vault_property_set name="status" value="done" file="Task"  → Set property
vault_files path="spaces/" limit=10    → Browse folder
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
- **vault_files** — List files, optionally in a folder. Use `limit=`.
- **vault_file_info** — Metadata for one file (size, timestamps).
- **vault_folders** — All folders. Understand vault structure.
- **vault_recents** — Recently modified files. What's been active.

### Properties (Atomic Frontmatter)
- **vault_property_read** — Read one property value.
- **vault_property_set** — Set/create a property. Atomic — safer than YAML editing.
- **vault_property_remove** — Delete a property.
- **vault_properties** — All properties for a note.

## Workflow Examples

### Daily Digest Data Gathering
```
1. vault_recents limit=10               → What changed recently
2. vault_files path="+/ingest/" limit=20 → Inbox items
3. vault_property_read name="status" file="Effort Note"  → Check effort status
```

### Create a New Effort Note
```
1. vault_folders                         → Find correct area path
2. vault_create name="My Effort" path="spaces/Systems/Areas/Knowledge Management/efforts/" content="..."
3. vault_property_set name="kind" value="effort" path="spaces/.../My Effort.md"
4. vault_property_set name="status" value="on" path="spaces/.../My Effort.md"
```

### Classify and File an Inbox Item
```
1. vault_read path="+/ingest/raw-capture.md"       → Read content
2. vault_properties path="+/ingest/raw-capture.md"  → Check existing metadata
3. vault_property_set name="ai_confidence" value="0.87" path="+/ingest/raw-capture.md"
4. vault_property_set name="ai_suggested_destination" value="spaces/Systems/..." path="+/ingest/raw-capture.md"
```

## Common Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `file` | Note name (wikilink resolution) | `file="My Note"` |
| `path` | Exact path from vault root | `path="spaces/Systems/note.md"` |
| `vault` | Target a different vault | `vault="other-vault"` |
| `limit` | Cap list results (default: 20) | `limit=10` |
| `name` | New note name (vault_create) | `name="New Note"` |
| `content` | Markdown content | `content="# Hello\nBody"` |

## Prerequisites

- **Obsidian v1.12+** must be installed and running
- **CLI enabled** at Settings → General
- Vault must be open in Obsidian
