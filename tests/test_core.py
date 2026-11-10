import json

from conexus.agents.analyst import ContractAnalystAgent, extract_payment_days
from conexus.agents.audit import AuditAgent
from conexus.agents.risk import LegalRiskAgent, RiskClassifier
from conexus.config import DATA, get_settings
from conexus.llm import strict_json_schema
from conexus.models import Clause, ClauseType, DealContext, Terms
from conexus.orchestrator import Orchestrator
from conexus.sim.counterparty import RuleCounterparty

S = get_settings()


def test_audit_chain_detects_tampering(tmp_path):
    p = tmp_path / "a.jsonl"
    a = AuditAgent(p)
    for i in range(5):
        a.log("x", "ACT", f"step {i}", {"i": i}, "k")
    assert AuditAgent.verify(p)[0]
    lines = p.read_text().splitlines()
    ev = json.loads(lines[2])
    ev["rationale"] = "edited after the fact"
    lines[2] = json.dumps(ev)
    p.write_text("\n".join(lines) + "\n")
    ok, msg = AuditAgent.verify(p)
    assert not ok and "modified" in msg


def test_audit_detects_deleted_event(tmp_path):
    p = tmp_path / "a.jsonl"
    a = AuditAgent(p)
    for i in range(4):
        a.log("x", "ACT", str(i))
    lines = p.read_text().splitlines()
    p.write_text("\n".join(lines[:1] + lines[2:]) + "\n")
    assert not AuditAgent.verify(p)[0]


def test_hard_rules_force_human():
    agent = LegalRiskAgent(S, None, RiskClassifier(), mode="hybrid")
    risky = Clause(id="c1", type=ClauseType.IP_OWNERSHIP,
                   text="Vendor hereby assigns to Customer all background IP and pre-existing tools.")
    safe = Clause(id="c2", type=ClauseType.IP_OWNERSHIP,
                  text="Vendor retains all right, title and interest in the Software.")
    assert agent.assess(risky).requires_human
    assert not agent.assess(safe).requires_human


def test_commercial_clause_is_redlined_not_escalated():
    agent = LegalRiskAgent(S, None, RiskClassifier(), mode="rules")
    r = agent.assess(Clause(id="c1", type=ClauseType.PAYMENT_TERMS, text="Customer shall pay invoices net 90 days."))
    assert r.redlinable and not r.requires_human and r.redline


def test_analyst_extracts_opening_terms():
    text = "1. Fees\nCustomer shall pay an annual subscription fee of USD 12,500 for 40 user seats.\n\n" \
           "2. Payment Terms\nInvoices are payable net 60 days.\n"
    clauses, terms = ContractAnalystAgent().analyze(text)
    assert [c.type for c in clauses] == [ClauseType.PRICE, ClauseType.PAYMENT_TERMS]
    assert terms == Terms(price=12500, payment_days=60)
    assert extract_payment_days("within thirty (30) days") == 30


def test_strict_schema_is_closed():
    sch = strict_json_schema(Terms)
    assert sch["additionalProperties"] is False and set(sch["required"]) == {"price", "payment_days", "term_months"}


def test_end_to_end_offline(tmp_path):
    row = json.loads((DATA / "labels" / "contracts.jsonl").read_text().splitlines()[0])
    h = row["hidden"]
    audit = AuditAgent(tmp_path / "audit.jsonl")
    orch = Orchestrator(S, audit=audit, out_dir=tmp_path)
    cp = RuleCounterparty(h["wtp"], Terms(price=h["opening_price"]), h["persona"], seed=0)
    st = orch.run(row["contract_id"], (DATA / "contracts" / f"{row['contract_id']}.txt").read_text(),
                  DealContext(**row["context"]), cp)
    assert st.outcome is not None
    if st.outcome.status == "agreed":
        assert st.outcome.final_terms.price >= st.plan.floor_price
    assert AuditAgent.verify(tmp_path / "audit.jsonl")[0]
