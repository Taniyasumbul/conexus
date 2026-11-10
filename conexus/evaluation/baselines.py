"""Baselines for RO5.

RuleBasedNegotiator  - no LLM, no memory, no risk gate: anchor at list price,
                       split-the-difference, sign whatever the customer drafted.
SingleLLMNegotiator  - one monolithic LLM that sees the whole contract and the
                       history and decides everything each round (no specialised
                       agents, no memory, no explicit escalation policy).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..agents.analyst import ContractAnalystAgent
from ..agents.communication import CommunicationAgent
from ..llm import LLM, LLMError
from ..models import DealContext, Outcome, EscalationDecision, Terms


class RuleBasedNegotiator:
    name = "rule_based"

    def __init__(self, max_discount: float = 0.45, max_rounds: int = 8):
        self.max_discount = max_discount
        self.max_rounds = max_rounds
        self.comms = CommunicationAgent(None)

    def run(self, contract_id: str, text: str, ctx: DealContext, cp) -> Outcome:
        _, opening = ContractAnalystAgent(None).analyze(text)
        floor = ctx.list_price * (1 - self.max_discount)
        ours = Terms(price=ctx.list_price, payment_days=30)
        theirs = opening
        for rnd in range(1, self.max_rounds + 1):
            if theirs and theirs.price >= floor and theirs.price >= ours.price * 0.98:
                return Outcome(status="agreed", final_terms=theirs, rounds=rnd)
            reply = self.comms.parse(cp.respond(rnd, ours, []), rnd, [])
            if reply.accept:
                return Outcome(status="agreed", final_terms=ours, rounds=rnd)
            if reply.walk_away:
                return Outcome(status="walked_away", rounds=rnd)
            if reply.terms:
                theirs = reply.terms
                mid = max(floor, (ours.price + theirs.price) / 2)
                ours = Terms(price=round(mid, 2), payment_days=min(60, max(30, (ours.payment_days + theirs.payment_days) // 2)))
        return Outcome(status="no_agreement", rounds=self.max_rounds)


class _Decision(BaseModel):
    action: Literal["offer", "accept", "escalate", "walk_away"]
    price: float
    payment_days: int
    reason: str


class SingleLLMNegotiator:
    name = "single_llm"

    def __init__(self, llm: LLM, max_discount: float = 0.45, max_rounds: int = 8):
        self.llm = llm
        self.max_discount = max_discount
        self.max_rounds = max_rounds
        self.comms = CommunicationAgent(None)

    def run(self, contract_id: str, text: str, ctx: DealContext, cp) -> Outcome:
        floor = ctx.list_price * (1 - self.max_discount)
        system = (
            "You negotiate B2B software contracts on behalf of a small vendor with no legal team. "
            f"List price is ${ctx.list_price:,.0f}/year; never go below ${floor:,.0f}. Prefer net 30 payment, max net 60. "
            "Maximise price while closing the deal. If the contract contains terms that need a lawyer, choose 'escalate'. "
            "Decide your next move each round."
        )
        history: list[str] = []
        last_ours: Terms | None = None
        for rnd in range(1, self.max_rounds + 1):
            prompt = f"Customer: {ctx.customer} ({ctx.segment}, {ctx.region}, {ctx.seats} seats)\n\nCONTRACT:\n{text}\n\n" \
                     f"NEGOTIATION SO FAR:\n" + ("\n".join(history) or "(none)") + f"\n\nRound {rnd}: your move."
            try:
                d = self.llm.structured(system, prompt, _Decision)
            except LLMError as e:
                return Outcome(status="no_agreement", rounds=rnd, escalation=EscalationDecision(escalate=False, triggers=[str(e)]))
            if d.action == "escalate":
                return Outcome(status="escalated", rounds=rnd - 1,
                               escalation=EscalationDecision(escalate=True, stage="in_negotiation", triggers=[d.reason]))
            if d.action == "walk_away":
                return Outcome(status="walked_away", rounds=rnd)
            if d.action == "accept" and history:
                theirs = self.comms.parse(history[-1], rnd, [])
                if theirs.terms:
                    return Outcome(status="agreed", final_terms=theirs.terms, rounds=rnd)
            ours = Terms(price=max(floor, d.price), payment_days=d.payment_days)
            last_ours = ours
            reply = cp.respond(rnd, ours, [])
            history += [f"YOU: ${ours.price:,.0f}/year, net {ours.payment_days}", f"CUSTOMER: {reply}"]
            parsed = self.comms.parse(reply, rnd, [])
            if parsed.accept:
                return Outcome(status="agreed", final_terms=last_ours, rounds=rnd)
            if parsed.walk_away:
                return Outcome(status="walked_away", rounds=rnd)
        return Outcome(status="no_agreement", rounds=self.max_rounds)
