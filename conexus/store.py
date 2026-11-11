"""Persistence for negotiation state machines, accounts and the audit chain.

Backends
  SQLite      default; a local file (runs/conexus.db)
  PostgreSQL  when DATABASE_URL is set (e.g. a free Neon or Supabase database), so
              data survives restarts and redeploys on hosts with ephemeral disks

Each contract row holds the full NegotiationState as JSON (so any process can resume
it), the source text, the channel mode, and - in simulation mode - the pickled
simulated counterparty so its private state survives restarts. Only objects this
process pickled itself are ever stored there.
"""
from __future__ import annotations

import json
import pickle
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import NegotiationState

# Portable schema. {ID} {BLOB} {TS} are filled per dialect: timestamps need DOUBLE PRECISION
# on Postgres (REAL there is 4-byte and would round epoch seconds).
SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id            TEXT PRIMARY KEY,
    created_at    {TS} NOT NULL,
    updated_at    {TS} NOT NULL,
    customer      TEXT NOT NULL,
    filename      TEXT,
    mode          TEXT NOT NULL DEFAULT 'none',
    status        TEXT NOT NULL,
    state_json    TEXT NOT NULL,
    text          TEXT NOT NULL,
    sim_blob      {BLOB},
    sim_delay     {TS} DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_status ON contracts(status);
CREATE TABLE IF NOT EXISTS annotations (
    id             {ID},
    clause_id      TEXT NOT NULL,
    annotator      TEXT NOT NULL,
    requires_human INTEGER,
    level          TEXT,
    redlinable     INTEGER,
    note           TEXT,
    ts             {TS} NOT NULL,
    UNIQUE (clause_id, annotator)
);
CREATE TABLE IF NOT EXISTS users (
    id             {ID},
    email          TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('sales', 'legal', 'admin')),
    password_hash  TEXT NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     {TS} NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    expires_at {TS} NOT NULL
);
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    purpose    TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
    expires_at {TS} NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    seq   INTEGER PRIMARY KEY,
    event TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id         {ID},
    user_id    INTEGER,
    role       TEXT,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    link       TEXT,
    created_at {TS} NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_reads (
    notification_id INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    PRIMARY KEY (notification_id, user_id)
);
"""
DIALECT = {
    "sqlite": {"ID": "INTEGER PRIMARY KEY AUTOINCREMENT", "BLOB": "BLOB", "TS": "REAL"},
    "postgres": {"ID": "BIGSERIAL PRIMARY KEY", "BLOB": "BYTEA", "TS": "DOUBLE PRECISION"},
}


class _DB:
    """Tiny adapter: '?' placeholders everywhere, rows addressable by column name."""

    def __init__(self, path: Path | None, url: str | None):
        self.url = url
        self.kind = "postgres" if url else "sqlite"
        self.path = path
        self.conn: Any = None
        self._connect()

    def _connect(self) -> None:
        if self.kind == "postgres":
            import psycopg
            from psycopg.rows import dict_row

            self.conn = psycopg.connect(self.url, autocommit=True, row_factory=dict_row)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.kind == "postgres" else sql

    def run(self, sql: str, args: tuple = (), fetch: str | None = None):
        """fetch: None | 'one' | 'all'. Reconnects once if a hosted Postgres dropped the connection."""
        for attempt in (0, 1):
            try:
                cur = self.conn.execute(self._sql(sql), args)
                out = cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
                if self.kind == "sqlite":
                    self.conn.commit()
                return out
            except Exception as e:  # noqa: BLE001 - narrowed below
                if self.kind == "postgres" and attempt == 0 and _is_connection_error(e):
                    self._connect()
                    continue
                raise

    def insert_id(self, sql: str, args: tuple) -> int:
        if self.kind == "postgres":
            return self.run(sql + " RETURNING id", args, fetch="one")["id"]
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur.lastrowid

    def script(self, sql: str) -> None:
        sql = sql.format(**DIALECT[self.kind])
        if self.kind == "sqlite":
            self.conn.executescript(sql)
        else:
            for stmt in (s.strip() for s in sql.split(";")):
                if stmt:
                    self.conn.execute(stmt)

    def columns(self, table: str) -> set[str]:
        if self.kind == "sqlite":
            return {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        rows = self.run("SELECT column_name FROM information_schema.columns WHERE table_name=?", (table,), fetch="all")
        return {r["column_name"] for r in rows}


def _is_connection_error(e: Exception) -> bool:
    try:
        import psycopg

        return isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError))
    except ImportError:
        return False


class Store:
    def __init__(self, path: str | Path | None = None, url: str | None = None):
        self.path = Path(path) if path else None
        self.lock = threading.RLock()
        self.db = _DB(self.path, url)
        with self.lock:
            self.db.script(SCHEMA)
            if "email_verified" not in self.db.columns("users"):  # migration for pre-sign-up databases
                self.db.run("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1")

    @property
    def backend(self) -> str:
        return self.db.kind

    def _q(self, sql: str, args: tuple = (), one: bool = False, commit: bool = False):
        with self.lock:
            return self.db.run(sql, args, fetch=None if commit else "one" if one else "all")

    # ------------------------------------------------------------ contracts
    def create(self, st: NegotiationState, text: str, filename: str | None) -> None:
        now = time.time()
        self._q("INSERT INTO contracts (id, created_at, updated_at, customer, filename, status, state_json, text) VALUES (?,?,?,?,?,?,?,?)",
                (st.contract_id, now, now, st.context.customer, filename, st.status, st.model_dump_json(), text), commit=True)

    def save(self, st: NegotiationState, *, sim=None, mode: str | None = None, sim_delay: float | None = None) -> None:
        sets, args = ["updated_at=?", "status=?", "state_json=?"], [time.time(), st.status, st.model_dump_json()]
        if sim is not None:
            sets.append("sim_blob=?")
            args.append(pickle.dumps(sim))
        if mode is not None:
            sets.append("mode=?")
            args.append(mode)
        if sim_delay is not None:
            sets.append("sim_delay=?")
            args.append(sim_delay)
        self._q(f"UPDATE contracts SET {', '.join(sets)} WHERE id=?", (*args, st.contract_id), commit=True)

    def row(self, cid: str):
        return self._q("SELECT * FROM contracts WHERE id=?", (cid,), one=True)

    def state(self, cid: str) -> NegotiationState | None:
        r = self.row(cid)
        return NegotiationState.model_validate_json(r["state_json"]) if r else None

    def sim(self, cid: str):
        r = self.row(cid)
        return pickle.loads(bytes(r["sim_blob"])) if r and r["sim_blob"] else None

    def all(self):
        return self._q("SELECT * FROM contracts ORDER BY created_at DESC")

    # ------------------------------------------------------------ annotations
    def annotate(self, clause_id: str, annotator: str, requires_human: bool | None, level: str | None,
                 redlinable: bool | None, note: str) -> None:
        self._q("INSERT INTO annotations (clause_id, annotator, requires_human, level, redlinable, note, ts) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(clause_id, annotator) DO UPDATE SET requires_human=excluded.requires_human, level=excluded.level, "
                "redlinable=excluded.redlinable, note=excluded.note, ts=excluded.ts",
                (clause_id, annotator, None if requires_human is None else int(requires_human), level,
                 None if redlinable is None else int(redlinable), note, time.time()), commit=True)

    def annotations(self):
        return self._q("SELECT * FROM annotations ORDER BY ts")

    # ------------------------------------------------------------ users & sessions
    def user_count(self) -> int:
        return self._q("SELECT COUNT(*) AS n FROM users", one=True)["n"]

    def create_user(self, email: str, name: str, role: str, password_hash: str, verified: bool = True) -> int:
        with self.lock:
            return self.db.insert_id("INSERT INTO users (email, name, role, password_hash, created_at, email_verified) VALUES (?,?,?,?,?,?)",
                                     (email.strip().lower(), name.strip(), role, password_hash, time.time(), int(verified)))

    def set_verified(self, uid: int) -> None:
        self._q("UPDATE users SET email_verified=1 WHERE id=?", (uid,), commit=True)

    def create_email_token(self, token_hash: str, uid: int, purpose: str, expires_at: float) -> None:
        # one live token per user and purpose: older links stop working
        with self.lock:
            self.db.run("UPDATE email_tokens SET used=1 WHERE user_id=? AND purpose=? AND used=0", (uid, purpose))
            self.db.run("INSERT INTO email_tokens (token_hash, user_id, purpose, expires_at) VALUES (?,?,?,?)",
                        (token_hash, uid, purpose, expires_at))

    def consume_email_token(self, token_hash: str, purpose: str):
        """Return the user for a valid, unused, unexpired token and mark it used; otherwise None."""
        with self.lock:
            row = self.db.run("SELECT * FROM email_tokens WHERE token_hash=? AND purpose=? AND used=0 AND expires_at>?",
                              (token_hash, purpose, time.time()), fetch="one")
            if not row:
                return None
            self.db.run("UPDATE email_tokens SET used=1 WHERE token_hash=?", (token_hash,))
            return self.db.run("SELECT * FROM users WHERE id=?", (row["user_id"],), fetch="one")

    def user_by_email(self, email: str):
        return self._q("SELECT * FROM users WHERE email=?", (email.strip().lower(),), one=True)

    def user_by_id(self, uid: int):
        return self._q("SELECT * FROM users WHERE id=?", (uid,), one=True)

    def users(self):
        return self._q("SELECT id, email, name, role, active, created_at FROM users ORDER BY created_at")

    def users_with_role(self, roles: tuple[str, ...]):
        marks = ",".join("?" for _ in roles)
        return self._q(f"SELECT id, email, name, role FROM users WHERE active=1 AND role IN ({marks})", roles)

    def update_user(self, uid: int, **fields) -> None:
        allowed = {k: v for k, v in fields.items() if k in ("name", "role", "active", "password_hash") and v is not None}
        if allowed:
            sets = ", ".join(f"{k}=?" for k in allowed)
            self._q(f"UPDATE users SET {sets} WHERE id=?", (*allowed.values(), uid), commit=True)
        if fields.get("active") == 0 or fields.get("password_hash"):
            self._q("DELETE FROM sessions WHERE user_id=?", (uid,), commit=True)  # force re-login

    def create_session(self, token_hash: str, uid: int, expires_at: float) -> None:
        self._q("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)", (token_hash, uid, expires_at), commit=True)

    def session_user(self, token_hash: str):
        return self._q("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                       "WHERE s.token_hash=? AND s.expires_at > ? AND u.active = 1", (token_hash, time.time()), one=True)

    def delete_session(self, token_hash: str) -> None:
        self._q("DELETE FROM sessions WHERE token_hash=?", (token_hash,), commit=True)

    # ------------------------------------------------------------ key/value settings
    def kv_get(self, key: str) -> str | None:
        r = self._q("SELECT value FROM kv WHERE key=?", (key,), one=True)
        return r["value"] if r else None

    def kv_set(self, key: str, value: str) -> None:
        self._q("INSERT INTO kv (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value), commit=True)

    # ------------------------------------------------------------ audit chain (used when the disk is ephemeral)
    def audit_load(self) -> list[dict]:
        return [json.loads(r["event"]) for r in self._q("SELECT event FROM audit_events ORDER BY seq")]

    def audit_append(self, event: dict) -> None:
        self._q("INSERT INTO audit_events (seq, event) VALUES (?,?)", (event["seq"], json.dumps(event, default=str)), commit=True)

    # ------------------------------------------------------------ notifications
    def notify(self, kind: str, title: str, body: str, link: str | None = None,
               user_id: int | None = None, role: str | None = None) -> int:
        """Address a notification to one user (user_id), to everyone with at least `role`, or to everyone."""
        with self.lock:
            return self.db.insert_id("INSERT INTO notifications (user_id, role, kind, title, body, link, created_at) VALUES (?,?,?,?,?,?,?)",
                                     (user_id, role, kind, title, body, link, time.time()))

    def notifications_for(self, uid: int, roles: tuple[str, ...], limit: int = 30):
        marks = ",".join("?" for _ in roles)
        return self._q(
            "SELECT n.*, CASE WHEN r.user_id IS NULL THEN 0 ELSE 1 END AS is_read FROM notifications n "
            "LEFT JOIN notification_reads r ON r.notification_id = n.id AND r.user_id = ? "
            f"WHERE (n.user_id = ? OR (n.user_id IS NULL AND (n.role IS NULL OR n.role IN ({marks})))) "
            "ORDER BY n.created_at DESC LIMIT ?",
            (uid, uid, *roles, limit))

    def mark_read(self, uid: int, ids: list[int]) -> None:
        with self.lock:
            for nid in ids:
                self.db.run("INSERT INTO notification_reads (notification_id, user_id) VALUES (?,?) ON CONFLICT DO NOTHING", (nid, uid))
