"""Memory Agent (RO3): retrieve and rank analogous historical CRM deals."""
from __future__ import annotations

import math

import numpy as np

from ..integrations.crm import CRMStore
from ..models import DealContext, DealRecord


class MemoryAgent:
    name = "memory"

    def __init__(self, crm: CRMStore, k: int = 25):
        self.crm = crm
        self.k = k

    @staticmethod
    def similarity(ctx: DealContext, d: DealRecord) -> float:
        s = 0.0
        s += 2.0 if d.segment == ctx.segment else 0.0
        s += 1.5 if d.region == ctx.region else 0.0
        s += 1.0 if d.product == ctx.product else 0.0
        s += 1.0 * math.exp(-abs(math.log((d.seats + 1) / (ctx.seats + 1))))
        return s / 5.5

    def retrieve(self, ctx: DealContext) -> list[tuple[DealRecord, float]]:
        scored = [(d, self.similarity(ctx, d)) for d in self.crm.deals]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: self.k]

    def estimate_wtp_ratio(self, ctx: DealContext) -> tuple[float | None, list[str]]:
        """Estimate counterparty WTP as a ratio of list price from similar deals.

        Won deals give a lower bound on WTP (they paid it); lost deals give an
        upper bound (they refused it). Estimate = midpoint between the weighted
        upper quantile of won ratios and the lower quantile of lost ratios.
        """
        hits = self.retrieve(ctx)
        if not hits:
            return None, ["no CRM history (cold start)"]
        won = [(d.price_ratio, w) for d, w in hits if d.won]
        lost = [(d.price_ratio, w) for d, w in hits if not d.won]
        evidence = [f"{len(hits)} similar deals ({len(won)} won / {len(lost)} lost), "
                    f"top match {hits[0][0].deal_id} sim={hits[0][1]:.2f}"]
        hi_won = _wquantile(won, 0.8) if won else None
        lo_lost = _wquantile(lost, 0.2) if lost else None
        if hi_won and lo_lost:
            est = (hi_won + lo_lost) / 2 if lo_lost > hi_won else hi_won
        else:
            est = hi_won or (lo_lost * 0.9 if lo_lost else None)
        if est:
            evidence.append(f"won ratio p80={hi_won or float('nan'):.2f}, lost ratio p20={lo_lost or float('nan'):.2f} -> WTP≈{est:.2f}x list")
        return est, evidence


def _wquantile(pairs: list[tuple[float, float]], q: float) -> float:
    vals = np.array([p[0] for p in pairs])
    w = np.array([p[1] for p in pairs])
    order = np.argsort(vals)
    vals, w = vals[order], w[order]
    cdf = np.cumsum(w) / w.sum()
    return float(vals[np.searchsorted(cdf, q, side="left").clip(0, len(vals) - 1)])
