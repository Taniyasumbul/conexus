"""CRM adapter. CSVCRM is the default; swap in a HubSpot/Salesforce adapter that
returns the same DealRecord objects for a live deployment."""
from __future__ import annotations

import csv
from pathlib import Path

from ..models import DealRecord


class CRMStore:
    def __init__(self, deals: list[DealRecord] | None = None, sink=None):
        self.deals = deals or []
        self.sink = None
        if sink is not None:
            self.attach(sink)

    def attach(self, sink) -> "CRMStore":
        """Persist write-backs through `sink` (crm_load / crm_append, e.g. the Store) and load the
        deals it already holds, so learned memory survives restarts and redeploys."""
        self.sink = sink
        known = {d.deal_id for d in self.deals}
        for row in sink.crm_load():
            if row["deal_id"] not in known:
                self.deals.append(DealRecord(**row))
                known.add(row["deal_id"])
        return self

    @classmethod
    def from_csv(cls, path: str | Path) -> "CRMStore":
        path = Path(path)
        if not path.exists():
            return cls([])
        with open(path) as f:
            rows = list(csv.DictReader(f))
        deals = [
            DealRecord(
                deal_id=r["deal_id"], segment=r["segment"], region=r["region"], product=r["product"],
                seats=int(r["seats"]), list_price=float(r["list_price"]), final_price=float(r["final_price"]),
                payment_days=int(r["payment_days"]), term_months=int(r["term_months"]),
                won=r["won"] in ("True", "true", "1"), rounds=int(r["rounds"]),
            )
            for r in rows
        ]
        return cls(deals)

    def record(self, deal: DealRecord) -> None:
        """Write back the outcome of a closed negotiation (memory grows over time)."""
        self.deals.append(deal)
        if self.sink is not None:
            self.sink.crm_append(deal.model_dump())
