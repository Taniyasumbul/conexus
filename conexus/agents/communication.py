"""Communication Agent: turns structured offers into counterparty-facing messages
and parses the counterparty's natural-language replies back into structured offers."""
from __future__ import annotations

import re

from pydantic import BaseModel

from ..llm import LLM, LLMError
from ..models import ClauseRisk, Offer, Terms

LEGAL_TERMS = re.compile(r"exclusiv|non-compete|indemn|unlimited liability|intellectual property|source code|audit", re.I)


class _ParsedReply(BaseModel):
    price: float | None
    payment_days: int | None
    accept: bool
    walk_away: bool
    accepted_redlines: list[str]
    rejected_redlines: list[str]
    new_legal_terms: bool


class CommunicationAgent:
    name = "communication"

    def __init__(self, llm: LLM | None = None, company: str = "CoNexus Software"):
        self.llm = llm
        self.company = company

    # ---------- outbound ----------
    def compose(self, terms: Terms | None, rnd: int, redlines: list[ClauseRisk] | None = None,
                accept: bool = False, customer: str = "") -> str:
        facts = []
        if accept and terms:
            facts.append(f"We accept your proposal of ${terms.price:,.0f} per year with net {terms.payment_days} day payment terms.")
        elif terms:
            facts.append(f"Our proposal: ${terms.price:,.0f} per year, payment net {terms.payment_days} days, "
                         f"{terms.term_months}-month term.")
        for r in redlines or []:
            facts.append(f"Proposed change to clause {r.clause_id} ({r.clause_type.value}): \"{r.redline}\"")
        if self.llm:
            try:
                return self.llm.text(
                    f"You write concise, courteous B2B negotiation emails on behalf of {self.company}. "
                    "Include every fact given, with the exact numbers and clause ids. No placeholders, no signature block.",
                    f"Customer: {customer}\nRound {rnd}. Facts to communicate:\n- " + "\n- ".join(facts),
                )
            except LLMError:
                pass
        return f"Hi {customer} team,\n\n" + "\n".join(facts) + f"\n\nBest regards,\n{self.company}"

    # ---------- inbound ----------
    def parse(self, message: str, rnd: int, pending_redlines: list[str]) -> Offer:
        if self.llm:
            try:
                p = self.llm.structured(
                    "Extract the counterparty's negotiation position from this email.\n"
                    "- price: the total annual price they propose or accept, as a plain number in USD. Convert shorthand "
                    "and words: '18.5k' = 18500, 'twenty-one thousand' = 21000, 'USD 15,000' = 15000. null if no price.\n"
                    "- payment_days: integer days from phrases like 'net 45', '45-day terms', 'within 45 days', "
                    "'45 days credit period'. null if not mentioned.\n"
                    "- accepted_redlines / rejected_redlines: clause ids from the pending list. 'clause 6', 'section 6', "
                    "'point 6' and 'c6' all mean c6. Approval words (fine, agreed, works, okay) mean accepted; "
                    "refusals (no, push back, not acceptable, will not move) mean rejected.\n"
                    "- accept: true only if they agree to close the deal on the terms on the table.\n"
                    "- walk_away: true only if they end the negotiation.\n"
                    "- new_legal_terms: true if they introduce new legal obligations (exclusivity, indemnity, IP, audit).",
                    f"Pending clause ids: {pending_redlines}\n\nEmail:\n{message}",
                    _ParsedReply,
                )
                return Offer(
                    round=rnd, sender="them", message=message, accept=p.accept, walk_away=p.walk_away,
                    terms=Terms(price=p.price, payment_days=p.payment_days or 30) if p.price else None,
                    redline_responses=self._grounded({**{c: True for c in p.accepted_redlines}, **{c: False for c in p.rejected_redlines}},
                                                     message, pending_redlines),
                    new_legal_terms=p.new_legal_terms,
                )
            except LLMError:
                pass
        return self._regex_parse(message, rnd, pending_redlines)

    @staticmethod
    def _grounded(responses: dict[str, bool], message: str, pending: list[str]) -> dict[str, bool]:
        """Keep a clause response only if it is a pending redline AND its number appears in the
        message: removes answers the model invented for clauses the customer never mentioned."""
        out = {}
        for cid, ok in responses.items():
            num = cid.lstrip("cC")
            if cid in pending and re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", message):
                out[cid] = ok
        return out

    @staticmethod
    def _regex_parse(message: str, rnd: int, pending: list[str]) -> Offer:
        low = message.lower()
        price = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", message)
        days = re.search(r"net\s*(\d{2,3})", low)
        responses = {}
        for cid in pending:
            m = re.search(rf"(accept|agree|cannot accept|reject|decline)[^.]*\b{cid}\b", low)
            if m:
                responses[cid] = m.group(1) in ("accept", "agree")
        return Offer(
            round=rnd, sender="them", message=message,
            terms=Terms(price=float(price.group(1).replace(",", "")), payment_days=int(days.group(1)) if days else 30) if price else None,
            accept=bool(re.search(r"\bwe accept your (proposal|offer)\b|\bdeal\b", low)),
            walk_away=bool(re.search(r"walk away|end (these|our) discussions|no longer interested", low)),
            redline_responses=responses,
            new_legal_terms=bool(re.search(r"(we|also) (require|need|insist)[^.]*", low)) and bool(LEGAL_TERMS.search(low)),
        )
