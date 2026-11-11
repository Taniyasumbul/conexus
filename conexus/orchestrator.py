"""Negotiation Orchestrator: an event-driven state machine over NegotiationState.
It owns the escalation decision (the risk-gated autonomy boundary, RO2).

Events (each persists cleanly between calls, so the API can pause for hours):
    analyze(text)            -> status "analyzed"
    start(state)             -> "awaiting_reply" | "awaiting_human" | terminal
    on_reply(state, message) -> "awaiting_reply" | "awaiting_human" | terminal
    resolve(state, decision) -> human-in-the-loop resumes the machine

Escalation kinds and what a human "approve" means:
    risky_clause        (pre_negotiation) reviewer accepts the flagged clauses -> negotiate
    redline_rejected    (in_negotiation)  reviewer accepts clause as drafted   -> continue
    new_legal_terms     (in_negotiation)  reviewer accepts the new terms       -> continue
    no_deal_high_value  (in_negotiation)  a human takes over the deal          -> handed_off
    value_limit         (pre_signature)   reviewer approves the agreed deal    -> sign
"Reject" always closes the deal.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .agents.analyst import ContractAnalystAgent
from .agents.audit import AuditAgent
from .agents.communication import CommunicationAgent
from .agents.memory import MemoryAgent
from .agents.pricing import SalesPricingAgent
from .agents.risk import LegalRiskAgent, RiskClassifier
from .config import RUNS, Settings
from .integrations.channels import Channel, ConsoleChannel, ESignStub
from .integrations.crm import CRMStore
from .llm import LLM
from .models import (ClauseRisk, DealContext, DealRecord, EscalationDecision, HumanDecision, NegotiationState, Offer,
                     Outcome, RiskLevel, Terms)

TERMINAL = ("signed", "closed")


class Counterparty(Protocol):
    def respond(self, rnd: int, ours: Terms | None, redline_ids: list[str]) -> str: ...


class Orchestrator:
    def __init__(self, settings: Settings, llm: LLM | None = None, *, use_memory: bool = True,
                 use_risk_gate: bool = True, audit: AuditAgent | None = None, risk_mode: str = "hybrid",
                 classifier: RiskClassifier | None = None, crm: CRMStore | None = None,
                 outbound: Channel | None = None, escalations: Channel | None = None, out_dir: Path = RUNS,
                 learn: bool = False):
        self.s = settings
        self.use_risk_gate = use_risk_gate
        self.learn = learn  # write closed deals back to CRM memory
        self.audit = audit or AuditAgent(enabled=False)
        self.analyst = ContractAnalystAgent(llm)
        self.risk = LegalRiskAgent(settings, llm, classifier, mode=risk_mode)
        self.crm = crm or CRMStore.from_csv(settings.crm_path)
        self.memory = MemoryAgent(self.crm, settings.pricing.memory_k) if use_memory else None
        self.pricing = SalesPricingAgent(settings.pricing, self.memory)
        self.comms = CommunicationAgent(llm)
        self.outbound = outbound or ConsoleChannel(quiet=True)
        self.escalations = escalations or ConsoleChannel(quiet=True)
        self.esign = ESignStub(Path(out_dir) / "envelopes")

    # ================================================================== helpers
    def _log(self, st: NegotiationState, agent: str, action: str, why: str, data=None):
        self.audit.log(agent, action, why, data, contract_id=st.contract_id)

    def _redlines(self, st: NegotiationState) -> list[ClauseRisk]:
        return [r for r in st.risks if r.clause_id in st.pending_redlines]

    def _open_redlines(self, st: NegotiationState) -> list[ClauseRisk]:
        return [r for r in self._redlines(st) if r.clause_id not in st.redline_results]

    def _escalate(self, st: NegotiationState, stage: str, kind: str, triggers: list[str], score: float,
                  clause_ids: list[str] | None = None) -> NegotiationState:
        dec = EscalationDecision(escalate=True, stage=stage, kind=kind, triggers=triggers, score=round(score, 3),
                                 clause_ids=clause_ids or [])
        terms = st.agreed_terms or st.last_our_offer
        flagged = [r for r in st.risks if r.requires_human and r.clause_id not in st.reviewed_clauses]
        packet = (
            f"Contract {st.contract_id} with {st.context.customer} needs human review ({stage} / {kind}).\n"
            f"Triggers: {'; '.join(triggers)}\n"
            f"Current terms: {terms.model_dump() if terms else 'n/a'}\n"
            "Flagged clauses:\n" + ("\n".join(f"  - {r.clause_id} [{r.clause_type.value}] {', '.join(r.reasons) or r.level.value}"
                                             for r in flagged) or "  (none)")
        )
        self.escalations.send("legal-review", f"[CoNexus] Escalation: {st.contract_id}", packet)
        self._log(st, "orchestrator", "ESCALATE", "; ".join(triggers), dec.model_dump())
        st.status = "awaiting_human"
        st.escalation = dec
        st.outcome = Outcome(status="escalated", escalation=dec, final_terms=terms, rounds=st.round,
                             accepted_redlines=[c for c, ok in st.redline_results.items() if ok])
        return st

    # ================================================================== events
    def analyze(self, contract_id: str, text: str, ctx: DealContext) -> NegotiationState:
        st = NegotiationState(contract_id=contract_id, context=ctx)
        st.clauses, st.opening_terms = self.analyst.analyze(text)
        self._log(st, "contract_analyst", "EXTRACT_CLAUSES",
                  f"{len(st.clauses)} clauses; opening terms {st.opening_terms.model_dump() if st.opening_terms else 'not found'}",
                  [c.model_dump(include={'id', 'type', 'type_confidence'}) for c in st.clauses])
        st.risks = self.risk.assess_all(st.clauses)
        for r in st.risks:
            if r.level != RiskLevel.LOW or r.requires_human:
                self._log(st, "legal_risk", "FLAG_CLAUSE",
                          f"{r.clause_id} {r.clause_type.value}: level={r.level.value} score={r.score} "
                          f"human={r.requires_human} redlinable={r.redlinable}; {'; '.join(r.reasons)}")
        return st

    def pre_negotiation_gate(self, st: NegotiationState) -> EscalationDecision:
        if not self.use_risk_gate:
            return EscalationDecision(escalate=False)
        blocking = [r for r in st.risks if r.requires_human and not r.redlinable and r.clause_id not in st.reviewed_clauses]
        if blocking:
            return EscalationDecision(
                escalate=True, stage="pre_negotiation", kind="risky_clause", score=max(r.score for r in blocking),
                clause_ids=[r.clause_id for r in blocking],
                triggers=[f"{r.clause_id} ({r.clause_type.value}) requires human: {', '.join(r.reasons) or 'score ' + str(r.score)}" for r in blocking],
            )
        return EscalationDecision(escalate=False, score=max((r.score for r in st.risks), default=0.0))

    def start(self, st: NegotiationState) -> NegotiationState:
        gate = self.pre_negotiation_gate(st)
        if gate.escalate:
            return self._escalate(st, "pre_negotiation", "risky_clause", gate.triggers, gate.score, gate.clause_ids)

        if self.use_risk_gate:
            st.pending_redlines = [r.clause_id for r in st.risks
                                   if r.redlinable and r.level != RiskLevel.LOW and r.clause_id not in st.reviewed_clauses]
        if st.pending_redlines:
            self._log(st, "legal_risk", "PROPOSE_REDLINES", f"{len(st.pending_redlines)} autonomous redlines", st.pending_redlines)

        st.plan = self.pricing.plan(st.context)
        if self.memory:
            st.similar_deals = [d for d, _ in self.memory.retrieve(st.context)[:5]]
        self._log(st, "sales_pricing", "PRICING_PLAN",
                  f"anchor ${st.plan.anchor.price:,.0f}, floor ${st.plan.floor_price:,.0f}, limit ${st.plan.concession_limit:,.0f}; "
                  + " | ".join(st.plan.evidence), st.plan.model_dump())
        st.their_last = st.opening_terms
        if st.opening_terms:
            st.history.append(Offer(round=0, sender="them", terms=st.opening_terms, message="(opening terms as drafted in their contract)"))
        return self._next_turn(st)

    def _next_turn(self, st: NegotiationState) -> NegotiationState:
        max_rounds = self.s.escalation.max_rounds
        rnd = st.round + 1
        if rnd > max_rounds:
            return self._fail(st, f"no agreement after {max_rounds} rounds")
        ours = self.pricing.next_offer(st.plan, rnd, max_rounds, st.their_last)
        open_rl = self._open_redlines(st)
        ctx = st.context

        if st.their_last and not open_rl and self.pricing.acceptable(st.plan, st.their_last, ours):
            msg = self.comms.compose(st.their_last, rnd, accept=True, customer=ctx.customer)
            self.outbound.send(ctx.customer, "Re: Subscription agreement", msg)
            st.history.append(Offer(round=rnd, sender="us", terms=st.their_last, message=msg, accept=True))
            st.round = rnd
            self._log(st, "sales_pricing", "ACCEPT_OFFER",
                      f"their ${st.their_last.price:,.0f}/net{st.their_last.payment_days} >= our next ${ours.price:,.0f}")
            return self._agree(st, st.their_last)

        msg = self.comms.compose(ours, rnd, open_rl, customer=ctx.customer)
        self.outbound.send(ctx.customer, "Re: Subscription agreement", msg)
        st.history.append(Offer(round=rnd, sender="us", terms=ours, message=msg))
        st.round, st.last_our_offer = rnd, ours
        st.last_sent_redlines = [r.clause_id for r in open_rl]
        st.status = "awaiting_reply"
        self._log(st, "communication", "SEND_OFFER", f"round {rnd}: ${ours.price:,.0f}, net {ours.payment_days}",
                  {"redlines": st.last_sent_redlines})
        return st

    def on_reply(self, st: NegotiationState, message: str) -> NegotiationState:
        if st.status != "awaiting_reply":
            raise ValueError(f"contract {st.contract_id} is not awaiting a reply (status={st.status})")
        theirs = self.comms.parse(message, st.round, st.last_sent_redlines)
        st.history.append(theirs)
        self._log(st, "communication", "RECEIVE_REPLY", message[:300],
                  theirs.model_dump(include={'terms', 'accept', 'walk_away', 'redline_responses', 'new_legal_terms'}))
        esc = self.s.escalation

        for cid, ok in theirs.redline_responses.items():
            risk = next((r for r in self._redlines(st) if r.clause_id == cid), None)
            if risk is None:
                continue
            st.redline_results[cid] = ok
            if not ok and risk.requires_human and esc.escalate_on_rejected_redline and cid not in st.reviewed_clauses:
                return self._escalate(st, "in_negotiation", "redline_rejected",
                                      [f"redline on risk-critical clause {cid} rejected"], risk.score, [cid])
            self._log(st, "legal_risk", "REDLINE_" + ("ACCEPTED" if ok else "REJECTED"),
                      f"{cid}: " + ("resolved" if ok else "commercial term, accepted as drafted"))

        if theirs.terms:
            st.their_last = theirs.terms
        if theirs.new_legal_terms and esc.escalate_on_new_legal_terms and self.use_risk_gate:
            return self._escalate(st, "in_negotiation", "new_legal_terms", ["counterparty introduced new legal terms"], 0.9)
        if theirs.accept:
            return self._agree(st, st.last_our_offer)
        if theirs.walk_away:
            return self._fail(st, "counterparty walked away")
        return self._next_turn(st)

    def resolve(self, st: NegotiationState, decision: HumanDecision) -> NegotiationState:
        """Human-in-the-loop: apply a reviewer's decision to a pending escalation."""
        if st.status != "awaiting_human" or not st.escalation:
            raise ValueError(f"contract {st.contract_id} has no pending escalation")
        st.human_decisions.append(decision)
        kind = st.escalation.kind
        self._log(st, f"human:{decision.reviewer}", "APPROVE" if decision.approve else "REJECT",
                  f"{kind}: {decision.note or 'no note'}", decision.model_dump())
        st.escalation = None
        if not decision.approve:
            st.status = "closed"
            st.outcome = Outcome(status="rejected_by_human", rounds=st.round)
            return st
        if kind == "risky_clause":
            st.reviewed_clauses += [r.clause_id for r in st.risks if r.requires_human]
            return self.start(st)
        if kind == "redline_rejected":
            st.reviewed_clauses += [c for c, ok in st.redline_results.items() if not ok]
            return self._next_turn(st)
        if kind == "new_legal_terms":
            return self._next_turn(st)
        if kind == "value_limit":
            return self._sign(st, st.agreed_terms)
        if kind == "no_deal_high_value":
            st.status = "closed"
            st.outcome = Outcome(status="handed_off", rounds=st.round, final_terms=st.their_last)
            return st
        raise ValueError(f"unknown escalation kind {kind}")

    # ================================================================== endings
    def _agree(self, st: NegotiationState, terms: Terms) -> NegotiationState:
        st.agreed_terms = terms
        value = terms.price * max(1, terms.term_months / 12)
        if self.use_risk_gate and value > self.s.escalation.autonomy_value_limit:
            return self._escalate(st, "pre_signature", "value_limit",
                                  [f"deal value ${value:,.0f} exceeds autonomy limit ${self.s.escalation.autonomy_value_limit:,.0f}"], 0.7)
        return self._sign(st, terms)

    def _sign(self, st: NegotiationState, terms: Terms) -> NegotiationState:
        unreviewed = sum(1 for r in st.risks if r.requires_human and not st.redline_results.get(r.clause_id)
                         and r.clause_id not in st.reviewed_clauses)
        accepted = [c for c, ok in st.redline_results.items() if ok]
        env = self.esign.send_for_signature(st.contract_id, {
            "customer": st.context.customer, "terms": terms.model_dump(), "accepted_redlines": accepted,
            "human_reviewed_clauses": st.reviewed_clauses, "audit_head": self.audit.head,
        })
        st.status = "signed"
        st.outcome = Outcome(status="agreed", final_terms=terms, rounds=st.round, envelope_id=env,
                             signed_unreviewed_risky_clauses=unreviewed, accepted_redlines=accepted,
                             escalation=EscalationDecision(escalate=False))
        self._log(st, "orchestrator", "EXECUTE", f"agreed ${terms.price:,.0f}/net{terms.payment_days} in {st.round} rounds; envelope {env}")
        if self.learn:
            c = st.context
            self.crm.record(DealRecord(deal_id=st.contract_id, segment=c.segment, region=c.region, product=c.product,
                                       seats=c.seats, list_price=c.list_price, final_price=terms.price,
                                       payment_days=terms.payment_days, term_months=terms.term_months, won=True, rounds=st.round))
            self._log(st, "memory", "WRITE_BACK", "closed deal added to CRM memory")
        return st

    def _fail(self, st: NegotiationState, why: str) -> NegotiationState:
        if self.use_risk_gate and st.context.list_price >= self.s.escalation.escalate_failed_high_value:
            return self._escalate(st, "in_negotiation", "no_deal_high_value", [why + " on high-value deal"], 0.6)
        st.status = "closed"
        st.outcome = Outcome(status="walked_away" if "walked" in why else "no_agreement", rounds=st.round)
        self._log(st, "orchestrator", "END_NO_DEAL", why)
        return st

    # ================================================================== simulation driver
    def drive(self, st: NegotiationState, counterparty: Counterparty) -> NegotiationState:
        """Feed simulated counterparty replies until the machine needs a human or finishes."""
        while st.status == "awaiting_reply":
            reply = counterparty.respond(st.round, st.last_our_offer, st.last_sent_redlines)
            st = self.on_reply(st, reply)
        return st

    def run(self, contract_id: str, text: str, ctx: DealContext, counterparty: Counterparty) -> NegotiationState:
        """Batch mode used by the evaluation: analyze -> start -> drive (stops at first escalation)."""
        st = self.analyze(contract_id, text, ctx)
        return self.drive(self.start(st), counterparty)
