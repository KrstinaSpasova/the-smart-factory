"""SQLite-backed long-term memory for HITL decisions and operator preferences."""
import os
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime

log = logging.getLogger(__name__)
DATABASE_PATH = os.getenv("DATABASE_PATH", "/app/data/memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ipc_id        TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    rationale     TEXT,
    status        TEXT    NOT NULL,
    operator_note TEXT,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)


def save_decision(ipc_id: str, action: str, rationale: str, status: str,
                  operator_note: str | None = None) -> int:
    """Persist an operator decision (approved/rejected/deferred) to SQLite and return the row id."""
    init_db()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO decisions (ipc_id, action, rationale, status, operator_note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (ipc_id, action, rationale, status, operator_note, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def load_past_decisions(ipc_id: str | None = None) -> list[dict]:
    """Load all past decisions from SQLite, optionally filtered to a single IPC."""
    init_db()
    with _conn() as c:
        if ipc_id:
            rows = c.execute(
                "SELECT * FROM decisions WHERE ipc_id = ? ORDER BY created_at DESC", (ipc_id,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM decisions ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_session_context(limit: int = 10) -> str:
    """Plain-text summary of recent decisions for injection into the Orchestrator system prompt."""
    decisions = load_past_decisions()[:limit]
    if not decisions:
        return "No prior decisions on record."
    lines = ["Recent operator decisions:"]
    for d in decisions:
        note = f" — note: {d['operator_note']}" if d.get("operator_note") else ""
        lines.append(
            f"- [{d['created_at'][:10]}] IPC={d['ipc_id']} action={d['action']} status={d['status']}{note}"
        )
    return "\n".join(lines)
