"""
SQLite-backed snapshot persistence for media library index data.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.logging_config import get_logger


logger = get_logger("media.library.snapshot")

_DB_PATH = Path(__file__).resolve().parents[2] / "cache" / "library_snapshot.db"
_DB_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS library_snapshot (
            root_dir TEXT PRIMARY KEY,
            generated_at INTEGER NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


def save_snapshot(root_dir: str, items: list[dict[str, Any]]) -> None:
    """
    Persist a full media-library scan snapshot for one root directory.
    """
    normalized_root = str(Path(root_dir).resolve())
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    generated_at = int(time.time())

    with _DB_LOCK:
        with closing(_connect()) as conn:
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO library_snapshot (root_dir, generated_at, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(root_dir) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    payload = excluded.payload
                """,
                (normalized_root, generated_at, payload),
            )
            conn.commit()


def load_snapshot(root_dir: str, max_age_seconds: int) -> list[dict[str, Any]] | None:
    """
    Load a snapshot if present and still fresh.
    """
    normalized_root = str(Path(root_dir).resolve())
    now = int(time.time())

    with _DB_LOCK:
        with closing(_connect()) as conn:
            _ensure_schema(conn)
            row = conn.execute(
                """
                SELECT generated_at, payload
                FROM library_snapshot
                WHERE root_dir = ?
                """,
                (normalized_root,),
            ).fetchone()

    if row is None:
        return None

    generated_at = int(row["generated_at"])
    if max_age_seconds > 0 and now - generated_at > max_age_seconds:
        return None

    try:
        payload = json.loads(row["payload"])
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse persisted library snapshot: {exc}")
        return None

    if not isinstance(payload, list):
        return None

    parsed_items: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            parsed_items.append(item)
    return parsed_items or None
