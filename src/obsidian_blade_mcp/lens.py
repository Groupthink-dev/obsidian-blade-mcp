"""Obsidian Lens integration — connection management, formatting, heartbeat."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None

HEARTBEAT_STALE_SECONDS = 300  # 5 minutes


def get_lens_connection() -> sqlite3.Connection:
    """Get or create a read-only connection to the lens database.

    Derives DB path from OBSIDIAN_VAULT_PATH via LensConfig.
    Raises RuntimeError if OBSIDIAN_VAULT_PATH is not set or DB doesn't exist.
    """
    global _conn  # noqa: PLW0603
    if _conn is not None:
        return _conn

    from obsidian_lens.config import LensConfig

    try:
        config = LensConfig.from_env()
    except ValueError as e:
        raise RuntimeError(str(e)) from e

    db_path = config.db_path
    if not db_path.exists():
        raise RuntimeError(
            f"Lens database not found at {db_path}. "
            "Run 'obsidian-lens reindex' to build the index."
        )

    from obsidian_lens.db import get_connection

    _conn = get_connection(db_path, readonly=True)
    logger.info("Lens DB connected: %s", db_path)
    return _conn


def heartbeat_warning(conn: sqlite3.Connection) -> str:
    """Return a warning string if the daemon heartbeat is stale, else empty string."""
    try:
        row = conn.execute(
            "SELECT last_beat, status FROM heartbeat WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return "⚠ Lens heartbeat table missing — index may be uninitialised.\n\n"

    if row is None:
        return "⚠ Lens daemon has never run — index may be stale.\n\n"

    last_beat = datetime.fromisoformat(row["last_beat"])
    if last_beat.tzinfo is None:
        last_beat = last_beat.replace(tzinfo=UTC)

    age = (datetime.now(UTC) - last_beat).total_seconds()
    if age > HEARTBEAT_STALE_SECONDS:
        mins = int(age // 60)
        return f"⚠ Lens daemon last seen {mins}m ago — results may be stale.\n\n"

    return ""


def format_lens_results(results: list[Any], label: str = "results") -> str:
    """Format SearchResult list as token-efficient text."""
    if not results:
        return f"No {label} found."

    lines: list[str] = []
    for r in results:
        parts = [r.path]
        if r.title and r.title != r.path:
            parts.append(f"«{r.title}»")
        if r.score:
            parts.append(f"score={r.score:.4f}")
        if r.kind:
            parts.append(f"kind={r.kind}")
        if r.status:
            parts.append(f"status={r.status}")
        lines.append(" | ".join(parts))
        if r.snippet:
            lines.append(f"  {r.snippet[:200]}")

    header = f"{len(results)} {label}:"
    return header + "\n" + "\n".join(lines)


def format_connections(results: list[dict[str, Any]]) -> str:
    """Format connections() output as token-efficient text."""
    if not results:
        return "No connections found."

    lines: list[str] = []
    for r in results:
        parts = [r["path"]]
        if r.get("alias"):
            parts.append(f"alias={r['alias']}")
        parts.append(f"dir={r['direction']}")
        parts.append(f"depth={r['depth']}")
        lines.append(" | ".join(parts))

    return f"{len(results)} connections:\n" + "\n".join(lines)
