"""Работа с таблицей items: все запросы к базе живут здесь."""
import sqlite3
from typing import Dict, List, Optional

from .models import today

SORTS = {
    "id": "id DESC",
    "title": "title COLLATE NOCASE ASC",
    "rating": "rating IS NULL, rating DESC",
    "finished": "finished_at IS NULL, finished_at DESC",
}


def add_item(
    conn: sqlite3.Connection,
    *,
    title: str,
    type: str = "movie",
    status: str = "planned",
    rating: Optional[int] = None,
    total: Optional[int] = None,
    notes: Optional[str] = None,
    external_id: Optional[str] = None,
    year: Optional[int] = None,
    original_title: Optional[str] = None,
) -> int:
    started = today() if status in ("watching", "completed") else None
    finished = today() if status == "completed" else None
    with conn:
        cur = conn.execute(
            "INSERT INTO items (title, type, status, rating, total, started_at, finished_at, "
            "notes, external_id, year, original_title) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, type, status, rating, total, started, finished, notes, external_id, year, original_title),
        )
    return cur.lastrowid


def get_item(conn: sqlite3.Connection, item_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def list_items(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "id",
) -> List[sqlite3.Row]:
    where, params = [], []
    if status:
        where.append("status = ?")
        params.append(status)
    if kind:
        where.append("type = ?")
        params.append(kind)
    sql = "SELECT * FROM items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {SORTS[sort]}"
    rows = conn.execute(sql, params).fetchall()
    if search:
        # LIKE в SQLite не различает регистр только у латиницы, поэтому ищем в Python
        needle = search.casefold()
        rows = [
            r for r in rows
            if needle in r["title"].casefold() or needle in (r["original_title"] or "").casefold()
        ]
    return rows


def set_progress(conn: sqlite3.Connection, item: sqlite3.Row, ep: int) -> bool:
    """Обновляет прогресс. Возвращает True, если запись стала completed."""
    started = item["started_at"] or today()
    with conn:
        if item["total"] and ep >= item["total"]:
            conn.execute(
                "UPDATE items SET progress = ?, status = 'completed', started_at = ?, finished_at = ? WHERE id = ?",
                (item["total"], started, today(), item["id"]),
            )
            return True
        conn.execute(
            "UPDATE items SET progress = ?, status = 'watching', started_at = ?, finished_at = NULL WHERE id = ?",
            (ep, started, item["id"]),
        )
        return False


def mark_done(conn: sqlite3.Connection, item_id: int, rating: Optional[int]) -> None:
    with conn:
        conn.execute(
            "UPDATE items SET status = 'completed', started_at = COALESCE(started_at, ?), finished_at = ?, "
            "progress = COALESCE(total, progress), rating = COALESCE(?, rating) WHERE id = ?",
            (today(), today(), rating, item_id),
        )


def set_rating(conn: sqlite3.Connection, item_id: int, rating: int) -> None:
    with conn:
        conn.execute("UPDATE items SET rating = ? WHERE id = ?", (rating, item_id))


def set_status(conn: sqlite3.Connection, item_id: int, status: str) -> None:
    with conn:
        conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))


def edit_item(conn: sqlite3.Connection, item: sqlite3.Row, title, kind, total, notes) -> None:
    with conn:
        conn.execute(
            "UPDATE items SET title = ?, type = ?, total = ?, notes = ? WHERE id = ?",
            (
                title or item["title"],
                kind or item["type"],
                total if total is not None else item["total"],
                notes if notes is not None else item["notes"],
                item["id"],
            ),
        )


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))


def apply_meta(conn: sqlite3.Connection, item: sqlite3.Row, meta) -> Dict[str, tuple]:
    """Подтягивает данные из онлайн-базы в существующую запись.

    Название, оценку, статус и прогресс не трогает. Возвращает словарь
    {поле: (было, стало)} только для реально изменившихся полей.
    """
    new_values = {"external_id": meta.ext_id}
    if meta.total and meta.total != item["total"]:
        new_values["total"] = meta.total
    if meta.year and not item["year"]:
        new_values["year"] = meta.year
    if meta.original_title and not item["original_title"]:
        new_values["original_title"] = meta.original_title

    changes = {k: (item[k], v) for k, v in new_values.items() if item[k] != v}
    if changes:
        sets = ", ".join(f"{k} = ?" for k in changes)
        with conn:
            conn.execute(
                f"UPDATE items SET {sets} WHERE id = ?",
                [v for _, v in changes.values()] + [item["id"]],
            )
    return changes


def completed_rows(conn: sqlite3.Connection, year: Optional[int] = None) -> List[sqlite3.Row]:
    if year:
        return conn.execute(
            "SELECT * FROM items WHERE status = 'completed' AND finished_at LIKE ?", (f"{year}%",)
        ).fetchall()
    return conn.execute("SELECT * FROM items WHERE status = 'completed'").fetchall()


def status_counts(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT status, COUNT(*) c FROM items GROUP BY status").fetchall()


def all_items(conn: sqlite3.Connection) -> List[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM items ORDER BY id").fetchall()]
