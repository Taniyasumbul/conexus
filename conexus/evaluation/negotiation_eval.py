"""RO3 / RO5: end-to-end negotiation evaluation, baselines and ablations.

Table A (end to end, all contracts): full CoNexus vs ablations vs baselines,
  including risk exposure = expert-labelled human-required clauses that ended
  up in a signed contract without being redlined away or reviewed by a human.
Table B (negotiation only, risk gate off for everyone, contracts with a ZOPA):
  isolates the effect of CRM memory on deal quality.

Time-to-close uses a transparent parametric model (TIME_MODEL) - replace these
assumptions with measured numbers from a pilot / user study for the paper.
"""
from __future__ import annotations

import statistics as stats
import time

from ..agents.audit import AuditAgent
from ..config import DATA, RUNS, Settings
from ..llm import LLM
from ..models import DealContext, Outcome, Terms
from ..orchestrator import Orchestrator
from ..sim.counterparty import RuleCounterparty
from .baselines import RuleBasedNegotiator, SingleLLMNegotiator
from .escalation_eval import load_contracts

TIME_MODEL = {
    "counterparty_reply_days_per_round": 1.0,  # async email turnaround
    "agent_turn_days": 0.0,                    # agent replies immediately
    "human_turn_days": 1.0,                    # human sales rep turnaround per round
    "legal_review_days": 5.0,                  # per escalation / per contract in human-only flow
}
COC = 0.12


def _value(t: Terms) -> float:
    return t.price * (1 - COC * t.payment_days / 365)


def _exposure(c: dict, o: Outcome) -> int:
    if o.status != "agreed":
        return 0
    return sum(1 for cl in c["clauses"] if cl["requires_human"] and f"c{cl['section']}" not in o.accepted_redlines)


def _days(o: Outcome, human_only: bool = False) -> float:
    tm = TIME_MODEL
    turn = tm["human_turn_days"] if human_only else tm["agent_turn_days"]
    d = o.rounds * (tm["counterparty_reply_days_per_round"] + turn)
    if human_only or o.status == "escalated":
        d += tm["legal_review_days"]
    return d


class _Orch:
    def __init__(self, name: str, orch: Orchestrator):
        self.name, self.orch = name, orch

    def run(self, cid, text, ctx, cp) -> Outcome:
        return self.orch.run(cid, text, ctx, cp).outcome


def _summarise(name: str, contracts: list[dict], outcomes: list[Outcome], runtimes: list[float], human_only=False) -> dict:
    n = len(outcomes)
    agreed = [(c, o) for c, o in zip(contracts, outcomes) if o.status == "agreed"]
    floors = {c["contract_id"]: DealContext(**c["context"]).list_price * 0.55 for c in contracts}
    shares, ratios = [], []
    for c, o in agreed:
        wtp, fl = c["hidden"]["wtp"], floors[c["contract_id"]]
        ratios.append(o.final_terms.price / wtp)
        if wtp > fl:
            shares.append(min(1.0, max(0.0, (o.final_terms.price - fl) / (wtp - fl))))
    risky = [(c, o) for c, o in zip(contracts, outcomes) if c["should_escalate"]]
    handled = [o.status == "escalated" or _exposure(c, o) == 0 for c, o in risky]
    return {
        "system": name,
        "n": n,
        "agreement_rate": round(len(agreed) / n, 3),
        "escalation_rate": round(sum(o.status == "escalated" for o in outcomes) / n, 3),
        "avg_rounds_to_agree": round(stats.mean(o.rounds for _, o in agreed), 2) if agreed else None,
        "price_over_wtp": round(stats.mean(ratios), 3) if ratios else None,
        "surplus_share": round(stats.mean(shares), 3) if shares else None,
        "revenue_per_contract": round(sum(_value(o.final_terms) for _, o in agreed) / n, 1),
        "risky_contracts_handled": round(sum(handled) / len(handled), 3) if handled else None,
        "unreviewed_risky_clauses_signed": sum(_exposure(c, o) for c, o in zip(contracts, outcomes)),
        "est_days_to_outcome": round(stats.mean(_days(o, human_only) for o in outcomes), 2),
        "runtime_ms_per_contract": round(1000 * stats.mean(runtimes), 2),
    }


def _run_system(system, contracts: list[dict], seed: int) -> tuple[list[Outcome], list[float]]:
    outs, times = [], []
    for c in contracts:
        h = c["hidden"]
        cp = RuleCounterparty(h["wtp"], Terms(price=h["opening_price"], payment_days=h.get("opening_days", 30)),
                              h["persona"], seed=seed + int(c["contract_id"].split("_")[1]))
        text = (DATA / "contracts" / f"{c['contract_id']}.txt").read_text()
        t0 = time.perf_counter()
        outs.append(system.run(c["contract_id"], text, DealContext(**c["context"]), cp))
        times.append(time.perf_counter() - t0)
    return outs, times


def run(settings: Settings, llm: LLM | None = None, seed: int = 0, limit: int | None = None, llm_limit: int = 20) -> dict:
    contracts = load_contracts()[:limit]
    RUNS.mkdir(exist_ok=True)
    audit_path = RUNS / "eval_audit.jsonl"
    audit_path.unlink(missing_ok=True)
    maxd = settings.pricing.max_discount

    systems = [
        _Orch("conexus (full)", Orchestrator(settings, audit=AuditAgent(audit_path))),
        _Orch("ablation: no audit", Orchestrator(settings)),
        _Orch("ablation: no memory", Orchestrator(settings, use_memory=False)),
        _Orch("ablation: no risk gate", Orchestrator(settings, use_risk_gate=False)),
        RuleBasedNegotiator(maxd, settings.escalation.max_rounds),
    ]
    table_a = []
    rule_outs = None
    for sysm in systems:
        outs, times = _run_system(sysm, contracts, seed)
        table_a.append(_summarise(sysm.name, contracts, outs, times))
        if sysm.name == "rule_based":
            rule_outs = outs
    # Human-only: legal review on every contract + human-paced rounds (rounds taken from rule-based run)
    table_a.append({**_summarise("human-only (modelled)", contracts, rule_outs, [0.0], human_only=True),
                    "unreviewed_risky_clauses_signed": 0, "risky_contracts_handled": 1.0, "runtime_ms_per_contract": None})

    zopa = [c for c in contracts if c["hidden"]["wtp"] > DealContext(**c["context"]).list_price * (1 - maxd)]
    neg_systems = [
        _Orch("memory (CoNexus pricing)", Orchestrator(settings, use_risk_gate=False)),
        _Orch("no memory (cold start)", Orchestrator(settings, use_memory=False, use_risk_gate=False)),
        RuleBasedNegotiator(maxd, settings.escalation.max_rounds),
    ]
    table_b = []
    for sysm in neg_systems:
        outs, times = _run_system(sysm, zopa, seed)
        table_b.append(_summarise(sysm.name, zopa, outs, times))

    if llm is not None:
        sub = contracts[:llm_limit]
        outs, times = _run_system(SingleLLMNegotiator(llm, maxd, settings.escalation.max_rounds), sub, seed)
        table_a.append(_summarise(f"single_llm ({llm.name}, n={len(sub)})", sub, outs, times))
        conexus_sub, t2 = _run_system(_Orch("x", Orchestrator(settings, llm)), sub, seed)
        table_a.append(_summarise(f"conexus + {llm.name} (n={len(sub)})", sub, conexus_sub, t2))

    ok, msg = AuditAgent.verify(audit_path)
    return {"table_a_end_to_end": table_a, "table_b_negotiation_only": table_b,
            "n_contracts": len(contracts), "n_zopa": len(zopa), "time_model": TIME_MODEL,
            "audit_verification": msg, "audit_events": sum(1 for _ in open(audit_path))}
