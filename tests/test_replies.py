"""Inbound replies must never sign a deal by accident (false acceptance is the worst failure)."""
import json

import pytest

from conexus.agents.communication import CommunicationAgent
from conexus.config import DATA, get_settings
from conexus.models import DealContext, HumanDecision
from conexus.orchestrator import Orchestrator

PARSE = CommunicationAgent(None).parse

EXITS = [
    "We are no longer interested in this deal.",
    "This is a bad deal for us, we walk away.",
    "Thanks, but we have decided to go with another vendor.",
    "We will not be moving forward with this deal.",
    "We have decided to pass on this deal.",
    "Unfortunately we must decline your offer.",
]
ACCEPTS = [
    "We accept your proposal of $12,000 per year, net 30. Deal.",
    "We accept your offer.",
    "Great, we have a deal!",
    "Deal. Let's sign.",
    "We agree to your terms.",
]
NOT_ACCEPTS = [
    "We cannot accept your proposal at that price.",
    "We do not accept your offer, $9,000 is our limit.",
    "What would the deal look like at net 45?",
    "This deal needs a lower price.",
]


@pytest.mark.parametrize("msg", EXITS)
def test_exit_messages_are_never_acceptance(msg):
    r = PARSE(msg, 2, [])
    assert r.walk_away and not r.accept


@pytest.mark.parametrize("msg", ACCEPTS)
def test_explicit_acceptance(msg):
    r = PARSE(msg, 2, [])
    assert r.accept and not r.walk_away


@pytest.mark.parametrize("msg", NOT_ACCEPTS)
def test_negated_or_incidental_deal_is_not_acceptance(msg):
    assert not PARSE(msg, 2, []).accept


def _negotiating(tmp_path):
    """An orchestrator and a contract that is waiting for the customer's reply."""
    orch = Orchestrator(get_settings(), out_dir=tmp_path, use_risk_gate=False)
    row = json.loads((DATA / "labels" / "contracts.jsonl").read_text().splitlines()[0])
    text = (DATA / "contracts" / f"{row['contract_id']}.txt").read_text()
    st = orch.start(orch.analyze(row["contract_id"], text, DealContext(**row["context"])))
    assert st.status == "awaiting_reply"
    return orch, st


def test_exit_reply_closes_instead_of_signing(tmp_path):
    orch, st = _negotiating(tmp_path)
    st = orch.on_reply(st, "We are no longer interested in this deal.")
    assert st.status == "closed" and st.outcome.status == "walked_away"


def test_conflicting_reply_goes_to_a_person(tmp_path):
    orch, st = _negotiating(tmp_path)
    st = orch.on_reply(st, "We accept your proposal, but honestly we will walk away if legal pushes back.")
    assert st.status == "awaiting_human" and st.escalation.kind == "unclear_reply"
    st = orch.resolve(st, HumanDecision(reviewer="legal@x.io", approve=True, note="not an exit"))
    assert st.status == "awaiting_reply"  # negotiation continues, nothing signed


def test_acceptance_signs_exactly_the_pending_offer(tmp_path):
    orch, st = _negotiating(tmp_path)
    ours = st.last_our_offer
    st = orch.on_reply(st, f"We accept your proposal of ${ours.price:,.0f} per year, net {ours.payment_days}. Deal.")
    assert st.status in ("signed", "awaiting_human")
    assert st.agreed_terms == ours


def test_acceptance_at_a_different_price_is_a_counter_offer(tmp_path):
    orch, st = _negotiating(tmp_path)
    ours = st.last_our_offer
    st = orch.on_reply(st, f"We accept your proposal at ${ours.price * 0.6:,.0f} per year, net 30.")
    assert st.status != "signed" and st.agreed_terms is None
