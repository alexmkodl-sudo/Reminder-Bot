"""
db/models.py — работа с SQLite.

Особенности:
  - Одно соединение на поток (threading.local) + WAL-режим вместо per-call connect/close.
    WAL устраняет "database is locked" при параллельных читателях/писателе.
  - Версионирование схемы: таблица schema_version + список миграций.
    Новые ALTER TABLE добавляются как новые элементы MIGRATIONS — без ручного вмешательства в БД.
  - Все события хранятся в UTC (ISO-8601 с +00:00).
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from config import DATABASE_PATH

# ── Connection pool (per-thread) ──────────────────────────────────────────────

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL: параллельные читатели не блокируют писателя
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


# ── Схема и миграции ──────────────────────────────────────────────────────────

_SCHEMA_V0 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
    user_id  INTEGER PRIMARY KEY,
    timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
    active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    summary      TEXT    NOT NULL,
    event_dt     TEXT    NOT NULL,
    recurrence   TEXT,                         -- NULL | 'daily' | 'weekly' | 'monthly'
    recur_until  TEXT,                         -- ISO date, до которой повторять
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    done         INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS reminders_sent (
    event_id        INTEGER NOT NULL,
    remind_minutes  INTEGER NOT NULL,
    PRIMARY KEY (event_id, remind_minutes)
);

INSERT OR IGNORE INTO schema_version VALUES (0);
"""

# Список миграций: (целевая версия, SQL)
# Чтобы добавить новую — просто дописать в конец.
MIGRATIONS: list[tuple[int, str]] = [
    # v1: индексы для ускорения выборок
    (1, """
        CREATE INDEX IF NOT EXISTS idx_events_user_dt ON events(user_id, event_dt);
        CREATE INDEX IF NOT EXISTS idx_events_dt      ON events(event_dt);
    """),
]


def init_db():
    conn = get_connection()
    conn.executescript(_SCHEMA_V0)
    conn.commit()

    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row[0] is not None else 0

    for target_ver, sql in MIGRATIONS:
        if current < target_ver:
            conn.executescript(sql)
            conn.execute("INSERT OR REPLACE INTO schema_version VALUES (?)", (target_ver,))
            conn.commit()
            current = target_ver


# ── Пользователи ──────────────────────────────────────────────────────────────

def ensure_user(user_id: int):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()


def get_timezone(user_id: int) -> str:
    conn = get_connection()
    row = conn.execute("SELECT timezone FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row["timezone"] if row else "Europe/Moscow"


def set_timezone(user_id: int, tz: str):
    conn = get_connection()
    conn.execute("UPDATE users SET timezone=? WHERE user_id=?", (tz, user_id))
    conn.commit()


def deactivate_user(user_id: int):
    """Помечает пользователя как заблокировавшего бота — напоминания прекращаются."""
    conn = get_connection()
    conn.execute("UPDATE users SET active=0 WHERE user_id=?", (user_id,))
    conn.commit()


def get_active_user_ids() -> set[int]:
    conn = get_connection()
    rows = conn.execute("SELECT user_id FROM users WHERE active=1").fetchall()
    return {r["user_id"] for r in rows}


# ── События ───────────────────────────────────────────────────────────────────

def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def add_event(
    user_id: int,
    summary: str,
    event_dt: datetime,
    recurrence: Optional[str] = None,
    recur_until: Optional[datetime] = None,
) -> int:
    conn = get_connection()
    dt_utc = _to_utc(event_dt)
    recur_until_s = _to_utc(recur_until).date().isoformat() if recur_until else None
    cur = conn.execute(
        "INSERT INTO events (user_id, summary, event_dt, recurrence, recur_until) VALUES (?,?,?,?,?)",
        (user_id, summary, dt_utc.isoformat(), recurrence, recur_until_s),
    )
    conn.commit()
    return cur.lastrowid


def get_upcoming_events(user_id: int, limit: int = 10) -> list[dict]:
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM events
           WHERE user_id=? AND event_dt >= ? AND done=0
           ORDER BY event_dt ASC LIMIT ?""",
        (user_id, now_utc, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_upcoming_events() -> list[dict]:
    """Только активных пользователей — не слать напоминания заблокировавшим бота."""
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    conn = get_connection()
    rows = conn.execute(
        """SELECT e.* FROM events e
           JOIN users u ON u.user_id = e.user_id
           WHERE e.event_dt >= ? AND e.done=0 AND u.active=1
           ORDER BY e.event_dt ASC""",
        (now_utc,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_event(event_id: int, user_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM events WHERE id=? AND user_id=?", (event_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def update_event(event_id: int, user_id: int, summary: str, event_dt: datetime) -> bool:
    conn = get_connection()
    dt_utc = _to_utc(event_dt)
    cur = conn.execute(
        "UPDATE events SET summary=?, event_dt=? WHERE id=? AND user_id=?",
        (summary, dt_utc.isoformat(), event_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def mark_event_done(event_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE events SET done=1 WHERE id=? AND user_id=?", (event_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0


def delete_event(event_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM events WHERE id=? AND user_id=?", (event_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0


def search_events(user_id: int, query: str, limit: int = 10) -> list[dict]:
    """Поиск по подстроке в названии (включая прошедшие)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM events
           WHERE user_id=? AND summary LIKE ? AND done=0
           ORDER BY event_dt ASC LIMIT ?""",
        (user_id, f"%{query}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats(user_id: int) -> dict:
    conn = get_connection()
    total = conn.execute(
        "SELECT COUNT(*) FROM events WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(*) FROM events WHERE user_id=? AND done=1", (user_id,)
    ).fetchone()[0]
    upcoming = conn.execute(
        "SELECT COUNT(*) FROM events WHERE user_id=? AND done=0 AND event_dt >= ?",
        (user_id, datetime.now(tz=timezone.utc).isoformat()),
    ).fetchone()[0]
    return {"total": total, "done": done, "upcoming": upcoming}


# ── Напоминания ───────────────────────────────────────────────────────────────

def reminder_already_sent(event_id: int, remind_minutes: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM reminders_sent WHERE event_id=? AND remind_minutes=?",
        (event_id, remind_minutes),
    ).fetchone()
    return row is not None


def mark_reminder_sent(event_id: int, remind_minutes: int):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO reminders_sent (event_id, remind_minutes) VALUES (?,?)",
        (event_id, remind_minutes),
    )
    conn.commit()
