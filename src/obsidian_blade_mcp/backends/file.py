"""Direct-file vault backend.

Serves the tool surface from the vault directory alone. No Obsidian process,
no CLI. Deterministic parsing only: Markdown headings, YAML frontmatter,
wikilinks, ``#tags`` and ``- [ ]`` tasks. No embeddings, no inference.

Response shapes mirror what the CLI backend returns for the same operation so
the formatters in ``server.py`` do not care which backend answered.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import yaml  # type: ignore[import-untyped]

from obsidian_blade_mcp.backend import BackendUnsupportedError
from obsidian_blade_mcp.client import ObsidianCLIError, ObsidianFileNotFoundError, ObsidianVaultError, content_hash_of

logger = logging.getLogger(__name__)

# Bounds (scoping §8c)
MAX_SCAN_FILES = 50_000  # listing bound (stat only, no reads)
MAX_SCAN_BYTES = 512 * 1024 * 1024  # bound on markdown bytes *read* per index build or search
MAX_FILE_BYTES = 20 * 1024 * 1024

CONFIG_DIR = ".obsidian"
TRASH_DIR = ".trash"
EXCLUDED_DIRS = frozenset({CONFIG_DIR, TRASH_DIR, ".git"})

# Partial-result register. A scan that hits a bound records one line here; the server's trailer middleware
# drains it after each tool call and appends it to the response as ``[partial: ...]``. Process-wide on purpose:
# the cli backend builds a throwaway FileBackend per delegated call, so instance state would be lost.
_partial_notes: list[str] = []


def note_partial(message: str) -> None:
    """Record that the current scan stopped at a bound; the response will carry ``[partial: message]``."""
    logger.warning("%s; results are partial", message)
    if message not in _partial_notes:
        _partial_notes.append(message)


def take_partial() -> list[str]:
    """Return and clear the partial-result notes recorded since the last call."""
    notes = list(_partial_notes)
    _partial_notes.clear()
    return notes


_WIKILINK = re.compile(r"!?\[\[([^\]\|#]+)(?:#[^\]\|]*)?(?:\|[^\]]*)?\]\]")
_MDLINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+\.md)(?:#[^)]*)?\)")
_TAG = re.compile(r"(?<![\w/#&])#([A-Za-z_][\w/-]*)")
_TASK = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)\[(.)\]\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_MOMENT_TOKENS = [
    ("YYYY", "%Y"),
    ("MMMM", "%B"),
    ("dddd", "%A"),
    ("MMM", "%b"),
    ("ddd", "%a"),
    ("YY", "%y"),
    ("MM", "%m"),
    ("DD", "%d"),
    ("HH", "%H"),
    ("mm", "%M"),
    ("ss", "%S"),
    ("M", "%-m"),
    ("D", "%-d"),
]


class _StringBoolLoader(yaml.SafeLoader):
    """YAML 1.1 booleans (on/off/yes/no) stay strings, as Obsidian treats them."""


_StringBoolLoader.add_constructor(
    "tag:yaml.org,2002:bool",
    lambda loader, node: loader.construct_scalar(node),
)


def parse_heading(line: str) -> tuple[int, str] | None:
    """Return ``(level, text)`` for an ATX heading line, else ``None``."""
    stripped = line.rstrip("\r\n")
    if not stripped.startswith("#"):
        return None
    i = 0
    while i < len(stripped) and stripped[i] == "#":
        i += 1
    if i == 0 or i > 6 or i >= len(stripped) or stripped[i] != " ":
        return None
    return i, stripped[i + 1 :].strip()


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split ``text`` into ``(yaml_block, body)``. ``yaml_block`` excludes the fences."""
    if not text.startswith("---\n") and text != "---":
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    after = end + len("\n---")
    if after < len(text) and text[after] not in "\r\n":
        return None, text
    yaml_block = text[4:end]
    body = text[after:]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return yaml_block, body


def parse_frontmatter_text(yaml_block: str | None) -> dict[str, Any] | None:
    if yaml_block is None:
        return None
    try:
        data = yaml.load(yaml_block, Loader=_StringBoolLoader)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def dump_frontmatter(data: dict[str, Any]) -> str:
    dumped: str = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return dumped.rstrip("\n")


def moment_to_strftime(fmt: str) -> str:
    """Translate the subset of moment.js tokens Obsidian users rely on."""
    out: list[str] = []
    i = 0
    while i < len(fmt):
        if fmt[i] == "[":
            j = fmt.find("]", i)
            if j == -1:
                out.append(fmt[i:])
                break
            out.append(fmt[i + 1 : j].replace("%", "%%"))
            i = j + 1
            continue
        for token, directive in _MOMENT_TOKENS:
            if fmt.startswith(token, i):
                out.append(directive)
                i += len(token)
                break
        else:
            out.append(fmt[i].replace("%", "%%"))
            i += 1
    return "".join(out)


@dataclass
class _Index:
    """Link graph over the vault, rebuilt when the vault changes."""

    stamp: tuple[int, int]
    stems: dict[str, list[str]] = field(default_factory=dict)  # lower stem -> rel paths
    outgoing: dict[str, list[str]] = field(default_factory=dict)  # rel path -> raw targets
    resolved: dict[str, list[str]] = field(default_factory=dict)  # rel path -> resolved rel paths
    incoming: dict[str, list[str]] = field(default_factory=dict)  # rel path -> sources
    unresolved: dict[str, list[str]] = field(default_factory=dict)  # rel path -> raw targets
    aliases: dict[str, list[str]] = field(default_factory=dict)  # lower alias -> rel paths
    tags: dict[str, Counter[str]] = field(default_factory=dict)  # rel path -> tag counts


class FileBackend:
    """Vault access from the filesystem. See module docstring."""

    name = "file"

    def __init__(self, vault_path: str) -> None:
        root = os.path.realpath(vault_path)
        if not os.path.isdir(root):
            raise ObsidianVaultError(f"Vault directory not found: {vault_path}", returncode=1)
        self.root = root
        self.vault_name = os.path.basename(root.rstrip(os.sep))
        self._index: _Index | None = None

    # -------------------------------------------------------------------
    # Path helpers
    # -------------------------------------------------------------------

    def _abs(self, rel: str) -> str:
        """Resolve a vault-relative path, refusing escapes and config internals."""
        rel = rel.replace("\\", "/").strip().lstrip("/")
        if not rel or rel.startswith("..") or "\n" in rel:
            raise ObsidianCLIError(f"Invalid path: {rel!r}")
        full = os.path.realpath(os.path.join(self.root, rel))
        if full != self.root and not full.startswith(self.root + os.sep):
            raise ObsidianCLIError(f"Path escapes the vault: {rel}")
        first = rel.split("/", 1)[0]
        if first in EXCLUDED_DIRS:
            raise ObsidianCLIError(f"Path is inside a reserved directory: {rel}")
        return full

    def _rel(self, full: str) -> str:
        return os.path.relpath(full, self.root).replace(os.sep, "/")

    def _target(self, file: str | None, path: str | None) -> str:
        """Resolve ``file=`` (wikilink-style) or ``path=`` (exact) to a rel path."""
        if path:
            rel = path.replace("\\", "/").strip().lstrip("/")
            full = self._abs(rel)
            if os.path.isfile(full):
                return rel
            if not rel.endswith(".md") and os.path.isfile(full + ".md"):
                return rel + ".md"
            raise ObsidianFileNotFoundError(f"File not found: {path}")
        if file:
            resolved = self.resolve_name(file)
            if resolved is None:
                raise ObsidianFileNotFoundError(f"File not found: {file}")
            return resolved
        raise ObsidianCLIError("Specify file= or path= (the file backend has no active file).")

    def resolve_name(self, name: str) -> str | None:
        """Resolve a note name like a wikilink: case-insensitive stem, shortest path wins."""
        name = name.replace("\\", "/").strip().lstrip("/")
        if name.lower().endswith(".md"):
            name = name[:-3]
        idx = self._get_index()
        if "/" in name:
            # folder-qualified: exact relative match preferred
            candidate = name + ".md"
            full = os.path.join(self.root, candidate)
            if os.path.isfile(full):
                return candidate
            stem = name.rsplit("/", 1)[1].lower()
            for rel in idx.stems.get(stem, []):
                if rel.lower().endswith(("/" + name + ".md").lower()):
                    return rel
            return None
        paths = idx.stems.get(name.lower(), [])
        if paths:
            return min(paths, key=lambda p: (p.count("/"), len(p), p))
        for rel in idx.aliases.get(name.lower(), []):
            return rel
        return None

    def _read_text(self, rel: str) -> str:
        full = self._abs(rel)
        if not os.path.isfile(full):
            raise ObsidianFileNotFoundError(f"File not found: {rel}")
        if os.path.getsize(full) > MAX_FILE_BYTES:
            raise ObsidianCLIError(f"File exceeds {MAX_FILE_BYTES} bytes: {rel}")
        try:
            with open(full, encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError as exc:
            raise ObsidianCLIError(f"File is not UTF-8 text: {rel}") from exc

    def _write_text(self, rel: str, text: str) -> None:
        """Atomic write: temp file in the same directory, then rename."""
        full = self._abs(rel)
        directory = os.path.dirname(full)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".blade-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            os.replace(tmp, full)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self._index = None

    def _walk(self, folder: str | None = None, ext: str | None = None) -> list[str]:
        """Rel paths under ``folder`` (vault root by default), bounded, excluding reserved dirs."""
        start = self._abs(folder) if folder else self.root
        if not os.path.isdir(start):
            return []
        want_ext = ("." + ext.lstrip(".")).lower() if ext else None
        out: list[str] = []
        for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith("."))
            for fn in sorted(filenames):
                if fn.startswith("."):
                    continue
                if want_ext and not fn.lower().endswith(want_ext):
                    continue
                full = os.path.join(dirpath, fn)
                if os.path.islink(full):
                    continue
                out.append(self._rel(full))
                if len(out) >= MAX_SCAN_FILES:
                    note_partial(f"listing bound reached at {len(out)} files")
                    return out
        return out

    def _read_notes(self, folder: str | None = None) -> Iterator[tuple[str, str]]:
        """Yield (rel, text) for markdown notes, bounded by MAX_SCAN_BYTES of content read."""
        total = 0
        for rel in self._notes(folder):
            try:
                text = self._read_text(rel)
            except ObsidianCLIError:
                continue
            total += len(text)
            yield rel, text
            if total >= MAX_SCAN_BYTES:
                note_partial(f"read bound reached at {total} bytes")
                return

    def _notes(self, folder: str | None = None) -> list[str]:
        return self._walk(folder, "md")

    # -------------------------------------------------------------------
    # Index
    # -------------------------------------------------------------------

    def _stamp(self) -> tuple[int, int]:
        """Cheap change detector: (file count, newest mtime in ns) over the vault."""
        count = 0
        newest = 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                count += 1
                try:
                    st = os.stat(os.path.join(dirpath, fn))
                except OSError:
                    continue
                newest = max(newest, st.st_mtime_ns)
                if count >= MAX_SCAN_FILES:
                    return count, newest
        return count, newest

    def _get_index(self) -> _Index:
        stamp = self._stamp()
        if self._index is not None and self._index.stamp == stamp:
            return self._index
        idx = _Index(stamp=stamp)
        notes = self._notes()
        for rel in notes:
            stem = os.path.splitext(os.path.basename(rel))[0].lower()
            idx.stems.setdefault(stem, []).append(rel)
        for rel, text in self._read_notes():
            yaml_block, body = split_frontmatter(text)
            fm = parse_frontmatter_text(yaml_block) or {}
            for alias in _as_list(fm.get("aliases")) + _as_list(fm.get("alias")):
                idx.aliases.setdefault(str(alias).lower(), []).append(rel)
            tag_counter: Counter[str] = Counter()
            for t in _as_list(fm.get("tags")) + _as_list(fm.get("tag")):
                tag_counter["#" + str(t).lstrip("#")] += 1
            targets: list[str] = []
            # Obsidian indexes wikilinks inside frontmatter values (e.g. ``up: "[[Parent]]"``).
            for val in _fm_strings(fm):
                targets.extend(m.group(1).strip() for m in _WIKILINK.finditer(val))
            in_fence = False
            for line in body.splitlines():
                if _FENCE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                targets.extend(m.group(1).strip() for m in _WIKILINK.finditer(line))
                targets.extend(m.group(1) for m in _MDLINK.finditer(line) if not m.group(1).startswith(("/", "file:")))
                for m in _TAG.finditer(line):
                    tag_counter["#" + m.group(1)] += 1
            idx.outgoing[rel] = targets
            idx.tags[rel] = tag_counter
        for rel, targets in idx.outgoing.items():
            resolved: list[str] = []
            unresolved: list[str] = []
            for raw in targets:
                hit = self._resolve_in_index(idx, raw, rel)
                if hit:
                    if hit not in resolved:
                        resolved.append(hit)
                    idx.incoming.setdefault(hit, [])
                    if rel not in idx.incoming[hit]:
                        idx.incoming[hit].append(rel)
                else:
                    unresolved.append(raw)
            idx.resolved[rel] = resolved
            if unresolved:
                idx.unresolved[rel] = unresolved
        self._index = idx
        return idx

    def _resolve_in_index(self, idx: _Index, raw: str, source: str) -> str | None:
        target = raw.replace("\\", "/").strip()
        if target.lower().endswith(".md"):
            target = target[:-3]
        if not target:
            return None
        if "/" in target:
            candidate = target.lstrip("/") + ".md"
            if candidate in idx.outgoing:
                return candidate
            # relative to the source folder
            base = os.path.dirname(source)
            rel = os.path.normpath(os.path.join(base, candidate)).replace(os.sep, "/")
            if rel in idx.outgoing:
                return rel
            stem = target.rsplit("/", 1)[1].lower()
        else:
            stem = target.lower()
        paths = idx.stems.get(stem, [])
        if not paths:
            return None
        if len(paths) == 1:
            return paths[0]
        source_dir = os.path.dirname(source)
        return min(paths, key=lambda p: (os.path.dirname(p) != source_dir, p.count("/"), len(p), p))

    # -------------------------------------------------------------------
    # F1 discovery
    # -------------------------------------------------------------------

    def vault_info(self, vault: str | None = None) -> Any:
        files = self._walk()
        folders = self.folders()
        size = 0
        for rel in files:
            try:
                size += os.path.getsize(os.path.join(self.root, rel))
            except OSError:
                pass
        return {
            "name": self.vault_name,
            "path": self.root,
            "files": len(files),
            "folders": len(folders),
            "size": size,
            "backend": self.name,
        }

    def files(
        self, folder: str | None = None, ext: str | None = None, limit: int | None = None, vault: str | None = None
    ) -> Any:
        rels = self._walk(folder, ext)
        entries: list[dict[str, Any]] = []
        for rel in rels:
            try:
                st = os.stat(os.path.join(self.root, rel))
            except OSError:
                continue
            entries.append({"path": rel, "size": st.st_size, "modified": _iso(st.st_mtime)})
        entries.sort(key=lambda e: str(e["modified"]), reverse=True)
        return entries

    def file_info(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        rel = self._target(file, path)
        st = os.stat(self._abs(rel))
        name, ext = os.path.splitext(os.path.basename(rel))
        info: dict[str, Any] = {
            "path": rel,
            "name": name,
            "extension": ext.lstrip("."),
            "size": st.st_size,
            "created": _iso(getattr(st, "st_birthtime", st.st_ctime)),
            "modified": _iso(st.st_mtime),
        }
        if rel.endswith(".md"):
            try:
                info["hash"] = content_hash_of(self._read_text(rel))
            except ObsidianCLIError:
                pass
            fm = self._frontmatter(rel)
            if fm:
                info["frontmatter"] = fm
        return info

    def folders(self, vault: str | None = None) -> Any:
        out: list[str] = []
        for dirpath, dirnames, _ in os.walk(self.root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith("."))
            for d in dirnames:
                out.append(self._rel(os.path.join(dirpath, d)))
                if len(out) >= MAX_SCAN_FILES:
                    note_partial(f"folder listing bound reached at {len(out)} folders")
                    return out
        return out

    def recents(self, limit: int | None = None, vault: str | None = None) -> Any:
        entries = self.files(ext="md")
        return entries[: limit or 20]

    # -------------------------------------------------------------------
    # F2 content
    # -------------------------------------------------------------------

    def read(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> str:
        return self._read_text(self._target(file, path))

    def create(
        self,
        name: str,
        content: str | None = None,
        path: str | None = None,
        template: str | None = None,
        vault: str | None = None,
        overwrite: bool = False,
        silent: bool = True,
    ) -> str:
        name = name.replace("\\", "/").strip().strip("/")
        if not name.endswith(".md"):
            name += ".md"
        rel = f"{path.strip().strip('/')}/{name}" if path else name
        full = self._abs(rel)
        if os.path.exists(full) and not overwrite:
            raise ObsidianCLIError(f"File already exists: {rel} (use overwrite=true)")
        body = content or ""
        if template:
            tpl = self.template_read(template)
            title = os.path.splitext(os.path.basename(rel))[0]
            tpl = _resolve_template_vars(tpl, title)
            body = tpl + ("\n" + body if body else "")
        self._write_text(rel, body)
        return f"Created: {rel}"

    def append(self, content: str, file: str | None = None, path: str | None = None, vault: str | None = None) -> str:
        rel = self._target(file, path)
        text = self._read_text(rel)
        if text and not text.endswith("\n"):
            text += "\n"
        self._write_text(rel, text + content + ("\n" if not content.endswith("\n") else ""))
        return f"Appended to: {rel}"

    def prepend(self, content: str, file: str | None = None, path: str | None = None, vault: str | None = None) -> str:
        rel = self._target(file, path)
        text = self._read_text(rel)
        yaml_block, body = split_frontmatter(text)
        chunk = content if content.endswith("\n") else content + "\n"
        if yaml_block is None:
            new = chunk + text
        else:
            new = f"---\n{yaml_block}\n---\n{chunk}{body}"
        self._write_text(rel, new)
        return f"Prepended to: {rel}"

    def outline(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        rel = self._target(file, path)
        text = self._read_text(rel)
        yaml_block, body = split_frontmatter(text)
        offset = (yaml_block.count("\n") + 3) if yaml_block is not None else 0
        out = []
        in_fence = False
        for i, line in enumerate(body.splitlines(), start=1):
            if _FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            h = parse_heading(line)
            if h:
                out.append({"level": h[0], "heading": h[1], "line": i + offset})
        return out

    def section_read(self, path: str, heading: str, vault: str | None = None) -> str:
        lines = self._read_text(self._target(None, path)).splitlines(keepends=True)
        start, level = _find_heading(lines, heading, path)
        section: list[str] = []
        for line in lines[start + 1 :]:
            h = parse_heading(line)
            if h is not None and h[0] <= level:
                break
            section.append(line)
        return "".join(section).rstrip("\n")

    def section_replace(self, path: str, heading: str, content: str, vault: str | None = None) -> str:
        rel = self._target(None, path)
        lines = self._read_text(rel).splitlines(keepends=True)
        start, level = _find_heading(lines, heading, path)
        end = len(lines)
        for i, line in enumerate(lines[start + 1 :], start=start + 1):
            h = parse_heading(line)
            if h is not None and h[0] <= level:
                end = i
                break
        if content and not content.endswith("\n"):
            content += "\n"
        new_lines = lines[: start + 1] + ([content] if content else []) + lines[end:]
        self._write_text(rel, "".join(new_lines))
        return f"Section '{heading}' replaced in {rel}"

    def delete_file(self, path: str, permanent: bool = False, vault: str | None = None) -> str:
        rel = self._target(None, path)
        full = self._abs(rel)
        if permanent:
            os.unlink(full)
            self._index = None
            return f"Deleted permanently: {rel}"
        trash_dir = os.path.join(self.root, TRASH_DIR)
        os.makedirs(trash_dir, exist_ok=True)
        dest = os.path.join(trash_dir, os.path.basename(rel))
        if os.path.exists(dest):
            stem, ext = os.path.splitext(os.path.basename(rel))
            dest = os.path.join(trash_dir, f"{stem} {datetime.now().strftime('%Y%m%d-%H%M%S')}{ext}")
        shutil.move(full, dest)
        self._index = None
        return f"Moved to trash: {rel}"

    def rename(self, path: str, to: str, vault: str | None = None) -> str:
        """Rename within the same folder and rewrite ``[[old]]`` links vault-wide."""
        rel = self._target(None, path)
        folder = os.path.dirname(rel)
        new_name = to.replace("\\", "/").strip().strip("/")
        if "/" in new_name:
            raise ObsidianCLIError("rename takes a file name, not a path; use move for folders")
        _, ext = os.path.splitext(rel)
        if not new_name.endswith(ext):
            new_name += ext
        new_rel = f"{folder}/{new_name}" if folder else new_name
        if os.path.exists(self._abs(new_rel)):
            raise ObsidianCLIError(f"Target already exists: {new_rel}")
        os.replace(self._abs(rel), self._abs(new_rel))
        self._index = None
        updated = 0
        if ext == ".md":
            updated = self._rewrite_links(rel, new_rel)
        return f"Renamed: {rel} → {new_rel}" + (f" ({updated} links updated)" if updated else "")

    def move(self, path: str, to: str, vault: str | None = None) -> str:
        """Move to a folder. Links by bare name keep resolving; path-qualified links are rewritten."""
        rel = self._target(None, path)
        dest_folder = to.replace("\\", "/").strip().strip("/")
        new_rel = f"{dest_folder}/{os.path.basename(rel)}" if dest_folder else os.path.basename(rel)
        new_full = self._abs(new_rel)
        if os.path.exists(new_full):
            raise ObsidianCLIError(f"Target already exists: {new_rel}")
        os.makedirs(os.path.dirname(new_full), exist_ok=True)
        os.replace(self._abs(rel), new_full)
        self._index = None
        updated = self._rewrite_links(rel, new_rel, qualified_only=True) if rel.endswith(".md") else 0
        return f"Moved: {rel} → {new_rel}" + (f" ({updated} links updated)" if updated else "")

    def _rewrite_links(self, old_rel: str, new_rel: str, qualified_only: bool = False, dry_run: bool = False) -> int:
        """Rewrite links from ``old_rel`` to ``new_rel``; with ``dry_run`` only count the notes it would touch."""
        old_stem = os.path.splitext(os.path.basename(old_rel))[0]
        new_stem = os.path.splitext(os.path.basename(new_rel))[0]
        old_q = old_rel[:-3] if old_rel.endswith(".md") else old_rel
        new_q = new_rel[:-3] if new_rel.endswith(".md") else new_rel
        pattern = re.compile(r"(!?\[\[)([^\]\|#]+)((?:#[^\]\|]*)?(?:\|[^\]]*)?\]\])")

        def sub(m: re.Match[str]) -> str:
            target = m.group(2).strip()
            if target == old_q or target == old_q + ".md":
                return f"{m.group(1)}{new_q}{m.group(3)}"
            if not qualified_only and target == old_stem:
                return f"{m.group(1)}{new_stem}{m.group(3)}"
            return m.group(0)

        touched = 0
        for rel in self._notes():
            if rel == new_rel:
                continue
            try:
                text = self._read_text(rel)
            except ObsidianCLIError:
                continue
            new_text, n = pattern.subn(sub, text)
            if n and new_text != text:
                if not dry_run:
                    self._write_text(rel, new_text)
                touched += 1
        return touched

    # -------------------------------------------------------------------
    # Safety helpers (Phase C)
    # -------------------------------------------------------------------

    def content_hash(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> str:
        """``sha256:<hex>`` over the note's bytes. Pass it back as ``if_hash`` to guard a write."""
        return content_hash_of(self._read_text(self._target(file, path)))

    def mutation_plan(
        self, op: str, path: str, to: str | None = None, permanent: bool = False, vault: str | None = None
    ) -> dict[str, Any]:
        """Describe what ``delete``/``rename``/``move`` would do, with exact paths, without doing it."""
        rel = self._target(None, path)
        plan: dict[str, Any] = {"op": op, "source": rel}
        if op == "delete":
            plan["destination"] = "permanent (unrecoverable)" if permanent else f"{TRASH_DIR}/{os.path.basename(rel)}"
            return plan
        if op == "rename":
            new_name = (to or "").replace("\\", "/").strip().strip("/")
            if "/" in new_name:
                raise ObsidianCLIError("rename takes a file name, not a path; use move for folders")
            _, ext = os.path.splitext(rel)
            if not new_name.endswith(ext):
                new_name += ext
            folder = os.path.dirname(rel)
            new_rel = f"{folder}/{new_name}" if folder else new_name
            qualified_only = False
        elif op == "move":
            dest_folder = (to or "").replace("\\", "/").strip().strip("/")
            new_rel = f"{dest_folder}/{os.path.basename(rel)}" if dest_folder else os.path.basename(rel)
            qualified_only = True
        else:
            raise ObsidianCLIError(f"Unknown mutation: {op}")
        plan["destination"] = new_rel
        plan["target_exists"] = os.path.exists(self._abs(new_rel))
        if rel.endswith(".md"):
            plan["notes_with_links_to_rewrite"] = self._rewrite_links(rel, new_rel, qualified_only, dry_run=True)
        return plan

    # -------------------------------------------------------------------
    # F3 properties
    # -------------------------------------------------------------------

    def _frontmatter(self, rel: str) -> dict[str, Any] | None:
        yaml_block, _ = split_frontmatter(self._read_text(rel))
        return parse_frontmatter_text(yaml_block)

    def property_read(
        self, name: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> Any:
        fm = self._frontmatter(self._target(file, path)) or {}
        if name not in fm:
            raise ObsidianCLIError(f"Property not found: {name}")
        return fm[name]

    def property_set(
        self, name: str, value: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> str:
        rel = self._target(file, path)
        text = self._read_text(rel)
        yaml_block, body = split_frontmatter(text)
        fm = parse_frontmatter_text(yaml_block)
        if yaml_block is not None and fm is None:
            raise ObsidianCLIError(f"Frontmatter is not a YAML mapping: {rel}")
        fm = dict(fm or {})
        fm[name] = _coerce(value)
        self._write_text(rel, f"---\n{dump_frontmatter(fm)}\n---\n{body}")
        return f"Set {name} in {rel}"

    def property_remove(
        self, name: str, file: str | None = None, path: str | None = None, vault: str | None = None
    ) -> str:
        rel = self._target(file, path)
        text = self._read_text(rel)
        yaml_block, body = split_frontmatter(text)
        fm = parse_frontmatter_text(yaml_block)
        if not fm or name not in fm:
            raise ObsidianCLIError(f"Property not found: {name}")
        fm = dict(fm)
        del fm[name]
        new = f"---\n{dump_frontmatter(fm)}\n---\n{body}" if fm else body
        self._write_text(rel, new)
        return f"Removed {name} from {rel}"

    def properties(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        if file or path:
            return self._frontmatter(self._target(file, path)) or {}
        counts: Counter[str] = Counter()
        for rel in self._notes():
            try:
                fm = self._frontmatter(rel)
            except ObsidianCLIError:
                continue
            for key in fm or {}:
                counts[key] += 1
        return [{"name": k, "count": v} for k, v in sorted(counts.items())]

    def query_properties(
        self,
        property: str,
        value: str,
        path: str | None = None,
        fields: str | None = None,
        limit: int = 50,
        vault: str | None = None,
    ) -> list[dict[str, Any]]:
        field_list = [f.strip() for f in fields.split(",")] if fields else None
        value_lower = value.lower()
        results: list[dict[str, Any]] = []
        for rel in self._notes(path):
            try:
                fm = self._frontmatter(rel)
            except ObsidianCLIError:
                continue
            if not fm:
                continue
            prop_value = fm.get(property)
            if prop_value is None or value_lower not in str(prop_value).lower():
                continue
            filtered = {k: v for k, v in fm.items() if k in field_list} if field_list else fm
            results.append({"file": rel, "properties": filtered})
            if len(results) >= limit:
                break
        results.sort(key=lambda r: r["properties"].get("rank", 0) or 0, reverse=True)
        return results

    # -------------------------------------------------------------------
    # F4 search
    # -------------------------------------------------------------------

    def search(
        self, query: str, path: str | None = None, case_sensitive: bool = False, vault: str | None = None
    ) -> Any:
        needle = query if case_sensitive else query.lower()
        hits: list[str] = []
        for rel, text in self._read_notes(path):
            hay = text if case_sensitive else text.lower()
            if needle in hay:
                hits.append(rel)
        return hits

    def search_context(
        self, query: str, path: str | None = None, case_sensitive: bool = False, vault: str | None = None
    ) -> str:
        needle = query if case_sensitive else query.lower()
        lines_out: list[str] = []
        for rel, text in self._read_notes(path):
            for n, line in enumerate(text.splitlines(), start=1):
                hay = line if case_sensitive else line.lower()
                if needle in hay:
                    lines_out.append(f"{rel}:{n}: {line.strip()}")
        return "\n".join(lines_out)

    # -------------------------------------------------------------------
    # F5 graph and tags
    # -------------------------------------------------------------------

    def tags(
        self, file: str | None = None, path: str | None = None, sort_by_count: bool = False, vault: str | None = None
    ) -> Any:
        idx = self._get_index()
        counter: Counter[str] = Counter()
        if file or (path and os.path.isfile(self._abs(path))):
            rel = self._target(file, path)
            counter.update(idx.tags.get(rel, Counter()))
        else:
            prefix = (path.strip().strip("/") + "/") if path else ""
            for rel, c in idx.tags.items():
                if not prefix or rel.startswith(prefix):
                    counter.update(c)
        items = sorted(counter.items(), key=(lambda kv: (-kv[1], kv[0])) if sort_by_count else (lambda kv: kv[0]))
        return [{"tag": t, "count": str(n)} for t, n in items]

    def tag(self, name: str, verbose: bool = False, vault: str | None = None) -> Any:
        idx = self._get_index()
        wanted = "#" + name.lstrip("#")
        return sorted(rel for rel, c in idx.tags.items() if wanted in c)

    def links(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        rel = self._target(file, path)
        return list(self._get_index().resolved.get(rel, []))

    def backlinks(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        rel = self._target(file, path)
        return [{"file": src} for src in self._get_index().incoming.get(rel, [])]

    def aliases(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        fm = self._frontmatter(self._target(file, path)) or {}
        return [str(a) for a in _as_list(fm.get("aliases")) + _as_list(fm.get("alias"))]

    def unresolved(self, path: str | None = None, vault: str | None = None) -> Any:
        idx = self._get_index()
        prefix = (path.strip().strip("/") + "/") if path else ""
        seen: dict[str, None] = {}
        for rel, raws in idx.unresolved.items():
            if prefix and not rel.startswith(prefix):
                continue
            for raw in raws:
                seen.setdefault(raw, None)
        return [{"link": raw} for raw in seen]

    def orphans(self, path: str | None = None, total_only: bool = True, vault: str | None = None) -> Any:
        idx = self._get_index()
        prefix = (path.strip().strip("/") + "/") if path else ""
        found = [rel for rel in idx.outgoing if (not prefix or rel.startswith(prefix)) and not idx.incoming.get(rel)]
        return str(len(found)) if total_only else found

    def deadends(self, path: str | None = None, total_only: bool = True, vault: str | None = None) -> Any:
        idx = self._get_index()
        prefix = (path.strip().strip("/") + "/") if path else ""
        found = [rel for rel, out in idx.resolved.items() if (not prefix or rel.startswith(prefix)) and not out]
        return str(len(found)) if total_only else found

    # -------------------------------------------------------------------
    # F6 bases — listing only
    # -------------------------------------------------------------------

    def bases(self, vault: str | None = None) -> Any:
        return self._walk(None, "base")

    def base_views(self, file: str | None = None, path: str | None = None, vault: str | None = None) -> Any:
        raise _unsupported("base_views")

    def base_query(
        self,
        file: str | None = None,
        path: str | None = None,
        view: str | None = None,
        output_format: str = "json",
        vault: str | None = None,
    ) -> Any:
        raise _unsupported("base_query")

    # -------------------------------------------------------------------
    # F7 tasks and bookmarks
    # -------------------------------------------------------------------

    def tasks(
        self, file: str | None = None, path: str | None = None, status: str | None = None, vault: str | None = None
    ) -> Any:
        if file or (path and os.path.isfile(self._abs(path))):
            rels = [self._target(file, path)]
        else:
            rels = self._notes(path)
        want = _normalise_status(status)
        out: list[dict[str, Any]] = []
        for rel in rels:
            try:
                text = self._read_text(rel)
            except ObsidianCLIError:
                continue
            in_fence = False
            for n, line in enumerate(text.splitlines(), start=1):
                if _FENCE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                m = _TASK.match(line)
                if not m:
                    continue
                mark = m.group(2)
                st = "unchecked" if mark == " " else "checked"
                if want and want != st and want != mark:
                    continue
                out.append({"text": m.group(3).strip(), "status": st, "mark": mark, "path": rel, "line": n})
        return out

    def task_update(self, ref: str, action: str = "toggle", vault: str | None = None) -> str:
        if ":" not in ref:
            raise ObsidianCLIError("Task ref must be path:line")
        rel_part, line_part = ref.rsplit(":", 1)
        try:
            line_no = int(line_part)
        except ValueError as exc:
            raise ObsidianCLIError(f"Bad line number in ref: {ref}") from exc
        rel = self._target(None, rel_part)
        lines = self._read_text(rel).splitlines(keepends=True)
        if line_no < 1 or line_no > len(lines):
            raise ObsidianCLIError(f"Line {line_no} out of range for {rel}")
        m = _TASK.match(lines[line_no - 1].rstrip("\r\n"))
        if not m:
            raise ObsidianCLIError(f"No task at {ref}")
        current = m.group(2)
        if action in ("toggle",):
            new_mark = " " if current != " " else "x"
        elif action in ("complete", "done", "check"):
            new_mark = "x"
        elif action in ("uncomplete", "todo", "uncheck"):
            new_mark = " "
        elif action.startswith("status=") and len(action) == 8:
            new_mark = action[-1]
        else:
            raise ObsidianCLIError(f"Unknown task action: {action}")
        prefix, text = m.group(1), m.group(3)
        eol = "\n" if lines[line_no - 1].endswith("\n") else ""
        lines[line_no - 1] = f"{prefix}[{new_mark}] {text}{eol}"
        self._write_text(rel, "".join(lines))
        return f"Task updated: {ref} ([{new_mark}])"

    def bookmarks(self, vault: str | None = None) -> Any:
        data = self._config_json("bookmarks.json")
        if not data:
            return []
        out: list[dict[str, Any]] = []

        def walk(items: list[dict[str, Any]], group: str | None) -> None:
            for item in items:
                kind = item.get("type", "file")
                if kind == "group":
                    walk(item.get("items", []), item.get("title"))
                    continue
                entry: dict[str, Any] = {"type": kind}
                if item.get("title"):
                    entry["title"] = item["title"]
                for key in ("path", "query", "url", "subpath"):
                    if item.get(key):
                        entry[key] = item[key]
                if group:
                    entry["group"] = group
                out.append(entry)

        walk(data.get("items", []), None)
        return out

    def bookmark_add(
        self,
        path: str | None = None,
        search: str | None = None,
        url: str | None = None,
        title: str | None = None,
        vault: str | None = None,
    ) -> str:
        raise _unsupported("bookmark_add")

    # -------------------------------------------------------------------
    # F8 daily notes and templates
    # -------------------------------------------------------------------

    def daily_path(self, when: datetime | None = None) -> str:
        cfg = self._config_json("daily-notes.json") or {}
        folder = str(cfg.get("folder") or "").strip().strip("/")
        fmt = str(cfg.get("format") or "YYYY-MM-DD")
        when = when or datetime.now()
        name = when.strftime(moment_to_strftime(fmt))
        rel = f"{folder}/{name}.md" if folder else f"{name}.md"
        return rel

    def daily_read(self, vault: str | None = None) -> str:
        rel = self.daily_path()
        full = self._abs(rel)
        if not os.path.isfile(full):
            raise ObsidianFileNotFoundError(f"Daily note does not exist yet: {rel}")
        return self._read_text(rel)

    def daily_append(self, content: str, vault: str | None = None) -> str:
        rel = self.daily_path()
        full = self._abs(rel)
        if not os.path.isfile(full):
            cfg = self._config_json("daily-notes.json") or {}
            body = ""
            tpl_name = cfg.get("template")
            if tpl_name:
                try:
                    body = _resolve_template_vars(self.template_read(str(tpl_name)), os.path.basename(rel)[:-3])
                except ObsidianCLIError:
                    body = ""
            self._write_text(rel, body)
        return self.append(content, path=rel)

    def template_read(self, name: str, vault: str | None = None) -> str:
        name = name.replace("\\", "/").strip().strip("/")
        if name.lower().endswith(".md"):
            name = name[:-3]
        cfg = self._config_json("templates.json") or {}
        folder = str(cfg.get("folder") or "").strip().strip("/")
        candidates = []
        if "/" in name:
            candidates.append(name + ".md")
        if folder:
            candidates.append(f"{folder}/{os.path.basename(name)}.md")
        candidates.append(name + ".md")
        for rel in candidates:
            try:
                full = self._abs(rel)
            except ObsidianCLIError:
                continue
            if os.path.isfile(full):
                return self._read_text(rel)
        raise ObsidianFileNotFoundError(f"Template not found: {name}")

    # -------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------

    def _config_json(self, filename: str) -> dict[str, Any] | None:
        full = os.path.join(self.root, CONFIG_DIR, filename)
        if not os.path.isfile(full):
            return None
        try:
            with open(full, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _unsupported(operation: str) -> BackendUnsupportedError:
    return BackendUnsupportedError(operation, "file")


def _find_heading(lines: list[str], heading: str, path: str) -> tuple[int, int]:
    for i, line in enumerate(lines):
        h = parse_heading(line)
        if h is not None and h[1] == heading:
            return i, h[0]
    raise ObsidianCLIError(f"Heading '{heading}' not found in {path}")


def _fm_strings(obj: Any) -> Iterator[str]:
    """All string leaves of a parsed frontmatter mapping, depth-first."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _fm_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _fm_strings(v)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [value]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


def _coerce(value: str) -> Any:
    """Turn a string tool argument into a YAML scalar/list the way Obsidian would."""
    s = value.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [v.strip().strip("\"'") for v in inner.split(",") if v.strip()] if inner else []
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return value


def _normalise_status(status: str | None) -> str | None:
    if not status:
        return None
    s = status.strip().lower()
    if s in ("checked", "done", "complete", "completed", "x"):
        return "checked"
    if s in ("unchecked", "todo", "open", "incomplete", " "):
        return "unchecked"
    return status.strip()


def _resolve_template_vars(text: str, title: str) -> str:
    now = datetime.now()
    text = re.sub(r"\{\{\s*title\s*\}\}", title, text)
    text = re.sub(
        r"\{\{\s*date(?::([^}]+))?\s*\}\}", lambda m: now.strftime(moment_to_strftime(m.group(1) or "YYYY-MM-DD")), text
    )
    text = re.sub(
        r"\{\{\s*time(?::([^}]+))?\s*\}\}", lambda m: now.strftime(moment_to_strftime(m.group(1) or "HH:mm")), text
    )
    return text
