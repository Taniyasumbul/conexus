"""SQLite persistence for negotiation state machines.

Each contract row holds the full NegotiationState as JSON (so any process can
resume it), the source text, the channel mode, and - in simulation mode - the
pickled simulated counterparty so its private state survives restarts."""
from __future__ import annotations

import pickle
import sqlite3
import threading
import time
from pathlib import Path

from .models import NegotiationState

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id            TEXT PRIMARY KEY,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    customer      TEXT NOT NULL,
    filename      TEXT,
    mode          TEXT NOT NULL DEFAULT 'none',   -- none | simulated | email
    status        TEXT NOT NULL,
    state_json    TEXT NOT NULL,
    text          TEXT NOT NULL,
    sim_blob      BLOB,
    sim_delay     REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_status ON contracts(status);
CREATE TABLE IF NOT EXISTS annotations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    clause_id      TEXT NOT NULL,
    annotator      TEXT NOT NULL,
    requires_human INTEGER,          -- 1 / 0 / NULL (skipped: unsure)
    level          TEXT,
    redlinable     INTEGER,
    note           TEXT,
    ts             REAL NOT NULL,
    UNIQUE (clause_id, annotator)
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('sales', 'legal', 'admin')),
    password_hash TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,          -- sha256 of the cookie token; the raw token is never stored
    user_id    INTEGER NOT NULL REFERENCES users(id),
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,          -- sha256 of the emailed token
    user_id    INTEGER NOT NULL REFERENCES users(id),
    purpose    TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
    expires_at REAL NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            cols = {r["name"] for r in self.db.execute("PRAGMA table_info(users)").fetchall()}
            if "email_verified" not in cols:  # migration: accounts that existed before sign-up are verified
                self.db.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1")
                self.db.commit()

    def create(self, st: NegotiationState, text: str, filename: str | None) -> None:
        now = time.time()
        with self.lock:
            self.db.execute(
                "INSERT INTO contracts (id, created_at, updated_at, customer, filename, status, state_json, text) VALUES (?,?,?,?,?,?,?,?)",
                (st.contract_id, now, now, st.context.customer, filename, st.status, st.model_dump_json(), text),
            )
            self.db.commit()

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
        with self.lock:
            self.db.execute(f"UPDATE contracts SET {', '.join(sets)} WHERE id=?", (*args, st.contract_id))
            self.db.commit()

    def row(self, cid: str) -> sqlite3.Row | None:
        with self.lock:
            return self.db.execute("SELECT * FROM contracts WHERE id=?", (cid,)).fetchone()

    def state(self, cid: str) -> NegotiationState | None:
        r = self.row(cid)
        return NegotiationState.model_validate_json(r["state_json"]) if r else None

    def sim(self, cid: str):
        r = self.row(cid)
        # Only objects this process pickled itself are ever stored here.
        return pickle.loads(r["sim_blob"]) if r and r["sim_blob"] else None

    # ------------------------------------------------------------ annotations
    def annotate(self, clause_id: str, annotator: str, requires_human: bool | None, level: str | None,
                 redlinable: bool | None, note: str) -> None:
        with self.lock:
            self.db.execute(
                "INSERT INTO annotations (clause_id, annotator, requires_human, level, redlinable, note, ts) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(clause_id, annotator) DO UPDATE SET requires_human=excluded.requires_human, level=excluded.level, "
                "redlinable=excluded.redlinable, note=excluded.note, ts=excluded.ts",
                (clause_id, annotator, None if requires_human is None else int(requires_human), level,
                 None if redlinable is None else int(redlinable), note, time.time()),
            )
            self.db.commit()

    def annotations(self) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute("SELECT * FROM annotations ORDER BY ts").fetchall()

    # ------------------------------------------------------------ users & sessions
    def _q(self, sql: str, args: tuple = (), one: bool = False, commit: bool = False):
        with self.lock:
            cur = self.db.execute(sql, args)
            if commit:
                self.db.commit()
                return cur.lastrowid
            return cur.fetchone() if one else cur.fetchall()

    def user_count(self) -> int:
        return self._q("SELECT COUNT(*) AS n FROM users", one=True)["n"]

    def create_user(self, email: str, name: str, role: str, password_hash: str, verified: bool = True) -> int:
        return self._q("INSERT INTO users (email, name, role, password_hash, created_at, email_verified) VALUES (?,?,?,?,?,?)",
                       (email.strip().lower(), name.strip(), role, password_hash, time.time(), int(verified)), commit=True)

    def set_verified(self, uid: int) -> None:
        self._q("UPDATE users SET email_verified=1 WHERE id=?", (uid,), commit=True)

    def create_email_token(self, token_hash: str, uid: int, purpose: str, expires_at: float) -> None:
        # one live token per user and purpose: older links stop working
        self._q("UPDATE email_tokens SET used=1 WHERE user_id=? AND purpose=? AND used=0", (uid, purpose), commit=True)
        self._q("INSERT INTO email_tokens (token_hash, user_id, purpose, expires_at) VALUES (?,?,?,?)",
                (token_hash, uid, purpose, expires_at), commit=True)

    def consume_email_token(self, token_hash: str, purpose: str):
        """Return the user for a valid, unused, unexpired token and mark it used; otherwise None."""
        with self.lock:
            row = self.db.execute("SELECT * FROM email_tokens WHERE token_hash=? AND purpose=? AND used=0 AND expires_at>?",
                                  (token_hash, purpose, time.time())).fetchone()
            if not row:
                return None
            self.db.execute("UPDATE email_tokens SET used=1 WHERE token_hash=?", (token_hash,))
            self.db.commit()
            return self.db.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()

    def user_by_email(self, email: str):
        return self._q("SELECT * FROM users WHERE email=?", (email.strip().lower(),), one=True)

    def user_by_id(self, uid: int):
        return self._q("SELECT * FROM users WHERE id=?", (uid,), one=True)

    def users(self):
        return self._q("SELECT id, email, name, role, active, created_at FROM users ORDER BY created_at")

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

    def all(self) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute("SELECT * FROM contracts ORDER BY created_at DESC").fetchall()
