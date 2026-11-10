"""Generative model of the market. Used to (1) synthesise CRM history and
(2) sample counterparties for simulation, so that historical deals carry real
signal about counterparties' willingness-to-pay (WTP) - which is what RO3 tests."""
from __future__ import annotations

import random

from ..models import DealContext

LIST_PER_SEAT = {"core": 120.0, "pro": 240.0, "suite": 480.0}  # USD / seat / year
SEGMENT_SEATS = {"startup": (5, 40), "smb": (20, 150), "mid_market": (100, 600), "enterprise": (500, 3000)}
# How WTP relates to list price, by segment and region (hidden from the agent)
SEGMENT_WTP = {"startup": 0.62, "smb": 0.80, "mid_market": 0.98, "enterprise": 1.18}
REGION_WTP = {"india": 0.85, "us": 1.08, "eu": 1.0, "apac": 0.92}
SEGMENT_MIX = {"startup": 0.30, "smb": 0.35, "mid_market": 0.25, "enterprise": 0.10}

COMPANY_A = ["Apex", "Nimbus", "Vertex", "Quanta", "Orbit", "Lumen", "Kite", "Saffron", "Indigo", "Banyan", "Helix", "Cobalt"]
COMPANY_B = ["Labs", "Systems", "Retail", "Health", "Logistics", "Fintech", "Foods", "Mobility", "Analytics", "Works"]


def sample_context(rng: random.Random) -> DealContext:
    segment = rng.choices(list(SEGMENT_MIX), weights=list(SEGMENT_MIX.values()))[0]
    region = rng.choice(list(REGION_WTP))
    product = rng.choices(["core", "pro", "suite"], weights=[0.45, 0.4, 0.15])[0]
    lo, hi = SEGMENT_SEATS[segment]
    seats = rng.randint(lo, hi)
    return DealContext(
        customer=f"{rng.choice(COMPANY_A)} {rng.choice(COMPANY_B)}",
        segment=segment,
        region=region,
        product=product,
        seats=seats,
        list_price=round(LIST_PER_SEAT[product] * seats, 2),
    )


def sample_wtp(ctx: DealContext, rng: random.Random) -> float:
    """Counterparty's private reservation price (max annual price they will pay)."""
    volume = 1.0 - min(0.15, 0.03 * (ctx.seats / 500))  # mild volume discount expectation
    noise = rng.lognormvariate(0, 0.10)
    return ctx.list_price * SEGMENT_WTP[ctx.segment] * REGION_WTP[ctx.region] * volume * noise
