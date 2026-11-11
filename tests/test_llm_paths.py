"""Every LLM code path, exercised offline with a scripted fake model (and a mocked
Anthropic client), including the fallback when the model errors or refuses."""
from types import SimpleNamespace

import pytest

from conexus.agents.analyst import ContractAnalystAgent
from conexus.agents.communication import CommunicationAgent, _ParsedReply
from conexus.agents.risk import LegalRiskAgent, RiskClassifier
from conexus.config import get_settings
from conexus.llm import AnthropicLLM, LLMError, strict_json_schema
from conexus.models import Clause, ClauseType, RiskLevel, Terms

S = get_settings()


class FakeLLM:
    name = "fake"

    def __init__(self, structured=None, text="Dear team, our offer stands.", fail=False):
        self._structured, self._text, self.fail, self.calls = structured or {}, text, fail, []

    def structured(self, system, prompt, schema):
        self.calls.append(schema.__name__)
        if self.fail:
            raise LLMError("model unavailable")
        return schema(**self._structured[schema.__name__])

    def text(self, system, prompt):
        self.calls.append("text")
        if self.fail:
            raise LLMError("model unavailable")
        return self._text


def test_analyst_asks_llm_only_when_keywords_are_unsure():
    llm = FakeLLM({"_LLMClauseType": {"type": "warranty", "confidence": 0.8}})
    an = ContractAnalystAgent(llm, type_classifier=False)
    clauses, _ = an.analyze("1. Miscellaneous\nThe goods shall conform to the agreed specification.\n\n"
                            "2. Payment Terms\nInvoices are payable net 30 days.\n")
    assert clauses[0].type == ClauseType.WARRANTY        # unclear clause -> LLM
    assert clauses[1].type == ClauseType.PAYMENT_TERMS   # heading hint -> no LLM call
    assert llm.calls == ["_LLMClauseType"]


def test_risk_llm_mode_and_hybrid_llm():
    llm = FakeLLM({"_LLMAssessment": {"level": "high", "requires_human": True, "reasons": ["One-sided audit"]}})
    clause = Clause(id="c1", type=ClauseType.DATA_PROTECTION, text="Customer may inspect records annually.")
    r = LegalRiskAgent(S, llm, RiskClassifier(), mode="llm").assess(clause)
    assert r.requires_human and r.level == RiskLevel.HIGH and "LLM: One-sided audit" in r.reasons
    r2 = LegalRiskAgent(S, llm, RiskClassifier(), mode="hybrid+llm").assess(clause)
    assert r2.requires_human  # LLM can raise, never lower, the hybrid score


def test_risk_falls_back_when_llm_fails():
    clause = Clause(id="c1", type=ClauseType.IP_OWNERSHIP, text="Vendor hereby assigns all background IP and pre-existing tools.")
    r = LegalRiskAgent(S, FakeLLM(fail=True), RiskClassifier(), mode="hybrid+llm").assess(clause)
    assert r.requires_human  # hard rule still fires
    assert any("LLM unavailable" in x for x in r.reasons)


def test_communication_llm_parse_and_compose():
    llm = FakeLLM({"_ParsedReply": {"price": 18500, "payment_days": 45, "accept": False, "walk_away": False,
                                    "accepted_redlines": ["c2"], "rejected_redlines": ["c6"], "new_legal_terms": True}},
                  text="Hello team, we propose $20,000.")
    comms = CommunicationAgent(llm)
    o = comms.parse("Eighteen and a half thousand works. Clause 2 is fine, clause 6 is not.", 2, ["c2", "c6"])
    assert o.terms == Terms(price=18500, payment_days=45)
    assert o.redline_responses == {"c2": True, "c6": False} and o.new_legal_terms
    # grounding: answers for clauses the customer never mentioned are dropped
    o2 = comms.parse("eighteen and a half thousand works if you drop the liability change", 2, ["c2", "c6"])
    assert o2.redline_responses == {}
    assert comms.compose(Terms(price=20000), 1, customer="Acme") == "Hello team, we propose $20,000."


def test_communication_falls_back_to_regex():
    o = CommunicationAgent(FakeLLM(fail=True)).parse("We can do $12,000 per year, net 45. We accept the change to clause c3.", 1, ["c3"])
    assert o.terms == Terms(price=12000, payment_days=45) and o.redline_responses == {"c3": True}


def test_strict_schema_closes_nested_objects():
    sch = strict_json_schema(_ParsedReply)
    assert sch["additionalProperties"] is False
    assert set(sch["required"]) == set(_ParsedReply.model_fields)


# ---------------------------------------------------------------- Anthropic wrapper (mocked client)
def _fake_anthropic(monkeypatch, response):
    llm = AnthropicLLM.__new__(AnthropicLLM)
    import anthropic

    llm._anthropic, llm.model, llm.effort, llm.name = anthropic, "claude-opus-5-5", "low", "anthropic:test"
    captured = {}

    def create(**kw):
        captured.update(kw)
        return response
    llm.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return llm, captured


def test_anthropic_structured_request_shape(monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"type": "price", "confidence": 0.9}')])
    llm, sent = _fake_anthropic(monkeypatch, resp)
    from conexus.agents.analyst import _LLMClauseType

    out = llm.structured("sys", "prompt", _LLMClauseType)
    assert out.type == ClauseType.PRICE
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    assert sent["output_config"]["format"]["type"] == "json_schema" and sent["output_config"]["effort"] == "low"


def test_anthropic_refusal_raises(monkeypatch):
    llm, _ = _fake_anthropic(monkeypatch, SimpleNamespace(stop_reason="refusal", content=[]))
    with pytest.raises(LLMError):
        llm.text("sys", "prompt")
