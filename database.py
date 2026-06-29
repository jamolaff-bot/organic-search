import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent / "organic.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS operations (
                nop_id       TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                status       TEXT,
                state        TEXT,
                country      TEXT,
                certifier    TEXT,
                cert_url     TEXT,
                all_products TEXT,
                data_date    TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS ops_fts
                USING fts5(
                    all_products,
                    nop_id UNINDEXED,
                    name UNINDEXED,
                    content='operations',
                    content_rowid='rowid'
                );

            CREATE TRIGGER IF NOT EXISTS ops_ai AFTER INSERT ON operations BEGIN
                INSERT INTO ops_fts(rowid, all_products, nop_id, name)
                VALUES (new.rowid, new.all_products, new.nop_id, new.name);
            END;

            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)


def clear_and_rebuild_fts():
    with get_conn() as conn:
        conn.execute("DELETE FROM operations")
        conn.execute("INSERT INTO ops_fts(ops_fts) VALUES('rebuild')")


def bulk_insert(rows):
    with get_conn() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO operations
                (nop_id, name, status, state, country, certifier, cert_url, all_products, data_date)
            VALUES
                (:nop_id, :name, :status, :state, :country, :certifier, :cert_url, :all_products, :data_date)
        """, rows)


def set_meta(key: str, value: str):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))


def get_meta(key: str):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None


def search_ingredient(query, limit=500):
    """Full-text search across all product fields, returns matching operations."""
    safe = re.sub(r'["\'\*\(\)\[\]\{\}\^\$\|\\]', ' ', query).strip()
    if not safe:
        return []
    # Quote each word so they must all appear
    fts_query = " AND ".join(f'"{w}"' for w in safe.split() if w)
    if not fts_query:
        return []

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT o.nop_id, o.name, o.status, o.state, o.country,
                   o.certifier, o.cert_url, o.all_products,
                   snippet(ops_fts, 0, '<mark>', '</mark>', '…', 20) AS snippet
            FROM ops_fts
            JOIN operations o ON o.rowid = ops_fts.rowid
            WHERE ops_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit)).fetchall()
        return [dict(r) for r in rows]


def stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        return {
            "total_operations": total,
            "data_date": get_meta("data_date") or "not loaded",
            "loaded_at": get_meta("loaded_at") or "never",
        }
