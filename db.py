import json
import os
import sqlite3
from datetime import datetime

from constants import (
    MAX_MARKED_PER_WISH,
    MAX_WISHES,
    STATUS_HIDDEN,
    STATUS_MARKED,
    STATUS_NEW,
)
from checker import extract_item_id

DB_PATH = os.environ.get("MARKETSEARCHER_DB", "marketsearcher.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS wishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    last_run_status TEXT
);
CREATE TABLE IF NOT EXISTS items (
    wish_id INTEGER NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    item_id TEXT NOT NULL,
    link TEXT,
    title TEXT,
    price TEXT,
    price_value REAL,
    image_url TEXT,
    condition TEXT,
    distance TEXT,
    status TEXT NOT NULL DEFAULT 'unbewertet',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_checked TEXT,
    check_status TEXT,
    current_price TEXT,
    current_price_value REAL,
    PRIMARY KEY (wish_id, source, item_id)
);
CREATE INDEX IF NOT EXISTS idx_items_wish ON items(wish_id, status);
"""


def get_conn(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path=DB_PATH):
    conn = get_conn(path)
    with conn:
        conn.executescript(SCHEMA)
    conn.close()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _row_to_item(row):
    return {k: row[k] for k in row.keys()}


def list_wishes(conn):
    rows = conn.execute(
        """
        SELECT w.*,
            (SELECT COUNT(*) FROM items i WHERE i.wish_id = w.id) AS total,
            (SELECT COUNT(*) FROM items i WHERE i.wish_id = w.id AND i.status = ?) AS cnt_new,
            (SELECT COUNT(*) FROM items i WHERE i.wish_id = w.id AND i.status = 'plain') AS cnt_plain,
            (SELECT COUNT(*) FROM items i WHERE i.wish_id = w.id AND i.status = ?) AS cnt_marked,
            (SELECT COUNT(*) FROM items i WHERE i.wish_id = w.id AND i.status = ?) AS cnt_hidden,
            (SELECT COUNT(*) FROM items i WHERE i.wish_id = w.id AND i.status = ?
                  AND i.check_status = 'gone') AS cnt_gone
        FROM wishes w ORDER BY w.id
        """,
        (STATUS_NEW, STATUS_MARKED, STATUS_HIDDEN, STATUS_MARKED),
    ).fetchall()
    wishes = []
    for r in rows:
        d = dict(r)
        d["query"] = json.loads(d["query_json"])
        del d["query_json"]
        wishes.append(d)
    return wishes


def wish_count(conn):
    return conn.execute("SELECT COUNT(*) AS c FROM wishes").fetchone()["c"]


def create_wish(conn, name, query):
    if wish_count(conn) >= MAX_WISHES:
        raise ValueError(f"Maximal {MAX_WISHES} Wuensche erlaubt.")
    with conn:
        cur = conn.execute(
            "INSERT INTO wishes (name, query_json, created_at) VALUES (?, ?, ?)",
            (name.strip(), json.dumps(query, ensure_ascii=False, default=str), _now()),
        )
    return cur.lastrowid


def get_wish(conn, wish_id):
    r = conn.execute("SELECT * FROM wishes WHERE id = ?", (wish_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["query"] = json.loads(d["query_json"])
    del d["query_json"]
    return d


def update_wish_query(conn, wish_id, query):
    with conn:
        conn.execute(
            "UPDATE wishes SET query_json = ? WHERE id = ?",
            (json.dumps(query, ensure_ascii=False, default=str), wish_id),
        )


def rename_wish(conn, wish_id, name):
    with conn:
        conn.execute(
            "UPDATE wishes SET name = ? WHERE id = ?", (name.strip(), wish_id)
        )


def delete_wish(conn, wish_id):
    with conn:
        conn.execute("DELETE FROM wishes WHERE id = ?", (wish_id,))


def marked_count(conn, wish_id):
    return conn.execute(
        "SELECT COUNT(*) AS c FROM items WHERE wish_id = ? AND status = ?",
        (wish_id, STATUS_MARKED),
    ).fetchone()["c"]


def set_item_status(conn, wish_id, source, item_id, status):
    if status == STATUS_MARKED:
        row = conn.execute(
            "SELECT status FROM items WHERE wish_id = ? AND source = ? AND item_id = ?",
            (wish_id, source, item_id),
        ).fetchone()
        if row and row["status"] != STATUS_MARKED and marked_count(conn, wish_id) >= MAX_MARKED_PER_WISH:
            raise ValueError(
                f"Maximal {MAX_MARKED_PER_WISH} markierte Artikel pro Wunsch erreicht."
            )
    with conn:
        conn.execute(
            "UPDATE items SET status = ? WHERE wish_id = ? AND source = ? AND item_id = ?",
            (status, wish_id, source, item_id),
        )


def get_items(conn, wish_id, statuses=None):
    sql = "SELECT * FROM items WHERE wish_id = ?"
    params = [wish_id]
    if statuses:
        sql += f" AND status IN ({','.join('?' for _ in statuses)})"
        params.extend(statuses)
    sql += " ORDER BY rowid"
    return [_row_to_item(r) for r in conn.execute(sql, params).fetchall()]


def item_counts(conn, wish_id):
    rows = conn.execute(
        "SELECT status, COUNT(*) AS c FROM items WHERE wish_id = ? GROUP BY status",
        (wish_id,),
    ).fetchall()
    return {r["status"]: r["c"] for r in rows}


def merge_run(conn, wish_id, found_items, run_date=None):
    """Uebernimmt die Ergebnisse eines Tageslaufs in den Wunsch.

    found_items: Liste von Item-Dicts (aus run_sources). Neue Artikel werden
    als 'unbewertet' angelegt, bestehende aktualisiert. Artikel, die nicht mehr
    im Ergebnis sind und nicht markiert sind, werden entfernt. Markierte
    bleiben stehen (Verfuegbarkeit wird separat geprueft).
    Liefert (added, updated, removed).
    """
    run_date = run_date or _today()
    seen = set()
    added = updated = 0
    for item in found_items:
        source = item.get("source") or ""
        item_id = item.get("item_id") or extract_item_id(source, item.get("link"))
        if not item_id:
            item_id = item.get("link") or item.get("title") or ""
        if not source or not item_id:
            continue
        key = (source, item_id)
        if key in seen:
            continue
        seen.add(key)
        row = conn.execute(
            "SELECT rowid FROM items WHERE wish_id = ? AND source = ? AND item_id = ?",
            (wish_id, source, item_id),
        ).fetchone()
        fields = (
            "link, title, price, price_value, image_url, condition, distance"
        )
        values = (
            item.get("link"),
            item.get("title"),
            item.get("price"),
            item.get("price_value"),
            item.get("image_url"),
            item.get("condition"),
            item.get("distance"),
        )
        if row:
            with conn:
                conn.execute(
                    f"UPDATE items SET ({fields}) = (?,?,?,?,?,?,?), last_seen = ?, "
                    "check_status = NULL, current_price = NULL, current_price_value = NULL "
                    "WHERE wish_id = ? AND source = ? AND item_id = ?",
                    (*values, run_date, wish_id, source, item_id),
                )
            updated += 1
        else:
            with conn:
                conn.execute(
                    "INSERT INTO items (wish_id, source, item_id, link, title, price, "
                    "price_value, image_url, condition, distance, status, first_seen, last_seen) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        wish_id, source, item_id, *values, STATUS_NEW, run_date, run_date
                    ),
                )
            added += 1
    with conn:
        cur = conn.execute(
            "DELETE FROM items WHERE wish_id = ? AND last_seen < ? AND status != ?",
            (wish_id, run_date, STATUS_MARKED),
        )
    removed = cur.rowcount
    return added, updated, removed


def apply_check_result(conn, wish_id, source, item_id, result, checked_at=None):
    checked_at = checked_at or _now()
    with conn:
        conn.execute(
            "UPDATE items SET last_checked = ?, check_status = ?, current_price = ?, "
            "current_price_value = ? WHERE wish_id = ? AND source = ? AND item_id = ?",
            (
                checked_at,
                result.get("status", ""),
                result.get("current_price", ""),
                result.get("current_price_value"),
                wish_id,
                source,
                item_id,
            ),
        )


def finish_run(conn, wish_id, status_text):
    with conn:
        conn.execute(
            "UPDATE wishes SET last_run_at = ?, last_run_status = ? WHERE id = ?",
            (_now(), status_text, wish_id),
        )


def remove_gone_marked(conn, wish_id):
    """Entfernt markierte Artikel, die als 'gone' geprueft wurden."""
    with conn:
        cur = conn.execute(
            "DELETE FROM items WHERE wish_id = ? AND status = ? AND check_status = 'gone'",
            (wish_id, STATUS_MARKED),
        )
    return cur.rowcount


def export_csv(conn, wish_id):
    from favorites import items_to_csv

    items = get_items(conn, wish_id)
    return items_to_csv(items)
