import os
import sqlite3
from datetime import datetime
from typing import Optional

from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id  INTEGER PRIMARY KEY,
            timezone TEXT NOT NULL DEFAULT 'Europe/Moscow'
        );

        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            summary    TEXT    NOT NULL,
            event_dt   TEXT    NOT NULL,  -- ISO8601, aware datetime
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS reminders_sent (
            event_id        INTEGER NOT NULL,
            remind_minutes  INTEGER NOT NULL,
            PRIMARY KEY (event_id, remind_minutes)
        );
    ''')
    conn.commit()
    conn.close()


# ── Пользователи ──────────────────────────────────────────────────────────────

def ensure_user(user_id: int):
    conn = get_connection()
    conn.execute(
        'INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,)
    )
    conn.commit()
    conn.close()


def get_timezone(user_id: int) -> str:
    conn = get_connection()
    row = conn.execute('SELECT timezone FROM users WHERE user_id=?', (user_id,)).fetchone()
    conn.close()
    return row['timezone'] if row else 'Europe/Moscow'


def set_timezone(user_id: int, tz: str):
    conn = get_connection()
    conn.execute('UPDATE users SET timezone=? WHERE user_id=?', (tz, user_id))
    conn.commit()
    conn.close()


# ── События ───────────────────────────────────────────────────────────────────

def add_event(user_id: int, summary: str, event_dt: datetime) -> int:
    """Добавляет событие, возвращает его id."""
    conn = get_connection()
    cur = conn.execute(
        'INSERT INTO events (user_id, summary, event_dt) VALUES (?, ?, ?)',
        (user_id, summary, event_dt.isoformat()),
    )
    event_id = cur.lastrowid
    conn.commit()
    conn.close()
    return event_id


def get_upcoming_events(user_id: int, limit: int = 10) -> list:
    """Возвращает ближайшие события пользователя (ещё не прошедшие)."""
    conn = get_connection()
    rows = conn.execute(
        '''SELECT * FROM events
           WHERE user_id=? AND event_dt >= datetime('now')
           ORDER BY event_dt ASC LIMIT ?''',
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_upcoming_events() -> list:
    """Все будущие события всех пользователей (для планировщика напоминаний)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM events WHERE event_dt >= datetime('now') ORDER BY event_dt ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_event(event_id: int, user_id: int) -> bool:
    """Удаляет событие. Возвращает True если строка была удалена."""
    conn = get_connection()
    cur = conn.execute(
        'DELETE FROM events WHERE id=? AND user_id=?', (event_id, user_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ── Напоминания ───────────────────────────────────────────────────────────────

def reminder_already_sent(event_id: int, remind_minutes: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        'SELECT 1 FROM reminders_sent WHERE event_id=? AND remind_minutes=?',
        (event_id, remind_minutes),
    ).fetchone()
    conn.close()
    return row is not None


def mark_reminder_sent(event_id: int, remind_minutes: int):
    conn = get_connection()
    conn.execute(
        'INSERT OR IGNORE INTO reminders_sent (event_id, remind_minutes) VALUES (?, ?)',
        (event_id, remind_minutes),
    )
    conn.commit()
    conn.close()
