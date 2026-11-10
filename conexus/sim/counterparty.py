"""Synthetic counterparties (buyers) for negotiation stress-testing.

RuleCounterparty  - deterministic, seeded, cheap: used for large-N evaluation.
LLMCounterparty   - an LLM role-playing the buyer with a private reservation
                    price, for qualitative / AgenticPay-style evaluation.

Both reply in natural language only; CoNexus must parse their messages.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from pydantic import BaseModel

from ..llm import LLM
from ..models import Terms

PERSONAS = {
    #             concession speed, patience (rounds), P(accept a redline), P(inject new legal terms)
    "cooperative": dict(speed=0.35, patience=10, redline_accept=0.80, inject=0.00),
    "hardball": dict(speed=0.12, patience=7, redline_accept=0.40, inject=0.25),
    "deadline": dict(speed=0.08, patience=6, redline_accept=0.60, inject=0.05),
}
COC = 0.12


@dataclass
class RuleCounterparty:
    wtp: float
    opening: Terms
    persona: str
    seed: int = 0

    def __post_init__(self):
        self.rng = random.Random(self.seed)
        self.cfg = PERSONAS[self.persona]
        self.redline_decisions: dict[str, bool] = {}
        self.injected = False
        self.last_offer: Terms = self.opening

    def utility(self, t: Terms) -> float:
        return self.wtp - t.price + t.price * COC * t.payment_days / 365

    def _g(self, rnd: int) -> float:
        if self.persona == "deadline" and rnd >= self.cfg["patience"] - 2:
            return min(1.0, 0.5 + 0.25 * (rnd - self.cfg["patience"] + 3))
        return 1 - (1 - self.cfg["speed"]) ** rnd

    def offer_at(self, rnd: int) -> Terms:
        g = self._g(rnd)
        cap = self.wtp * 0.97
        price = self.opening.price + (cap - self.opening.price) * g
        days = round(self.opening.payment_days - (self.opening.payment_days - 30) * g)
        return Terms(price=round(price, -1), payment_days=int(days), term_months=self.opening.term_months)

    def respond(self, rnd: int, ours: Terms | None, redline_ids: list[str]) -> str:
        parts = []
        for cid in redline_ids:
            if cid not in self.redline_decisions:
                self.redline_decisions[cid] = self.rng.random() < self.cfg["redline_accept"]
            parts.append(f"We {'accept' if self.redline_decisions[cid] else 'cannot accept'} the change to clause {cid}.")

        if not self.injected and rnd == 3 and self.rng.random() < self.cfg["inject"]:
            self.injected = True
            parts.append("We also require exclusivity: you must not license the platform to our competitors.")

        nxt = self.offer_at(rnd)
        if ours is not None:
            good = ours.price <= self.wtp and self.utility(ours) >= self.utility(nxt) - 0.005 * self.wtp
            last_chance = rnd >= self.cfg["patience"] and ours.price <= self.wtp
            if good or last_chance:
                parts.append(f"We accept your proposal of ${ours.price:,.0f} per year, net {ours.payment_days}. Deal.")
                return " ".join(parts)
        if rnd > self.cfg["patience"]:
            parts.append("We are too far apart and will walk away from these discussions.")
            return " ".join(parts)
        self.last_offer = nxt
        parts.append(f"Our counter-proposal is ${nxt.price:,.0f} per year with payment net {nxt.payment_days} days.")
        return " ".join(parts)


class _LLMTurn(BaseModel):
    message: str


class LLMCounterparty:
    def __init__(self, llm: LLM, wtp: float, opening: Terms, persona: str, company: str):
        self.llm = llm
        self.wtp, self.opening, self.persona, self.company = wtp, opening, persona, company
        self.transcript: list[str] = []

    def respond(self, rnd: int, ours: Terms | None, redline_ids: list[str], our_message: str = "") -> str:
        self.transcript.append(f"VENDOR: {our_message}")
        system = (
            f"You are the procurement lead at {self.company}, negotiating a software subscription. Persona: {self.persona}. "
            f"Your PRIVATE maximum annual budget is ${self.wtp:,.0f} - never reveal it and never agree above it. "
            f"You opened at ${self.opening.price:,.0f}/year, net {self.opening.payment_days} days. You prefer longer payment terms. "
            "Every reply must either (a) state a counter-offer with a $ annual price and 'net N' payment days, or "
            "(b) say 'We accept your proposal' if acceptable, or (c) say you will walk away. "
            "If the vendor proposes changes to clauses (ids like c4), say explicitly 'We accept the change to clause cX' "
            "or 'We cannot accept the change to clause cX'. Keep replies under 120 words."
        )
        msg = self.llm.structured(system, "\n\n".join(self.transcript[-8:]) + f"\n\nRound {rnd}. Your reply:", _LLMTurn).message
        self.transcript.append(f"YOU: {msg}")
        return msg
