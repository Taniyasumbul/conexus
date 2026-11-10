"""Negotiation Orchestrator: runs the pipeline over the shared NegotiationState and
owns the escalation decision (the risk-gated autonomy boundary, RO2).

Escalation triggers (all logged with rationale):
  pre_negotiation  - a clause requires a human and has no autonomous fallback
  in_negotiation   - a risk-critical redline is rejected; counterparty adds new
                     legal terms; talks fail / stall on a high-value deal
  pre_signature    - agreed deal value exceeds the autonomy limit
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
from .models import (ClauseRisk, DealContext, EscalationDecision, NegotiationState, Offer, Outcome, RiskLevel,
                     Terms)


class Counterparty(Protocol):
    def respond(self, rnd: int, ours: Terms | None, redline_ids: list[str]) -> str: ...


class Orchestrator:
    def __init__(self, settings: Settings, llm: LLM | None = None, *, use_memory: bool = True,
                 use_risk_gate: bool = True, audit: AuditAgent | None = None, risk_mode: str = "hybrid",
                 classifier: RiskClassifier | None = None, crm: CRMStore | None = None,
                 outbound: Channel | None = None, escalations: Channel | None = None, out_dir: Path = RUNS):
        self.s = settings
        self.use_risk_gate = use_risk_gate
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

    # ------------------------------------------------------------------ helpers
    def _log(self, st: NegotiationState, agent: str, action: str, why: str, data=None):
        self.audit.log(agent, action, why, data, contract_id=st.contract_id)

    def _escalate(self, st: NegotiationState, stage: str, triggers: list[str], score: float = 1.0,
                  terms: Terms | None = None, rounds: int = 0) -> Outcome:
        dec = EscalationDecision(escalate=True, stage=stage, triggers=triggers, score=score)
        risky = [r for r in st.risks if r.requires_human]
        packet = (
            f"Contract {st.contract_id} with {st.context.customer} needs human review ({stage}).\n"
            f"Triggers: {'; '.join(triggers)}\n"
            f"Current terms: {terms.model_dump() if terms else 'n/a'}\n"
            "Flagged clauses:\n" + "\n".join(f"  - {r.clause_id} [{r.clause_type.value}] {', '.join(r.reasons) or r.level.value}" for r in risky)
        )
        self.escalations.send("legal-review", f"[CoNexus] Escalation: {st.contract_id}", packet)
        self._log(st, "orchestrator", "ESCALATE", "; ".join(triggers), dec.model_dump())
        return Outcome(status="escalated", escalation=dec, final_terms=terms, rounds=rounds,
                       accepted_redlines=[c for c, ok in self._redline_results.items() if ok])

    # ------------------------------------------------------------------ pipeline
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
        blocking = [r for r in st.risks if r.requires_human and not r.redlinable]
        if blocking:
            return EscalationDecision(
                escalate=True, stage="pre_negotiation", score=max(r.score for r in blocking),
                triggers=[f"{r.clause_id} ({r.clause_type.value}) requires human: {', '.join(r.reasons) or 'score ' + str(r.score)}" for r in blocking],
            )
        return EscalationDecision(escalate=False, score=max((r.score for r in st.risks), default=0.0))

    def run(self, contract_id: str, text: str, ctx: DealContext, counterparty: Counterparty) -> NegotiationState:
        self._redline_results: dict[str, bool] = {}
        st = self.analyze(contract_id, text, ctx)
        esc = self.s.escalation

        gate = self.pre_negotiation_gate(st)
        if gate.escalate:
            st.outcome = self._escalate(st, "pre_negotiation", gate.triggers, gate.score)
            return st

        redlines: list[ClauseRisk] = [r for r in st.risks if r.redlinable and r.level != RiskLevel.LOW] if self.use_risk_gate else []
        st.pending_redlines = [r.clause_id for r in redlines]
        if redlines:
            self._log(st, "legal_risk", "PROPOSE_REDLINES", f"{len(redlines)} autonomous redlines", st.pending_redlines)

        st.plan = self.pricing.plan(ctx)
        if self.memory:
            st.similar_deals = [d for d, _ in self.memory.retrieve(ctx)[:5]]
        self._log(st, "sales_pricing", "PRICING_PLAN",
                  f"anchor ${st.plan.anchor.price:,.0f}, floor ${st.plan.floor_price:,.0f}; " + " | ".join(st.plan.evidence),
                  st.plan.model_dump())

        their_last = st.opening_terms
        if their_last:
            st.history.append(Offer(round=0, sender="them", terms=their_last, message="(contract as drafted)"))

        for rnd in range(1, esc.max_rounds + 1):
            ours = self.pricing.next_offer(st.plan, rnd, esc.max_rounds, their_last)
            open_redlines = [r for r in redlines if r.clause_id not in self._redline_results]

            # Accept their position if it beats what we would offer next
            if their_last and not open_redlines and self.pricing.acceptable(st.plan, their_last, ours):
                msg = self.comms.compose(their_last, rnd, accept=True, customer=ctx.customer)
                self.outbound.send(ctx.customer, "Re: Subscription agreement", msg)
                st.history.append(Offer(round=rnd, sender="us", terms=their_last, message=msg, accept=True))
                self._log(st, "sales_pricing", "ACCEPT_OFFER",
                          f"their ${their_last.price:,.0f}/net{their_last.payment_days} >= our next ${ours.price:,.0f}")
                return self._close(st, their_last, rnd)

            msg = self.comms.compose(ours, rnd, open_redlines, customer=ctx.customer)
            self.outbound.send(ctx.customer, "Re: Subscription agreement", msg)
            st.history.append(Offer(round=rnd, sender="us", terms=ours, message=msg))
            self._log(st, "communication", "SEND_OFFER", f"round {rnd}: ${ours.price:,.0f}, net {ours.payment_days}",
                      {"redlines": [r.clause_id for r in open_redlines]})

            reply = counterparty.respond(rnd, ours, [r.clause_id for r in open_redlines])
            theirs = self.comms.parse(reply, rnd, [r.clause_id for r in open_redlines])
            st.history.append(theirs)
            self._log(st, "communication", "RECEIVE_REPLY", reply[:300],
                      theirs.model_dump(include={'terms', 'accept', 'walk_away', 'redline_responses', 'new_legal_terms'}))

            for cid, ok in theirs.redline_responses.items():
                self._redline_results[cid] = ok
                risk = next(r for r in redlines if r.clause_id == cid)
                if not ok and risk.requires_human and esc.escalate_on_rejected_redline:
                    st.outcome = self._escalate(st, "in_negotiation", [f"redline on risk-critical clause {cid} rejected"],
                                                risk.score, ours, rnd)
                    return st
                self._log(st, "legal_risk", "REDLINE_" + ("ACCEPTED" if ok else "REJECTED"),
                          f"{cid}: " + ("resolved" if ok else "commercial term, accepted as drafted"))

            if theirs.new_legal_terms and esc.escalate_on_new_legal_terms and self.use_risk_gate:
                st.outcome = self._escalate(st, "in_negotiation", ["counterparty introduced new legal terms"], 0.9, ours, rnd)
                return st
            if theirs.accept:
                return self._close(st, ours, rnd)
            if theirs.walk_away:
                return self._fail(st, rnd, "counterparty walked away", ours)
            if theirs.terms:
                their_last = theirs.terms
        return self._fail(st, esc.max_rounds, f"no agreement after {esc.max_rounds} rounds", their_last)

    # ------------------------------------------------------------------ endings
    def _close(self, st: NegotiationState, terms: Terms, rnd: int) -> NegotiationState:
        if self.use_risk_gate and terms.price * max(1, terms.term_months / 12) > self.s.escalation.autonomy_value_limit:
            st.outcome = self._escalate(st, "pre_signature",
                                        [f"deal value ${terms.price:,.0f} exceeds autonomy limit ${self.s.escalation.autonomy_value_limit:,.0f}"],
                                        0.7, terms, rnd)
            return st
        unreviewed = sum(1 for r in st.risks if r.requires_human and not self._redline_results.get(r.clause_id))
        env = self.esign.send_for_signature(st.contract_id, {
            "customer": st.context.customer, "terms": terms.model_dump(),
            "accepted_redlines": [c for c, ok in self._redline_results.items() if ok],
            "audit_head": self.audit.head,
        })
        st.outcome = Outcome(status="agreed", final_terms=terms, rounds=rnd, envelope_id=env,
                             signed_unreviewed_risky_clauses=unreviewed,
                             accepted_redlines=[c for c, ok in self._redline_results.items() if ok],
                             escalation=EscalationDecision(escalate=False))
        self._log(st, "orchestrator", "EXECUTE", f"agreed ${terms.price:,.0f}/net{terms.payment_days} in {rnd} rounds; envelope {env}")
        return st

    def _fail(self, st: NegotiationState, rnd: int, why: str, terms: Terms | None) -> NegotiationState:
        if self.use_risk_gate and st.context.list_price >= self.s.escalation.escalate_failed_high_value:
            st.outcome = self._escalate(st, "in_negotiation", [why + " on high-value deal"], 0.6, terms, rnd)
            return st
        st.outcome = Outcome(status="walked_away" if "walked" in why else "no_agreement", rounds=rnd, final_terms=None)
        self._log(st, "orchestrator", "END_NO_DEAL", why)
        return st
