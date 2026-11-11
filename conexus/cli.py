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


@app.command("fetch-cuad")
def fetch_cuad(url: str = "https://github.com/TheAtticusProject/cuad/raw/main/data.zip"):
    """Download CUAD v1 (CC BY 4.0) and build data/cuad/clauses.jsonl."""
    import io
    import urllib.request
    import zipfile

    from .datasets.cuad import build

    raw_dir = DATA / "external" / "cuad_raw"
    raw = raw_dir / "CUADv1.json"
    if not raw.exists():
        con.print(f"Downloading {url} ...")
        with urllib.request.urlopen(url, timeout=300) as r:
            blob = r.read()
        raw_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            raw.write_bytes(z.read("CUADv1.json"))  # extract only the file we need, by name
    stats = build(raw, DATA / "cuad" / "clauses.jsonl")
    con.print(stats)


@app.command("eval-cuad")
def eval_cuad(with_llm: bool = False, llm_limit: int = 60):
    """RO2 on real contract text (CUAD): rules vs ML vs hybrid, plus clause-type accuracy."""
    from .evaluation.cuad_eval import run

    s = get_settings()
    res = run(s, build_llm(s) if with_llm else None, llm_limit=llm_limit)
    _table([{"mode": k, **v} for k, v in res["results"].items()],
           f"CUAD dev, 5-fold CV (n={res['n_clauses']} clauses, {res['n_contracts']} contracts, "
           f"{res['positives']} positive, {res['expert_labelled']} expert-labelled)")
    _table([{"mode": k, **v} for k, v in res["held_out_test"].items()],
           f"Held-out TEST contracts (n={res['n_test_clauses']} clauses, {res['n_test_contracts']} contracts) - report once")
    _table(res["recall_by_category"], "Recall on deal-breaker categories")
    con.print(f"Analyst clause-type accuracy (no headings): {res['analyst_type_accuracy']}")
    out = RUNS / "eval_cuad.json"
    RUNS.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    con.print(f"saved {out}")


@app.command("eval-llm")
def eval_llm(risk_sample: int = 60, negotiation_contracts: int = 10, skip_negotiation: bool = False):
    """LLM experiments: reply-parsing robustness, risk on held-out CUAD, single-LLM vs CoNexus.
    Uses CONEXUS_LLM (anthropic or ollama). Every call is local with ollama; with anthropic it is billed."""
    from .evaluation.cuad_eval import run as run_cuad
    from .evaluation.llm_eval import parsing_robustness
    from .evaluation.negotiation_eval import _run_system, _summarise, _Orch
    from .evaluation.baselines import SingleLLMNegotiator
    from .evaluation.escalation_eval import load_contracts

    s = get_settings()
    llm = build_llm(s)
    if llm is None:
        raise typer.BadParameter("Set CONEXUS_LLM=ollama (local) or anthropic in .env first")
    out: dict = {"model": llm.name}

    con.rule(f"1/3 Reply parsing robustness ({llm.name})")
    pr = parsing_robustness(llm)
    out["parsing"] = pr
    _table([{"parser": k, "overall": v["overall"], **v["by_style"], "s/msg": v["sec_per_message"]} for k, v in pr["results"].items()],
           f"Messages parsed fully correctly (n={pr['n_messages']})")

    con.rule("2/3 Risk scoring on held-out CUAD contracts")
    cu = run_cuad(s, llm, llm_limit=risk_sample)
    out["risk_held_out"] = {k: v for k, v in cu["held_out_test"].items() if "sample" in k}
    _table([{"mode": k, **v} for k, v in out["risk_held_out"].items()], "Stratified sample of held-out test clauses")

    if not skip_negotiation:
        con.rule("3/3 Negotiation: single monolithic LLM vs CoNexus (+LLM comms)")
        contracts = load_contracts()[:negotiation_contracts]
        rows = []
        for name, system in ((f"single_llm ({llm.name})", SingleLLMNegotiator(llm, s.pricing.max_discount, s.escalation.max_rounds)),
                             (f"conexus + {llm.name}", _Orch("c", Orchestrator(s, llm))),
                             ("conexus (offline)", _Orch("o", Orchestrator(s)))):
            outs, times = _run_system(system, contracts, 0)
            rows.append(_summarise(name, contracts, outs, times))
        out["negotiation"] = rows
        _table([{k: r[k] for k in ("system", "agreement_rate", "escalation_rate", "surplus_share", "unreviewed_risky_clauses_signed", "runtime_ms_per_contract")} for r in rows],
               f"First {len(contracts)} contracts, rule-based buyers")

    path = RUNS / "eval_llm.json"
    RUNS.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2, default=str))
    con.print(f"saved {path}")


@app.command("create-user")
def create_user(email: str, name: str = typer.Option(...), role: str = typer.Option("sales", help="sales | legal | admin"),
                db: Path = RUNS / "conexus.db"):
    """Create a login. Prompts for the password (never pass it on the command line)."""
    from .api.auth import MIN_PASSWORD, ROLES, hash_password
    from .store import Store

    if role not in ROLES:
        raise typer.BadParameter(f"role must be one of {ROLES}")
    pw = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    if len(pw) < MIN_PASSWORD:
        raise typer.BadParameter(f"password must be at least {MIN_PASSWORD} characters")
    store = Store(db)
    if store.user_by_email(email):
        raise typer.BadParameter(f"{email} already exists")
    store.create_user(email, name, role, hash_password(pw))
    con.print(f"[green]Created {role} {email}")


@app.command("verify-audit")
def verify_audit(path: Path):
    """Check that an audit log's hash chain is intact."""
    ok, msg = AuditAgent.verify(path)
    con.print(("[green]" if ok else "[red]") + msg)
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
