"""Audit Agent (RO4): append-only, hash-chained decision log.

Every event stores the SHA-256 of the previous event, so any after-the-fact
edit, deletion or reordering breaks the chain and is detected by `verify()`.
The head hash can be anchored externally (e-mail to compliance, a git commit,
or a public blockchain) to make the whole log tamper-evident.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _digest(event: dict) -> str:
    body = {k: v for k, v in event.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


class AuditAgent:
    name = "audit"

    def __init__(self, path: str | Path | None = None, enabled: bool = True, sink: Any = None):
        """sink: optional object with audit_load() / audit_append(event), e.g. the Store when
        DATABASE_URL is set, so the chain survives restarts on hosts with ephemeral disks."""
        self.enabled = enabled
        self.path = Path(path) if path and sink is None else None
        self.sink = sink
        self.events: list[dict] = []
        self.head = GENESIS
        self._lock = threading.Lock()
        if sink is not None:
            self.events = sink.audit_load()
            if self.events:
                self.head = self.events[-1]["hash"]
        elif self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                for line in self.path.read_text().splitlines():
                    if line.strip():
                        self.events.append(json.loads(line))
                if self.events:
                    self.head = self.events[-1]["hash"]

    def log(self, agent: str, action: str, rationale: str, data: Any = None, contract_id: str | None = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._append(agent, action, rationale, data, contract_id)

    def _append(self, agent, action, rationale, data, contract_id) -> None:
        event = {
            "seq": len(self.events),
            "ts": time.time(),
            "contract_id": contract_id,
            "agent": agent,
            "action": action,
            "rationale": rationale,
            "data": data,
            "prev_hash": self.head,
        }
        event["hash"] = _digest(event)
        self.head = event["hash"]
        self.events.append(event)
        if self.sink is not None:
            self.sink.audit_append(event)
        elif self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")

    @staticmethod
    def verify_chain(events: list[dict]) -> tuple[bool, str]:
        prev = GENESIS
        for i, ev in enumerate(events):
            if ev.get("prev_hash") != prev:
                return False, f"chain broken at seq {i}: prev_hash mismatch"
            if _digest(json.loads(json.dumps(ev, default=str))) != ev.get("hash"):
                return False, f"event {i} was modified (hash mismatch)"
            prev = ev["hash"]
        return True, f"OK - chain intact, head={prev[:16]}..."

    def verify_stored(self) -> tuple[bool, str]:
        """Verify what is actually persisted (database or file), not just memory."""
        if self.sink is not None:
            return self.verify_chain(self.sink.audit_load())
        if self.path and self.path.exists():
            return self.verify(self.path)
        return True, "empty log"

    @staticmethod
    def verify(path: str | Path) -> tuple[bool, str]:
        prev = GENESIS
        for i, line in enumerate(Path(path).read_text().splitlines()):
            if not line.strip():
                continue
            ev = json.loads(line)
            if ev.get("prev_hash") != prev:
                return False, f"chain broken at seq {i}: prev_hash mismatch"
            if _digest(ev) != ev.get("hash"):
                return False, f"event {i} was modified (hash mismatch)"
            prev = ev["hash"]
        return True, f"OK - chain intact, head={prev[:16]}..."

    def report(self, contract_id: str | None = None) -> str:
        """Human-readable decision trail for a reviewer / compliance officer."""
        lines = []
        for ev in self.events:
            if contract_id and ev["contract_id"] != contract_id:
                continue
            lines.append(f"[{ev['seq']:03d}] {ev['agent']:<14} {ev['action']:<22} {ev['rationale']}")
        return "\n".join(lines)
