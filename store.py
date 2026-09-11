"""
store.py — SQLite storage for pending / approved posts.

DB path: DATA_DIR/posts.db  (survives cloud restarts via persistent volume)
"""
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from config import DATA_DIR

_DB_PATH = Path(DATA_DIR) / "posts.db"

_CREATE = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    topic TEXT,
    source_tweets TEXT,
    generated_post TEXT,
    hashtags TEXT,
    hook TEXT,
    source_note TEXT,
    status TEXT,
    created_at TEXT,
    approved_at TEXT
)
"""


def _conn() -> sqlite3.Connection:
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # allow concurrent reads during writes
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(_CREATE)
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["source_tweets"] = json.loads(d["source_tweets"] or "[]")
    d["hashtags"] = json.loads(d["hashtags"] or "[]")
    return d


# ─────────────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────────────

def save_pending(topic: str, tweets: list[dict], generated: dict) -> str:
    """Save a generated post as pending. Returns the new post ID (UUID)."""
    post_id = str(uuid.uuid4())
    with _conn() as conn:
        conn.execute(
            """INSERT INTO posts
               (id, topic, source_tweets, generated_post, hashtags, hook,
                source_note, status, created_at, approved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                post_id,
                topic,
                json.dumps(tweets, ensure_ascii=False),
                generated.get("post", ""),
                json.dumps(generated.get("hashtags", []), ensure_ascii=False),
                generated.get("hook", topic),
                generated.get("source_note", ""),
                "pending",
                datetime.utcnow().isoformat(),
                None,
            ),
        )
    return post_id


# ─────────────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────────────

def load_post(post_id: str) -> dict | None:
    """Load a single post by ID."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_pending() -> list[dict]:
    """Return all pending posts sorted newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_approved() -> list[dict]:
    """Return all approved posts sorted newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status='approved' ORDER BY approved_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────

def approve(post_id: str) -> bool:
    """Mark a post as approved. Returns True on success."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE posts SET status='approved', approved_at=? WHERE id=? AND status='pending'",
            (datetime.utcnow().isoformat(), post_id),
        )
    return cur.rowcount > 0


def reject(post_id: str) -> bool:
    """Delete a pending post. Returns True on success."""
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM posts WHERE id=? AND status='pending'", (post_id,)
        )
    return cur.rowcount > 0
