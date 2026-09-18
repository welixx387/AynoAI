# db.py
# Хранилище диалогов и сообщений на SQLite (один файл chat_history.db рядом
# с проектом). Позволяет вести несколько отдельных диалогов и не терять
# историю при перезапуске сервера — в отличие от Streamlit-версии, где
# история жила только в рамках одной сессии браузера.

import datetime
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).parent / "chat_history.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def create_conversation(title: str = "Новый диалог") -> Dict:
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, now, now),
    )
    conn.commit()
    conv_id = cur.lastrowid
    conn.close()
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}


def list_conversations() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_conversation(conv_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
        (conv_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def rename_conversation(conv_id: int, title: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, _now(), conv_id),
    )
    conn.commit()
    conn.close()


def touch_conversation(conv_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (_now(), conv_id))
    conn.commit()
    conn.close()


def delete_conversation(conv_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()


def add_message(conv_id: int, role: str, content: str) -> Dict:
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, now),
    )
    conn.commit()
    msg_id = cur.lastrowid
    conn.close()
    touch_conversation(conv_id)
    return {
        "id": msg_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "created_at": now,
    }


def get_messages(conv_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
