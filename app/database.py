"""SQLite database setup and helpers."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from app.config import DB_PATH

_db_path: Optional[Path] = None


def get_db_path() -> Path:
    global _db_path
    if _db_path is None:
        _db_path = Path(__file__).parent.parent / DB_PATH
    return _db_path


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            published TEXT,
            summary TEXT,
            ai_summary TEXT,
            image_url TEXT,
            score INTEGER DEFAULT 0,
            fetched_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
        CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at);

        CREATE TABLE IF NOT EXISTS weather (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL,
            fetched_at REAL NOT NULL
        );
    """)
    # Migration: add image_url if missing (existing DB)
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()


# --- Weather helpers ---

def save_weather(data: dict):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO weather (id, data, fetched_at) VALUES (1, ?, ?)",
        (json.dumps(data), time.time()),
    )
    conn.commit()
    conn.close()


def load_weather() -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT data, fetched_at FROM weather WHERE id = 1").fetchone()
    conn.close()
    if row:
        return json.loads(row["data"])
    return None


# --- Article helpers ---

def save_articles(articles: list[dict]):
    conn = get_conn()
    for a in articles:
        conn.execute(
            """INSERT OR IGNORE INTO articles
               (source, category, title, url, published, summary, image_url, score, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                a["source"],
                a["category"],
                a["title"],
                a["url"],
                a.get("published"),
                a.get("summary"),
                a.get("image_url"),
                a.get("score", 0),
                time.time(),
            ),
        )
    conn.commit()
    conn.close()


def load_articles(category: str, limit: int = 15) -> list[dict]:
    conn = get_conn()
    # Prioritize articles with images first (for featured cards), then by recency/score
    rows = conn.execute(
        """SELECT source, title, url, published, summary, ai_summary, image_url, score
           FROM articles
           WHERE category = ?
           ORDER BY (image_url IS NOT NULL) DESC, fetched_at DESC, score DESC
           LIMIT ?""",
        (category, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unsummarized_articles(limit: int = 5) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, title, summary FROM articles
           WHERE ai_summary IS NULL
           ORDER BY fetched_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_ai_summary(article_id: int, summary: str):
    conn = get_conn()
    conn.execute(
        "UPDATE articles SET ai_summary = ? WHERE id = ?",
        (summary, article_id),
    )
    conn.commit()
    conn.close()
