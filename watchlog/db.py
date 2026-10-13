"""Подключение к SQLite и схема базы."""
import sqlite3
from pathlib import Path
from typing import Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    type           TEXT NOT NULL DEFAULT 'movie',
    status         TEXT NOT NULL DEFAULT 'planned',
    rating         INTEGER CHECK (rating BETWEEN 1 AND 10),
    progress       INTEGER NOT NULL DEFAULT 0,
    total          INTEGER,
    started_at     TEXT,
    finished_at    TEXT,
    notes          TEXT,
    external_id    TEXT,
    created_at     TEXT NOT NULL DEFAULT (date('now')),
    year           INTEGER,
    original_title TEXT
);
"""

# Столбцы, появившиеся после первой версии. Нужны, чтобы старая база
# (из версии с одним файлом) обновилась сама при первом запуске.
ADDED_COLUMNS = {
    "year": "INTEGER",
    "original_title": "TEXT",
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
    for name, ddl_type in ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE items ADD COLUMN {name} {ddl_type}")
    conn.commit()


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(path) if path else config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    return conn
