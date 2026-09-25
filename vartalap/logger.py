import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).parent.parent / "logs" / "vartalap.db"


def init_db(db_path: Path = DB_PATH):
    """Initialize SQLite tables for logging if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                backend TEXT NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                duration_ms INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                thread_username TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                llm_reasoning TEXT,
                dry_run INTEGER NOT NULL,
                success INTEGER NOT NULL
            )
        """)
        conn.commit()


def log_llm_call(backend: str, prompt: str, response: str, duration_ms: Optional[int] = None):
    """Log an LLM prompt and raw response."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO llm_logs (timestamp, backend, prompt, response, duration_ms) VALUES (?, ?, ?, ?, ?)",
            (ts, backend, prompt, response, duration_ms or 0)
        )
        conn.commit()


def log_action(
    thread_username: str,
    action: str,
    details: str,
    llm_reasoning: Optional[str] = None,
    dry_run: bool = True,
    success: bool = True
):
    """Log an executed action or attempt."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO action_logs 
               (timestamp, thread_username, action, details, llm_reasoning, dry_run, success) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, thread_username, action, details, llm_reasoning or "", 1 if dry_run else 0, 1 if success else 0)
        )
        conn.commit()


def get_recent_logs(limit: int = 100, username: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve recent action logs."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if username:
            cursor.execute(
                """SELECT timestamp, thread_username, action, details, llm_reasoning, dry_run, success 
                   FROM action_logs WHERE thread_username = ? ORDER BY id DESC LIMIT ?""",
                (username, limit)
            )
        else:
            cursor.execute(
                """SELECT timestamp, thread_username, action, details, llm_reasoning, dry_run, success 
                   FROM action_logs ORDER BY id DESC LIMIT ?""",
                (limit,)
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_messages_sent_today_count() -> int:
    """Count non-dry-run reply actions sent today (UTC)."""
    init_db()
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) FROM action_logs 
               WHERE action = 'reply' AND dry_run = 0 AND success = 1 AND timestamp LIKE ?""",
            (f"{today_prefix}%",)
        )
        row = cursor.fetchone()
        return row[0] if row else 0
