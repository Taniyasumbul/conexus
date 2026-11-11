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

    def all(self) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute("SELECT * FROM contracts ORDER BY created_at DESC").fetchall()
