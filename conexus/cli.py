"""CoNexus command line.

  conexus generate-data
  conexus analyze data/contracts/contract_003.txt --segment smb --region india --product pro --seats 40
  conexus negotiate data/contracts/contract_003.txt --wtp 9000 --persona hardball ...
  conexus demo contract_017
  conexus eval-escalation
  conexus eval-negotiation
  conexus verify-audit runs/audit.jsonl
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .agents.audit import AuditAgent
from .config import DATA, RUNS, get_settings
from .integrations.channels import ConsoleChannel
from .llm import build_llm
from .models import DealContext, Terms
from .orchestrator import Orchestrator
from .parsing import read_document
from .sim.counterparty import LLMCounterparty, RuleCounterparty
from .sim.world import LIST_PER_SEAT

app = typer.Typer(add_completion=False, help="CoNexus - risk-aware multi-agent contract negotiation")
con = Console()


def _ctx(customer, segment, region, product, seats) -> DealContext:
    return DealContext(customer=customer, segment=segment, region=region, product=product, seats=seats,
                       list_price=LIST_PER_SEAT[product] * seats)


def _table(rows: list[dict], title: str) -> None:
    if not rows:
        return
    t = Table(title=title, show_lines=False)
    for k in rows[0]:
        t.add_column(str(k), overflow="fold")
    for r in rows:
        t.add_row(*["" if v is None else str(v) for v in r.values()])
    con.print(t)


@app.command("generate-data")
def generate_data(seed: int = 7, contracts: int = 200, deals: int = 1500):
    """Generate the synthetic seed dataset (labelled clauses, contracts, CRM history)."""
    from .data_gen.generate import main

    main(seed, contracts, deals)


@app.command()
def analyze(path: Path, customer: str = "Customer", segment: str = "smb", region: str = "india",
            product: str = "pro", seats: int = 50, risk_mode: str = "hybrid"):
    """Extract clauses, score risk, and show the pre-negotiation escalation decision."""
    s = get_settings()
    orch = Orchestrator(s, build_llm(s), risk_mode=risk_mode)
    st = orch.analyze(path.stem, read_document(path), _ctx(customer, segment, region, product, seats))
    rows = []
    for c, r in zip(st.clauses, st.risks):
        rows.append({"id": c.id, "type": c.type.value, "level": r.level.value, "score": r.score,
                     "human": "YES" if r.requires_human else "", "redline": "yes" if r.redlinable else "",
                     "why": "; ".join(r.reasons)[:80]})
    _table(rows, f"Clause risk - {path.name}")
    con.print(f"Opening terms: {st.opening_terms}")
    con.print(f"Gate: {orch.pre_negotiation_gate(st).model_dump()}")


@app.command()
def negotiate(path: Path, wtp: float = typer.Option(..., help="Simulated buyer's private max price"),
              persona: str = "cooperative", customer: str = "Customer", segment: str = "smb", region: str = "india",
              product: str = "pro", seats: int = 50, llm_counterparty: bool = False, no_memory: bool = False):
    """Run the full pipeline against a simulated counterparty and print the transcript."""
    s = get_settings()
    llm = build_llm(s)
    run_dir = RUNS / datetime.now().strftime("%Y%m%d-%H%M%S")
    audit = AuditAgent(run_dir / "audit.jsonl")
    orch = Orchestrator(s, llm, audit=audit, use_memory=not no_memory, outbound=ConsoleChannel(),
                        escalations=ConsoleChannel(), out_dir=run_dir)
    text = read_document(path)
    ctx = _ctx(customer, segment, region, product, seats)
    _, opening = orch.analyst.analyze(text)
    opening = opening or Terms(price=ctx.list_price * 0.6)
    if llm_counterparty:
        if llm is None:
            raise typer.BadParameter("--llm-counterparty needs CONEXUS_LLM=anthropic or ollama")
        lcp = LLMCounterparty(llm, wtp, opening, persona, customer)
        cp = type("CP", (), {"respond": lambda self, rnd, ours, rl: lcp.respond(rnd, ours, rl, orch.comms.compose(ours, rnd, customer=customer))})()
    else:
        cp = RuleCounterparty(wtp, opening, persona, seed=0)
        _orig = cp.respond

        def _respond(rnd, ours, rl):
            msg = _orig(rnd, ours, rl)
            con.print(f"[cyan]--- {customer} (round {rnd}) ---[/cyan]\n{msg}")
            return msg
        cp.respond = _respond
    st = orch.run(path.stem, text, ctx, cp)
    con.rule("Outcome")
    con.print(st.outcome.model_dump())
    con.rule("Audit trail")
    con.print(audit.report(st.contract_id))
    con.print(f"\nAudit log: {run_dir / 'audit.jsonl'}  ({AuditAgent.verify(run_dir / 'audit.jsonl')[1]})")


@app.command()
def demo(contract_id: str = typer.Argument("contract_003"), llm_counterparty: bool = False):
    """Run `negotiate` on a generated contract using its stored scenario."""
    row = next(json.loads(l) for l in (DATA / "labels" / "contracts.jsonl").read_text().splitlines() if contract_id in l)
    c, h = row["context"], row["hidden"]
    con.print(f"[bold]{contract_id}[/bold]: {c['customer']} | {c['segment']}/{c['region']}/{c['product']} x{c['seats']} "
              f"| list ${c['list_price']:,.0f} | hidden WTP ${h['wtp']:,.0f} ({h['persona']}) | expert says escalate={row['should_escalate']}")
    negotiate(DATA / "contracts" / f"{contract_id}.txt", wtp=h["wtp"], persona=h["persona"], customer=c["customer"],
              segment=c["segment"], region=c["region"], product=c["product"], seats=c["seats"],
              llm_counterparty=llm_counterparty, no_memory=False)


@app.command("eval-escalation")
def eval_escalation(with_llm: bool = False, llm_limit: int = 60):
    """RO2: precision/recall of clause- and contract-level escalation."""
    from .evaluation.escalation_eval import clause_level, contract_level

    s = get_settings()
    llm = build_llm(s) if with_llm else None
    a = clause_level(s, llm=llm, llm_limit=llm_limit)
    b = contract_level(s)
    _table([{"mode": k, **v} for k, v in a["clause_level"].items()], f"Clause-level requires_human (grouped CV, n={a['n_clauses']})")
    _table(a["hybrid_threshold_sweep_scores_only"], "Hybrid score threshold sweep (score-only, before hard rules)")
    _table([{"mode": k, **v} for k, v in b["contract_level"].items()],
           f"Contract-level escalation (n={b['n_contracts']}, positives={b['positives']})")
    out = RUNS / "eval_escalation.json"
    RUNS.mkdir(exist_ok=True)
    out.write_text(json.dumps({**a, **b}, indent=2, default=int))
    con.print(f"saved {out}")


@app.command("eval-negotiation")
def eval_negotiation(with_llm: bool = False, llm_limit: int = 20, seed: int = 0):
    """RO3/RO5: baselines + ablations on simulated counterparties."""
    from .evaluation.negotiation_eval import run

    s = get_settings()
    res = run(s, build_llm(s) if with_llm else None, seed=seed, llm_limit=llm_limit)
    _table(res["table_a_end_to_end"], f"Table A - end to end (n={res['n_contracts']})")
    _table(res["table_b_negotiation_only"], f"Table B - negotiation only, risk gate off (n={res['n_zopa']} with ZOPA)")
    con.print(f"Audit: {res['audit_events']} events, {res['audit_verification']}")
    out = RUNS / "eval_negotiation.json"
    out.write_text(json.dumps(res, indent=2, default=int))
    con.print(f"saved {out}")


@app.command("verify-audit")
def verify_audit(path: Path):
    """Check that an audit log's hash chain is intact."""
    ok, msg = AuditAgent.verify(path)
    con.print(("[green]" if ok else "[red]") + msg)
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
