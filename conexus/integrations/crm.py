"""CRM adapter. CSVCRM is the default; swap in a HubSpot/Salesforce adapter that
returns the same DealRecord objects for a live deployment."""
from __future__ import annotations

import csv
from pathlib import Path

from ..models import DealRecord


class CRMStore:
    def __init__(self, deals: list[DealRecord] | None = None):
        self.deals = deals or []

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
